"""대본 작성용 팩트 수집기.

LLM 은 숫자를 지어내거나 없는 공시/테마를 만들어내는 경향이 강하다.
따라서 "사실"은 전부 코드가 KRX/DART 에서 직접 조회해 넘기고,
LLM 은 그 사실을 해석하고 표현하는 역할만 맡긴다.

수집 항목:
  * 시가총액 / 업종 / 상장일
  * 52주 신고가·저가, 현재가 위치
  * 거래대금 추이, 외국인/기관 순매수 (가용 시)
  * 뉴스 헤드라인 (네이버 금융 RSS — 실패해도 무시)
"""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from config import DAILY_VIDEO_COUNT  # noqa: F401  (config 로딩 부수효과)
from logger import log


def _fmt_int(v) -> str:
    """1234567890 -> '12억 3,456만' 처럼 읽기 좋게.

    소수점은 버린다 (대본 표기 규칙: 1100.32억 -> 1100억).
    단위 뒤에 '원' 을 붙이지 않는다. 대본이 '억'/'원' 을 직접 다루므로
    표시값은 숫자+단위만 둔다 (cues._fmt_variants 파싱과 맞물린다).
    """
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "-"
    if v >= 1e12:
        return f"{int(round(v / 1e12))}조"
    if v >= 1e8:
        return f"{int(round(v / 1e8))}억"
    # 1억 미만(주가 등)은 '만' 단위로 바꾸지 않는다 — 37,200원을 '4만' 으로 부르면 오독이다
    return f"{int(v):,}"


def _fmt_price(v) -> str:
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return "-"


def _safe(fn, default=None, label=""):
    """개별 조회 실패가 전체를 죽이지 않게 한다."""
    try:
        return fn()
    except Exception as exc:
        log.debug("팩트 조회 실패 %s: %s", label or getattr(fn, "__name__", "?"), exc)
        return default


def _naver_news(ticker: str, name: str, limit: int = 4) -> list[str]:
    """네이버 금융 뉴스 RSS — 조회 실패 시 빈 목록 (파이프라인 영향 없음)."""
    try:
        query = urllib.parse.quote(f"{name} 주가")
        url = f"https://news.naver.com/rss/search.naver?query={query}&sort=1&where=news"
        import httpx

        r = httpx.get(url, timeout=8, follow_redirects=True)
        root = ET.fromstring(r.text.encode("utf-8", "ignore"))
        out = []
        for item in root.findall(".//item")[:limit]:
            title = (item.findtext("title") or "").strip()
            title = re.sub(r"\[.*?\]", "", title).strip()
            if title:
                out.append(title)
        return out
    except Exception:
        return []


HISTORY_DAYS = 365  # 차트와 대본이 같은 기간을 보도록 고정


def _fetch_history(stock, ticker: str, end_date: str, days: int = HISTORY_DAYS):
    """조정가 OHLCV 단일 소스.

    get_market_ohlcv_by_ticker 에는 adjusted 개념이 없고(미조정가),
    get_market_ohlcv_by_date 는 adjusted=True(조정가) 다. 두 값을 섞으면
    대본 수치와 차트 축이 어긋난다. by_date 만 사용한다.
    """
    end = datetime.strptime(end_date, "%Y%m%d")
    start = (end - timedelta(days=days)).strftime("%Y%m%d")
    return stock.get_market_ohlcv_by_date(start, end_date, ticker)


def collect(ticker: str, name: str, market: str = "KOSPI", hist=None,
            history_days: int = HISTORY_DAYS) -> dict:
    """대본 프롬프트에 주입할 팩트 묶음.

    모든 가격은 차트와 동일한 기간 / 동일한 adjusted 기준에서 가져온다.
    """
    from pykrx import stock

    facts: dict = {
        "ticker": ticker, "name": name, "market": market,
        "news": [], "history_days": history_days,
    }

    basic = _safe(lambda: stock.get_market_ticker_name(ticker), label="name")
    if basic:
        facts["name"] = basic

    tday = _safe(
        lambda: stock.get_nearest_business_day_in_a_week(
            datetime.now().strftime("%Y%m%d"), prev=True),
        label="trading_day")
    facts["trading_day"] = tday

    # 차트와 동일한 기간/동일한 adjusted 기준의 시세
    series = hist if (hist is not None and len(hist)) else _safe(
        lambda: _fetch_history(stock, ticker, tday, history_days), label="history")

    if series is not None and len(series):
        last = series.iloc[-1]
        cur = float(last["종가"])
        facts["close"] = _fmt_price(cur)
        facts["close_raw"] = cur
        if len(series) > 1:
            prev_close = float(series["종가"].iloc[-2])
            chg = (cur / prev_close - 1) * 100 if prev_close else 0.0
            facts["change_rate"] = f"{chg:+.2f}%"
            facts["change_raw"] = chg
        hi = float(series["고가"].max())
        lo = float(series["저가"].min())
        pos = (cur - lo) / (hi - lo) * 100 if hi > lo else 50
        facts["high_52w"] = _fmt_price(hi)
        facts["low_52w"] = _fmt_price(lo)
        facts["range_pos"] = f"{pos:.0f}%"
        facts["from_high"] = f"{(cur / hi - 1) * 100:.1f}%"
        facts["range_days"] = len(series)

    snap = _safe(
        lambda: stock.get_market_ohlcv_by_ticker(tday, market=market), label="snapshot")
    if snap is not None and ticker in snap.index and len(snap):
        facts["market_cap"] = _fmt_int(snap.loc[ticker].get("시가총액"))

    facts["news"] = _naver_news(ticker, name)
    if facts["news"]:
        log.debug("%s 뉴스 %d건 수집", ticker, len(facts["news"]))
    return facts


def format_facts(facts: dict) -> str:
    """LLM 프롬프트에 넣을 한국어 팩트 블록."""
    lines = [f"- 종목코드: {facts.get('ticker')} ({facts.get('name')})"]
    for key, label in [
        ("market_cap", "시가총액"),
        ("close", "현재가"),
        ("change_rate", "등락률"),
        ("trading_value", "거래대금"),
        ("high_52w", "52주 신고가"),
        ("low_52w", "52주 저가"),
        ("range_pos", "52주 레인지 내 현재 위치"),
        ("from_high", "신고가 대비"),
    ]:
        if facts.get(key):
            lines.append(f"- {label}: {facts[key]}")
    if facts.get("news"):
        lines.append("- 최근 뉴스 헤드라인(참고용, 사실 확인된 것 아님):")
        lines.extend(f"  · {n}" for n in facts["news"][:4])
    return "\n".join(lines)