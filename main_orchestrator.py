"""5단계 야간 파이프라인 오케스트레이터.

  단계 1  종목 스크리닝 & 쿨다운 필터링 (pykrx)              약 2분
  단계 2  LLM 대본 비동기 생성 + 4K 투명 차트 렌더 (mplfinance) 약 4분
  단계 3  TTS 비동기 수신 + mlx-whisper 단어 타임스탬프 추출  약 6분
  단계 4  Remotion 하드웨어 가속 렌더링 (VideoToolbox)      약 40~50분
  단계 5  ffprobe QC + YouTube 예약 발행 + 7일 디스크 클린업  약 10분

사용법:
    python3 main_orchestrator.py            # 전체 실행
    python3 main_orchestrator.py --stage 1  # 특정 단계만
    python3 main_orchestrator.py --dry-run  # 렌더/게시 생략 (검증용)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime

import archive
import config
import screening
import stage2_script
import stage3_audio
import stage4_render
import stage5_publish
from config import DATA_DIR, STATE_DIR
from logger import log, stage


RUN_STATE = STATE_DIR / "run_state.json"


def _load_state() -> dict:
    if RUN_STATE.exists():
        try:
            return json.loads(RUN_STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _save_state(state: dict) -> None:
    RUN_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def run_pipeline(
    dry_run: bool = False,
    only_stage: int | None = None,
    no_publish: bool = False,
    tickers: list[str] | None = None,
) -> int:
    started = time.time()
    state = _load_state()
    state["started_at"] = datetime.now().isoformat(timespec="seconds")
    state["dry_run"] = dry_run

    def should_run(n: int) -> bool:
        return only_stage is None or only_stage == n

    log.info("=" * 62)
    log.info("stock-pipeline 시작 (%s) dry_run=%s", state["started_at"], dry_run)
    log.info("=" * 62)

    # ── 단계 1 ──
    candidates: list = []
    if should_run(1):
        with stage("단계1 · 종목 스크리닝 & 쿨다운 필터"):
            if tickers:
                candidates = screening.screen_by_tickers(tickers)
            else:
                candidates = screening.screen()
            state["candidates"] = [c.ticker for c in candidates]
    elif RUN_STATE.exists():
        candidates = [
            screening.Candidate(**c) for c in json.loads((STATE_DIR / "candidates.json").read_text(encoding="utf-8"))
        ]

    if not candidates:
        log.error("선정된 후보 종목이 없어 파이프라인을 종료합니다.")
        return 1

    # ── 단계 2 ──
    # VIDEO_DURATION=long 이면 섹션 기반 장편 대본을 사용한다.
    is_long = config.VIDEO_DURATION == "long"
    scripts: list = []
    if should_run(2):
        title = "단계2 · 장편 대본 생성 (7분 풀버전)" if is_long else "단계2 · LLM 대본 생성 + 4K 차트 렌더"
        with stage(title):
            if is_long:
                import stage2_long

                long_manifest = stage2_long.generate_long(candidates)
                # 검증에 막힌 항목은 audio 가 없다. 대본 목록에는 이름만 남긴다.
                blocked = [k for k, v in long_manifest.items() if v.get("blocked")]
                if blocked:
                    log.error("대본 검증으로 차단된 종목 %d개 — TTS/렌더 제외: %s",
                              len(blocked), ", ".join(blocked))
                scripts = [
                    stage2_script.Script(
                        ticker=k,
                        name=v.get("name", k),
                        hook=((v.get("script") or {}).get("hook") or ""),
                        body=[],
                        closing=((v.get("script") or {}).get("closing")
                                 or "이 영상은 투자 권유가 아니며, 투자 판단과 책임은 본인에게 있습니다."),
                    )
                    for k, v in long_manifest.items()
                ]
                # 차트는 장편 모드에서도 생성 (렌더 배경)
                for cand in candidates:
                    try:
                        for s in scripts:
                            if s.ticker == cand.ticker:
                                stage2_script.render_charts(cand, s)
                    except Exception as exc:
                        log.error("차트 렌더 실패 %s: %s", cand.ticker, exc)
            else:
                scripts = stage2_script.generate_scripts(candidates)
            state["scripts"] = [s.ticker for s in scripts]
    else:
        scripts_path = DATA_DIR / "scripts.json"
        if scripts_path.exists():
            scripts = [stage2_script.Script(**d) for d in json.loads(scripts_path.read_text(encoding="utf-8"))]

    if not scripts:
        log.error("생성된 대본이 없어 파이프라인을 종료합니다.")
        return 1

    # ── 단계 3 ──
    manifest: dict = {}
    if should_run(3):
        if is_long:
            with stage("단계3 · 장편 TTS + 단어 타임스탬프"):
                mf = DATA_DIR / "long_manifest.json"
                manifest = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
        else:
            with stage("단계3 · TTS + 단어 타임스탬프 추출"):
                manifest = stage3_audio.synthesize(scripts)
    else:
        name = "long_manifest.json" if is_long else "audio_manifest.json"
        mf = DATA_DIR / name
        if mf.exists():
            manifest = json.loads(mf.read_text(encoding="utf-8"))

    if not manifest:
        log.error("TTS 결과가 없어 파이프라인을 종료합니다.")
        return 1

    # ── 단계 4 ──
    videos: list = []
    if should_run(4):
        if dry_run:
            log.info("[dry-run] 단계4 Remotion 렌더 생략")
        else:
            with stage("단계4 · Remotion VideoToolbox 렌더링"):
                videos = stage4_render.render(manifest)
    else:
        videos = list(config.OUTPUT_DIR.glob("*.mp4"))

    if not videos and not dry_run:
        log.error("렌더링된 영상이 없어 파이프라인을 종료합니다.")
        return 1

    # ── 단계 5 ──
    qc_results: list = []
    published: dict[str, str] = {}
    if should_run(5):
        with stage("단계5 · QC + 게시 + 클린업"):
            if dry_run or not videos:
                log.info("[dry-run] 단계5 QC/게시 생략")
                qc_results = []
            elif no_publish:
                # 렌더·QC·아카이브까지만 하고 YouTube 는 올리지 않는다.
                log.info("[--no-publish] QC 만 수행, YouTube 게시 생략")
                qc_results = stage5_publish.run_qc(videos)
            else:
                qc_results = stage5_publish.run_qc(videos)
                published = stage5_publish.publish_all(qc_results, manifest)
                state["published"] = published
                if published:
                    screening.mark_published(list(published.keys()))
            stage5_publish.cleanup()

    elapsed = time.time() - started
    state["finished_at"] = datetime.now().isoformat(timespec="seconds")
    state["elapsed_sec"] = round(elapsed, 1)
    _save_state(state)

    # ── 이력 아카이브 (대시보드용) ──
    try:
        archive.write_run(
            run_state=state,
            candidates=candidates,
            scripts=scripts,
            manifest=manifest,
            qc_results=qc_results,
            published=published,
        )
    except Exception as exc:
        log.error("아카이브 실패(무시): %s", exc)

    log.info("=" * 62)
    log.info("파이프라인 종료 — 총 %.1f분 소요", elapsed / 60)
    log.info("=" * 62)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="stock-pipeline 5단계 야간 오케스트레이터")
    parser.add_argument("--stage", type=int, choices=[1, 2, 3, 4, 5], help="특정 단계만 실행")
    parser.add_argument("--dry-run", action="store_true", help="렌더/게시 생략 (파이프라인 검증용)")
    parser.add_argument(
        "--no-publish",
        action="store_true",
        help="QC·아카이브까지만 수행하고 YouTube 게시는 하지 않는다",
    )
    parser.add_argument(
        "--tickers",
        type=str,
        help="스크리닝 대신 지정 종목으로 실행 (쉼표 구분, 예: 000650,001210)",
    )
    args = parser.parse_args()
    tickers = [t for t in (args.tickers or "").split(",") if t.strip()] or None

    try:
        return run_pipeline(
            dry_run=args.dry_run,
            only_stage=args.stage,
            no_publish=args.no_publish,
            tickers=tickers,
        )
    except KeyboardInterrupt:
        log.error("사용자에 의해 중단되었습니다.")
        return 130
    except Exception as exc:
        log.exception("파이프라인 치명적 오류")
        # 실패도 대시보드에서 확인되도록 아카이브에 남긴다.
        try:
            state = _load_state()
            state["started_at"] = state.get("started_at") or datetime.now().isoformat(timespec="seconds")
            state["dry_run"] = args.dry_run
            archive.write_run(run_state=state, error=f"{type(exc).__name__}: {exc}")
        except Exception as arch_exc:
            log.error("실패 아카이브도 실패: %s", arch_exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())