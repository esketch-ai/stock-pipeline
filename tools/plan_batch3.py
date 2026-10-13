"""신규 종목 3편 사전 준비 — 스크리닝 + 종목별 시나리오 설계.

LLM 을 호출하지 않는다. 대본 본문(TTS 직전)까지만 만들어 두고,
할당량이 복구되면 이어서 생성·합성·렌더한다.

사용 방법:
    venv/bin/python tools/plan_batch3.py            # 3종목 자동 선정
    venv/bin/python tools/plan_batch3.py 011330 088790
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
import editorial  # noqa: E402
import facts as facts_mod  # noqa: E402
import investment_lenses  # noqa: E402
import screening  # noqa: E402
from logger import log  # noqa: E402
from video_files import video_ticker  # noqa: E402

BATCH_SIZE = 3


def already_produced() -> set[str]:
    """output/ 에 이미 영상이 있는 종목 — 중복选题을 피한다."""
    done = set()
    for path in config.OUTPUT_DIR.glob("*.mp4"):
        done.add(video_ticker(path))
    return done


def select_new() -> list[screening.Candidate]:
    """오늘 스크리닝 결과에서 아직 영상이 없는 종목을 고른다."""
    produced = already_produced()
    picked: list[screening.Candidate] = []
    for _ in range(4):
        # 상위 후보를 넉넉히 받아 이미 제작한 종목을 제외한 뒤 3개를 고른다.
        candidates = screening.screen(count=40)
        picked = [c for c in candidates if c.ticker not in produced][:BATCH_SIZE]
        if len(picked) >= BATCH_SIZE:
            break
    if len(picked) < BATCH_SIZE:
        raise RuntimeError(
            f"신규 종목을 {BATCH_SIZE}개 고르지 못했습니다 (제외 {len(produced)}종목). "
            "DAILY_VIDEO_COUNT 를 늘리거나 쿨다운을 확인하세요."
        )
    log.info("제외된 기존 종목 %d개 · 신규 선정 %d개", len(produced), len(picked))
    return picked


def history(ticker: str):
    from pykrx import stock

    tday = screening.last_trading_day(stock)
    end = datetime.strptime(tday, "%Y%m%d")
    return stock.get_market_ohlcv_by_date((end - timedelta(days=365)).strftime("%Y%m%d"), tday, ticker)


def main() -> int:
    requested = [t.strip() for t in sys.argv[1:] if t.strip()]
    candidates = (
        [screening.screen_by_tickers(requested)[i] for i in range(len(requested))]
        if requested
        else select_new()
    )

    import chart_data

    reserved: list[dict] = []
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = config.DATA_DIR / "editorial_review" / stamp
    out.mkdir(parents=True, exist_ok=True)

    plans = []
    for cand in candidates:
        source = facts_mod.collect(cand.ticker, cand.name, cand.market)
        name = source.get("name") or cand.name
        plan = investment_lenses.allocate({**source, "ticker": cand.ticker, "name": name}, reserved)
        plan["outline"] = None  # LLM 호출 시점에 채워진다
        series = chart_data.to_series(history(cand.ticker))
        brief = editorial.stock_brief(source, cand.reason)
        record = {
            "ticker": cand.ticker,
            "name": name,
            "reason": cand.reason,
            "editorial_plan": plan,
            "facts": source,
            "series_points": len(series.get("c") or []),
            "brief": brief,
            "status": "대본 생성 대기 (LLM 할당량)",
        }
        plans.append(record)
        (out / f"PLAN_{cand.ticker}_{name}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"{cand.ticker} {name} · {plan['investor']} 관점 · {plan['structure_id']} 전개 · {plan['question'][:60]}", flush=True)

    md = ["# 신규 3편 사전 준비", "", f"작성 {datetime.now().isoformat(timespec='seconds')}", ""]
    for record in plans:
        md += [
            f"## {record['ticker']} {record['name']}",
            f"- 관점: {record['editorial_plan']['investor']} — {record['editorial_plan']['principle']}",
            f"- 전개: {record['editorial_plan']['structure']}",
            f"- 중심 질문: {record['editorial_plan']['question']}",
            f"- 기술 관찰: {record['reason']}",
            f"- 차트 봉 수: {record['series_points']}",
            "",
        ]
    (out / "PLAN.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\n계획 저장: {out}", flush=True)
    print("다음 단계(대본 본문)는 LLM 할당량 복구 후 실행합니다.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())