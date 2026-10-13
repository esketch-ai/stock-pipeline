"""LLM 없이 장편 샘플 영상 만들기 — 저장된 대본 + TTS + 로컬 자막 + Remotion 렌더.

대본 생성(LLM)은 건너뛰고, 이미 저장된 대본으로 음성·자막·화면·렌더만 수행한다.
사용 방법:
    venv/bin/python tools/render_sample3.py 000650 001210 084670
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archive  # noqa: E402
import config  # noqa: E402
import facts as facts_mod  # noqa: E402
import investment_lenses  # noqa: E402
import stage2_long  # noqa: E402
import stage3_audio  # noqa: E402
import stage4_render  # noqa: E402
import stage5_publish  # noqa: E402
from logger import log  # noqa: E402
from screening import Candidate, last_trading_day  # noqa: E402


def _history(ticker: str):
    from pykrx import stock

    tday = last_trading_day(stock)
    end = datetime.strptime(tday, "%Y%m%d")
    return stock.get_market_ohlcv_by_date((end - timedelta(days=365)).strftime("%Y%m%d"), tday, ticker)


def _sections(ticker: str, text: str) -> list[dict]:
    """장편 대본을 7개 구간으로 나눈다.

    저장된 구간표(long_manifest)의 글자 수 비율을 문장 경계로 자른다.
    대본이 한 단락이어도 문장 단위로 끊으므로 구간이 비지 않는다.
    씬 시간 배분이 여기서 정해지므로 비우면 안 된다.
    """
    import re

    import script_long

    saved = {}
    manifest = config.DATA_DIR / "long_manifest.json"
    if manifest.exists():
        try:
            entry = json.loads(manifest.read_text(encoding="utf-8")).get(ticker) or {}
            saved = {s["id"]: s for s in entry.get("sections", [])}
        except (json.JSONDecodeError, KeyError, TypeError):
            saved = {}

    ids = [s[0] for s in script_long.SECTIONS]
    weights = {s[0]: (saved.get(s[0]) or {}).get("chars") or s[2] for s in script_long.SECTIONS}
    titles = {s[0]: (saved.get(s[0]) or {}).get("title") or s[1] for s in script_long.SECTIONS}

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    if not sentences:
        sentences = [text.strip()]

    total = sum(weights.values()) or 1
    # 각 구간이 차지할 문자 예산의 누적 경계 — 마지막 구간이 0이 되지 않도록 나눈다.
    bounds: list[int] = []
    running = 0
    for sid in ids:
        running += weights[sid]
        bounds.append(round(len(text) * running / total))

    bodies: list[list[str]] = [[] for _ in ids]
    used = 0
    position = 0
    for sentence in sentences:
        while position < len(ids) - 1 and used >= bounds[position]:
            position += 1
        bodies[position].append(sentence)
        used += len(sentence) + 1

    sections = [
        {"id": sid, "title": titles[sid], "text": " ".join(bodies[i]).strip(), "chars": len(" ".join(bodies[i]).strip())}
        for i, sid in enumerate(ids)
    ]
    empty = [s["id"] for s in sections if not s["text"]]
    if empty:
        raise RuntimeError(f"{ticker}: 구간이 비었습니다 {empty}")

    log.info("%s 구간 분할 — %s", ticker, ", ".join(f"{s['id']}:{s['chars']}" for s in sections))
    return sections


async def build_item(ticker: str, reserved: list[dict]) -> dict:
    import chart_data

    script_path = config.DATA_DIR / f"script_long_{ticker}.txt"
    if not script_path.exists():
        raise RuntimeError(f"{ticker}: 저장된 장편 대본이 없습니다 ({script_path})")
    text = script_path.read_text(encoding="utf-8")
    log.info("%s 대본 %d자", ticker, len(text))

    source = facts_mod.collect(ticker, ticker)
    name = source.get("name") or ticker
    cand = Candidate(
        ticker=ticker,
        name=name,
        market="KOSPI",
        close=float(source.get("close_raw") or 0.0),
        change_rate=float(source.get("change_raw") or 0.0),
        volume=int(source.get("volume") or 0),
        trading_value=int(source.get("trading_value") or 0),
        score=0.0,
        reason=f"저장 대본 재생성 ({source.get('trading_day')})",
    )

    audio = config.CACHE_DIR / ticker / "voice.mp3"
    # 음성은 대본 길이에 맞춰 매번 다시 합성한다 (저장본이 짧으면 7분이 되지 않는다).
    log.info("%s TTS 합성 (대본 %d자)", ticker, len(text))
    await stage2_long._tts_long(text, ticker)
    if not audio.exists():
        raise RuntimeError(f"{ticker}: TTS 결과 없음")

    log.info("%s 로컬 단어 타임스탬프 추출", ticker)
    words = stage3_audio.extract_word_timestamps(audio, script_text=text, company_name=name)
    if not words:
        raise RuntimeError(f"{ticker}: 자막 타임스탬프 추출 실패")

    hist = _history(ticker)
    series = chart_data.to_series(hist)

    # LLM 이 없으므로 편집 계획은 결정론적으로 배정한다. 대본 생성 관점과 같은 기준이다.
    plan = investment_lenses.allocate({**source, "ticker": ticker, "name": name}, reserved)

    return {
        "name": name,
        "audio": str(audio),
        "timestamps": words,
        "script": {"ticker": ticker, "name": name, "hook": "", "body": [], "closing": ""},
        "long_text": text,
        "facts": source,
        "series": series,
        "chart_paths": [],
        "candidate": {"change_rate": source.get("change_raw")},
        "editorial_plan": plan,
        "sections": _sections(ticker, text),
    }


def main() -> int:
    tickers = sys.argv[1:] or ["000650", "001210", "084670"]
    reserved: list[dict] = []
    manifest: dict[str, dict] = {}

    async def run_all():
        for ticker in tickers:
            manifest[ticker] = await build_item(ticker, reserved)

    asyncio.run(run_all())

    log.info("렌더 시작 — %d편", len(manifest))
    videos = stage4_render.render(manifest)
    results = stage5_publish.run_qc(videos)

    report = config.DATA_DIR / "sample3_render.json"
    report.write_text(json.dumps(archive._jsonable(results), ensure_ascii=False, indent=2), encoding="utf-8")
    for result in results:
        print(f"{'PASS' if result.ok else 'FAIL'} {result.path.name} {result.duration:.0f}초 {result.size_mb:.0f}MB", flush=True)
    return 0 if len(results) == len(manifest) and all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())