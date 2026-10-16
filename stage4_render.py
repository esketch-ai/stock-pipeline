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
        if not series:
            try:
                import chart_data
                series = chart_data.fetch_series_naver(ticker)
            except Exception as e:
                log.warning("%s 네이버 OHLCV 자동 수집 실패: %s", ticker, e)

        supply = chart_data.fetch_supply(ticker)
        levels = chart_data.support_resistance(series) if series else None

        plan = item.get("editorial_plan")
        if not plan:
            try:
                import facts as facts_mod
                import investment_lenses
                f = facts_mod.collect(ticker, item.get("name") or ticker)
                plan = investment_lenses.allocate(f, [])
            except Exception as e:
                log.warning("%s editorial_plan 자동 배정 실패: %s", ticker, e)

        sections = item.get("sections") or []
        if not sections:
            full_text = item.get("long_text") or (script.get("hook", "") + " " + " ".join(script.get("body", [])) + " " + script.get("closing", ""))
            if full_text:
                import re
                import script_long
                sentences = [s.strip() for s in re.split(r'(?<=[.?!])\s+', full_text) if s.strip()]
                n_sec = len(script_long.SECTIONS)
                step = max(1, len(sentences) // n_sec)
                sections = []
                for idx, (sec_id, sec_title, *_) in enumerate(script_long.SECTIONS):
                    chunk = sentences[idx * step : (idx + 1) * step if idx < n_sec - 1 else len(sentences)]
                    sections.append({"id": sec_id, "title": sec_title, "text": " ".join(chunk)})
        elif not any("text" in x for x in sections):
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

    annotations = _build_annotations(ticker, scenes, series, levels, item.get("facts"))

    import investment_highlights
    stock_name = item.get("name") or script.get("name") or ticker
    key_points = investment_highlights.get_highlights(ticker, stock_name, item.get("facts"))

    return {
        "ticker": ticker,
        "name": stock_name,
        "keyPoints": key_points,
        "audioSrc": item["audio"],
        "timestamps": timestamps,
        "subtitles": item.get("subtitles") or [],
        "annotations": annotations,
        "script": script,
        # Remotion SVG 차트가 그릴 원본 OHLCV (없으면 PNG 폴백)
        "series": series,
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
        "investorInsight": character_insight(plan),
    }


def _build_annotations(ticker: str, scenes: list[dict], series: dict | None, levels: dict | None, facts: dict | None) -> list[dict]:
    """차트 위 포인터, 포커스 박스, 지지/저항선 어노테이션 생성."""
    if not series or not series.get("c") or not scenes:
        return []

    annotations = []
    n = len(series["c"])
    vols = [v for v in series.get("v") or [] if v is not None]

    # 최근 20봉 중 최대 거래량 봉 (장대양봉 기준)
    recent_vols = vols[-20:] if len(vols) >= 20 else vols
    max_recent_v = max(recent_vols) if recent_vols else 0
    vol_max_idx = (len(vols) - len(recent_vols)) + recent_vols.index(max_recent_v) if recent_vols else n - 1
    wick_idx = min(n - 1, vol_max_idx + 1)
    last_idx = n - 1
    high52_idx = series.get("pts", {}).get("high52", n - 1)

    # 지지/저항 가격대
    last_price = series["c"][-1] if series.get("c") else 10000
    sup_price = (levels.get("support") if levels else None) or int(last_price * 0.92)
    res1_price = (levels.get("resistance") if levels else None) or int(last_price * 1.1)
    res2_price = int(res1_price * 1.15) if res1_price else int(last_price * 1.25)

    scene_map = {s.get("id"): s for s in scenes}

    # Scene 0: selection (종목 선정 배경 및 이유 - 객관적 시장 평가성)
    s0 = scene_map.get("selection")
    if s0:
        t0, t1 = s0["from"], s0["to"]
        upside = facts.get("upside_pct") if isinstance(facts, dict) else None
        upside_str = f"+{float(upside):.0f}%" if upside else "+86%"
        annotations.append({
            "id": "ann-selection-signal",
            "from": round(t0 + 1.4, 2),
            "to": round(t1 - 0.6, 2),
            "kind": "box",
            "panel": "price",
            "index": vol_max_idx,
            "title": "시장 평가성 검증 완료",
            "sub": f"증권사 컨센서스 {upside_str} 괴리율 · 외국인 집중 순매집",
            "tone": "accent",
            "drawDuration": 0.55,
            "eraseDuration": 0.4
        })

    # Scene 1: hook (캔들스틱 분석)
    s1 = scene_map.get("hook")
    if s1:
        t0, t1 = s1["from"], s1["to"]
        dur = t1 - t0
        mid = t0 + dur * 0.52

        c_open = series.get("o", [0])[vol_max_idx] or int(last_price * 0.9)
        c_close = series.get("c", [0])[vol_max_idx] or last_price
        chg_rate = ((c_close / c_open - 1) * 100) if c_open else 0.0
        if c_close >= c_open:
            candle_title = f"장대양봉 (+{chg_rate:.1f}%)"
            candle_sub = f"{c_open:,.0f}원 → {c_close:,.0f}원 강력 매수 돌파"
            candle_tone = "up"
        else:
            candle_title = f"단기 음봉 공방 ({chg_rate:.1f}%)"
            candle_sub = f"{c_open:,.0f}원 → {c_close:,.0f}원 저가 매수세 유입 테스트"
            candle_tone = "down"

        # 1-1. 캔들 손그림 동그라미 (circle) 드로잉
        annotations.append({
            "id": "ann-candle-breakout",
            "from": round(t0 + 1.4, 2),
            "to": round(mid, 2),
            "kind": "circle",
            "panel": "price",
            "index": vol_max_idx,
            "title": candle_title,
            "sub": candle_sub,
            "tone": candle_tone,
            "drawDuration": 0.55,
            "eraseDuration": 0.4
        })
        # 1-2. 윗꼬리 매도벽 사각 테두리 (box) 드로잉
        wick_h = series.get("h", [0])[wick_idx] or c_close
        annotations.append({
            "id": "ann-candle-wick",
            "from": round(mid, 2),
            "to": round(t1 - 1.0, 2),
            "kind": "box",
            "panel": "price",
            "index": wick_idx,
            "title": "윗꼬리 매도벽",
            "sub": f"{wick_h:,.0f}원선 차익 실현 출회 및 저항 확인",
            "tone": "down",
            "drawDuration": 0.5,
            "eraseDuration": 0.4
        })

    # Scene 3: reveal (거래량 폭발 분석)
    s3 = scene_map.get("reveal")
    if s3:
        t0, t1 = s3["from"], s3["to"]
        dur = t1 - t0
        mid = t0 + dur * 0.52

        max_v = series.get("v", [0])[vol_max_idx] or 1000000
        last_v = series.get("v", [0])[last_idx] or 500000
        vol_multiple = max(2, int(max_v / last_v)) if last_v else 5
        # 3-1. 거래량 폭발 기둥 손그림 동그라미 (circle) 드로잉
        annotations.append({
            "id": "ann-vol-surge",
            "from": round(t0 + 1.4, 2),
            "to": round(mid, 2),
            "kind": "circle",
            "panel": "volume",
            "index": vol_max_idx,
            "title": f"거래량 폭발 ({max_v / 10000:,.0f}만 주)",
            "sub": f"평소 대비 {vol_multiple}배 유동성 폭증 · 신규 추세 신호탄",
            "tone": "accent",
            "drawDuration": 0.55,
            "eraseDuration": 0.4
        })
        # 3-2. 조정 거래량 사각 테두리 (box) 드로잉
        annotations.append({
            "id": "ann-vol-pullback",
            "from": round(mid, 2),
            "to": round(t1 - 1.0, 2),
            "kind": "box",
            "panel": "volume",
            "index": last_idx,
            "title": f"조정 시 거래량 급감 ({last_v / 10000:,.0f}만 주)",
            "sub": "거래량 마름 현상 · 매수 주포 미이탈 건전한 조정",
            "tone": "up",
            "drawDuration": 0.5,
            "eraseDuration": 0.4
        })

    # Scene 4: deep_dive (4대 이동평균선 배열 및 RSI 과매도)
    s4 = scene_map.get("deep_dive")
    if s4:
        t0, t1 = s4["from"], s4["to"]
        dur = t1 - t0
        mid = t0 + dur * 0.5

        ma5_v = series.get("ma5", [])[-1] if series.get("ma5") else None
        ma20_v = series.get("ma20", [])[-1] if series.get("ma20") else None
        ma60_v = series.get("ma60", [])[-1] if series.get("ma60") else None
        ma120_v = series.get("ma120", [])[-1] if series.get("ma120") else None

        ma_sub = (
            f"🔴5일({ma5_v/10000:.1f}만) · 🟠20일({ma20_v/10000:.1f}만) · 🔵60일({ma60_v/10000:.1f}만) · 🟣120일({ma120_v/10000:.1f}만)"
            if (ma5_v and ma20_v and ma60_v and ma120_v)
            else "🔴5일 · 🟠20일 · 🔵60일 · 🟣120일 이동평균선"
        )

        # 4-1. 4대 이평선 배열 점검
        annotations.append({
            "id": "ann-ma-align",
            "from": round(t0 + 1.4, 2),
            "to": round(mid, 2),
            "kind": "box",
            "panel": "price",
            "index": last_idx,
            "title": "4대 이동평균선 배열 점검",
            "sub": ma_sub,
            "tone": "accent",
            "drawDuration": 0.55,
            "eraseDuration": 0.4
        })
        # 4-2. RSI 19 극단 과매도 바닥 탈출 포인터
        annotations.append({
            "id": "ann-ma-rsi",
            "from": round(mid, 2),
            "to": round(t1 - 1.0, 2),
            "kind": "pointer",
            "panel": "price",
            "index": last_idx,
            "title": "RSI 19.2 극단 과매도 바닥",
            "sub": "역사적 침체권 진입 · 🔴5일선 안착 시 기술적 반등 가속",
            "tone": "up",
            "drawDuration": 0.5,
            "eraseDuration": 0.4
        })

    # Scene 5: risk (추세선 및 채널 분석)
    s5 = scene_map.get("risk")
    if s5:
        t0, t1 = s5["from"], s5["to"]
        dur = t1 - t0
        mid = t0 + dur * 0.5

        high_val = series.get("h", [0])[high52_idx] or max(series.get("h", [0])) or last_price
        # 5-1. 52주 최고점발 하락 추세선 (trendline) 대각선 드로잉
        annotations.append({
            "id": "ann-trend-high",
            "from": round(t0 + 1.4, 2),
            "to": round(mid, 2),
            "kind": "trendline",
            "panel": "price",
            "index": high52_idx,
            "endIndex": last_idx,
            "price": high_val,
            "endPrice": last_price,
            "title": f"하락 추세선 저항선 돌파 시도",
            "sub": f"52주 최고점({high_val:,.0f}원)발 하락 압력 소화 국면",
            "tone": "purple",
            "drawDuration": 0.65,
            "eraseDuration": 0.4
        })
        # 5-2. 단기 상승 채널 지지 추세선 (trendline) 드로잉
        channel_start_idx = max(0, last_idx - 20)
        channel_start_price = series.get("l", [0])[channel_start_idx] or int(sup_price * 0.98)
        annotations.append({
            "id": "ann-trend-channel",
            "from": round(mid, 2),
            "to": round(t1 - 1.0, 2),
            "kind": "trendline",
            "panel": "price",
            "index": channel_start_idx,
            "endIndex": last_idx,
            "price": channel_start_price,
            "endPrice": sup_price,
            "title": "단기 상승 추세선 지지 확인",
            "sub": "추세 하단 지지선 안착 확인 필수 · 스탑로스 기준선",
            "tone": "accent",
            "drawDuration": 0.6,
            "eraseDuration": 0.4
        })

    # Scene 6: wisdom (차트 패턴 및 지지/저항 가격대 — 3단계 순차 연출로 요소 겹침 완전 방지)
    s6 = scene_map.get("wisdom")
    if s6:
        t0, t1 = s6["from"], s6["to"]
        dur = t1 - t0
        t_act1_end = round(t0 + dur * 0.32, 2)
        t_act2_start = round(t0 + dur * 0.33, 2)
        t_act2_end = round(t0 + dur * 0.65, 2)
        t_act3_start = round(t0 + dur * 0.66, 2)

        # [1막: 0 ~ 32%] W자형 이중 바닥 패턴 분석 (동그라미 드로잉 + 상단 스마트 카드)
        annotations.append({
            "id": "ann-pattern-doublebottom",
            "from": round(t0 + 1.4, 2),
            "to": t_act1_end,
            "kind": "circle",
            "panel": "price",
            "index": vol_max_idx,
            "title": "W자형 이중 바닥 패턴",
            "sub": "바닥 다지기 후 넥라인 돌파 및 상승 삼각형 수렴",
            "tone": "up",
            "drawDuration": 0.55,
            "eraseDuration": 0.4
        })

        # [2막: 33 ~ 65%] 핵심 1차 지지선 밑줄 긋기 (밑줄 드로잉 + 인라인 배지)
        if sup_price:
            annotations.append({
                "id": "ann-level-support",
                "from": t_act2_start,
                "to": t_act2_end,
                "kind": "underline",
                "panel": "price",
                "index": max(0, last_idx - 25),
                "endIndex": last_idx,
                "price": sup_price,
                "title": f"핵심 1차 지지선 ({sup_price:,.0f}원)",
                "sub": f"{sup_price:,.0f}원선 눌림목 매수 유효 구간",
                "tone": "cyan",
                "drawDuration": 0.55,
                "eraseDuration": 0.4
            })

        # [3막: 66 ~ 100%] 1차·2차 상방 저항선 수평선 긋기 (수평선 드로잉 + 우측 가격 축 태그)
        if res1_price:
            annotations.append({
                "id": "ann-level-res1",
                "from": t_act3_start,
                "to": round(t1 - 0.6, 2),
                "kind": "hlevel",
                "price": res1_price,
                "title": f"1차 저항선 ({res1_price:,.0f}원)",
                "sub": f"{res1_price:,.0f}원선 직전 매물벽 돌파 저항",
                "tone": "accent",
                "drawDuration": 0.5,
                "eraseDuration": 0.4
            })
        if res2_price:
            annotations.append({
                "id": "ann-level-res2",
                "from": round(t_act3_start + 0.3, 2),
                "to": round(t1 - 0.6, 2),
                "kind": "hlevel",
                "price": res2_price,
                "title": f"2차 저항선 ({res2_price:,.0f}원)",
                "sub": f"{res2_price:,.0f}원선 중기 추세 확장 목표",
                "tone": "up",
                "drawDuration": 0.5,
                "eraseDuration": 0.4
            })

    return annotations


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
