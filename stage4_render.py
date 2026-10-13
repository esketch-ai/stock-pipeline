"""단계 4 — Remotion 하드웨어 가속 렌더링 (VideoToolbox).

렌더링은 remotion/ 디렉터리에서 npx remotion render 를 호출한다.
VideoToolbox 하드웨어 인코더와 동적 Concurrency 설정은 remotion.config.ts 에 정의되므로
여기서는 --concurrency 를 강제로 덮어쓰지 않는다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import config
import cues as cues_mod
from config import DATA_DIR, OUTPUT_DIR, REMOTION_DIR
from logger import log
from video_files import video_filename


def _chart_kind(path: str) -> str:
    """차트 파일명에서 종류를 추론한다 (포인터 좌표 보정용)."""
    name = Path(path).stem.lower()
    if "momentum" in name or "rsi" in name:
        return "momentum"
    if "return" in name or "수익률" in name:
        return "return"
    if "trend" in name or "ma" in name:
        return "trend"
    return "price"


def _item_props(ticker: str, item: dict) -> dict:
    """StockVideo 컴포넌트가 기대하는 VideoItem 단일 객체."""
    script = item.get("script") or {}
    cand = item.get("candidate") or {}
    change = cand.get("change_rate")
    change_str = f"{change:+.2f}%" if isinstance(change, (int, float)) else None

    long_text = item.get("long_text") or ""
    timestamps = item.get("timestamps") or []

    # 방송용 지표 + 차트 포인터 cue 생성
    cue_list = []
    if long_text and timestamps:
        try:
            # 차트 파일명에서 종류를 추론해 포인터 대상을 차트별로 맞춘다
            chart_files = (
                item.get("chart_paths")
                or (script.get("chart_paths") or [])
            )
            kinds = [_chart_kind(p) for p in chart_files]
            cue_list = cues_mod.build_cues(
                long_text, timestamps, item.get("facts"), item.get("series"), kinds
            )
        except Exception as exc:
            log.warning("%s cue 생성 실패(무시): %s", ticker, exc)

    metrics = item.get("metrics")
    if not metrics and item.get("facts"):
        metrics = cues_mod.metrics_summary(item["facts"])

    # ── 장면 데이터 ──
    # 대본 섹션 + 팩트 + 수급 → 화면 단위 구성.
    # 실패해도 렌더는 계속된다 (레거시 모드로 물러난다).
    scenes, supply, levels, contact = [], None, None, None
    try:
        import chart_data
        import scene_data

        series = item.get("series")
        supply = chart_data.fetch_supply(ticker)
        levels = chart_data.support_resistance(series) if series else None
        sections = item.get("sections") or []
        if not any("text" in x for x in sections):
            paras = [x.strip() for x in (item.get("long_text") or "").split("\n\n") if x.strip()]
            if len(paras) == len(sections):
                for sec, para in zip(sections, paras):
                    sec["text"] = para
        scenes = scene_data.build_scenes(
            name=item.get("name") or script.get("name") or ticker,
            ticker=ticker,
            sections=sections,
            timestamps=timestamps,
            series=series,
            supply=supply,
            levels=levels,
            facts=item.get("facts") or {},
        )
    except Exception as exc:
        log.warning("%s 장면 구성 실패 — 기본 레이아웃으로 진행: %s", ticker, exc)

    from campaign import contact_payload
    contact = contact_payload(ticker)
    from investment_lenses import character_insight

    return {
        "ticker": ticker,
        "name": item.get("name") or script.get("name") or ticker,
        "audioSrc": item["audio"],
        "timestamps": timestamps,
        "script": script,
        # Remotion SVG 차트가 그릴 원본 OHLCV (없으면 PNG 폴백)
        "series": item.get("series"),
        # script 안쪽과 최상위 어느 쪽에 차트 목록이 있든 인식한다
        "charts": (
            item.get("chart_paths")
            or script.get("chart_paths")
            or (script.get("script") or {}).get("chart_paths")
            or []
        ),
        "changeRate": change_str,
        "metrics": metrics,
        "cues": cue_list,
        "scenes": scenes,
        "supply": supply,
        "levels": levels,
        "contact": contact,
        "investorInsight": character_insight(item.get("editorial_plan")),
    }


def _ensure_assets_linked() -> None:
    """public/cache, public/output 심볼릭 링크 보장 (staticFile 로컬 자산 로드용)."""
    public = REMOTION_DIR / "public"
    public.mkdir(parents=True, exist_ok=True)
    for name, target in (("cache", config.CACHE_DIR), ("output", config.OUTPUT_DIR)):
        link = public / name
        try:
            if link.is_symlink() or link.exists():
                if link.is_symlink() and link.resolve() == target.resolve():
                    continue
                link.unlink()
            link.symlink_to(target, target_is_directory=True)
        except OSError as exc:
            log.warning("%s 심볼릭 링크 생성 실패: %s", name, exc)


def render(manifest: dict[str, dict], composition: str = "StockVideo") -> list[Path]:
    """각 종목별 Remotion 렌더. 실패 시 빈 목록 반환."""
    if not manifest:
        log.warning("렌더링할 항목이 없습니다.")
        return []

    if not shutil.which("npx"):
        log.error("npx 없음 — Node.js 설치를 확인하세요.")
        return []

    _ensure_assets_linked()

    node_modules = REMOTION_DIR / "node_modules"
    if not node_modules.exists():
        log.warning("node_modules 없음 — npm install 실행 중...")
        subprocess.run(["npm", "install"], cwd=REMOTION_DIR, check=False)

    width, height = config.resolution()
    rendered: list[Path] = []

    for ticker, item in manifest.items():
        audio = item.get("audio")
        if not audio or not Path(audio).exists():
            # 검증에 막혔거나 TTS 결과가 없는 종목은 렌더하지 않는다.
            reason = "대본 검증 차단" if item.get("blocked") else "음성 파일 없음"
            log.error("렌더 건너뜀 %s — %s", ticker, reason)
            continue
        name = item.get("name") or (item.get("script") or {}).get("name") or ticker
        out_path = OUTPUT_DIR / video_filename(ticker, name)
        props_path = DATA_DIR / f"props_{ticker}.json"
        props_path.write_text(
            json.dumps({"items": [_item_props(ticker, item)]}, ensure_ascii=False),
            encoding="utf-8",
        )

        log.info("렌더 시작 %s (%dx%d) → %s", ticker, width, height, out_path.name)

        cmd = [
            "npx", "remotion", "render",
            "src/index.ts", composition,
            f"--props={props_path}",
            f"--output={out_path}",
            f"--width={width}",
            f"--height={height}",
            "--log=info",
        ]
        env = os.environ.copy()
        env["NODE_OPTIONS"] = "--max-old-space-size=8192"
        env.setdefault("DEBUG_FFMPEG_ARGS", "0")
        env["CONTACT_QR_PERSISTENT"] = "1" if config.CONTACT_QR_PERSISTENT else "0"

        result = subprocess.run(cmd, cwd=REMOTION_DIR, env=env, capture_output=True, text=True)
        if result.returncode == 0 and out_path.exists():
            size_mb = out_path.stat().st_size / (1024 * 1024)
            log.info("✔ 렌더 완료 %s (%.1fMB)", ticker, size_mb)
            rendered.append(out_path)
            item["video"] = str(out_path)
        else:
            log.error("✖ 렌더 실패 %s (rc=%s)\n%s", ticker, result.returncode, result.stderr[-2000:])

    return rendered
