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

    1차 우선: 네이버 증권(stock.naver.com) 서비스 정보
    2차 폴백: pykrx
    """
    facts: dict = {
        "ticker": ticker, "name": name, "market": market,
        "news": [], "history_days": history_days,
        "researches": [],
    }

    # 1. 네이버 증권 서비스 API 우선 수집
    try:
        import naver_finance
        integ = naver_finance.fetch_stock_integration(ticker)
        if integ and integ.get("name"):
            facts["name"] = integ["name"]
            info = integ.get("info", {})
            if "시총" in info:
                facts["market_cap"] = info["시총"]
            if "현재가" in info:
                facts["close"] = info["현재가"]
                try:
                    facts["close_raw"] = float(info["현재가"].replace(",", ""))
                except Exception:
                    pass
            if "52주 최고" in info:
                facts["high_52w"] = info["52주 최고"]
                try:
                    hi = float(info["52주 최고"].replace(",", ""))
                    cur = facts.get("close_raw", 0.0)
                    if hi > 0 and cur > 0:
                        facts["from_high"] = f"{(cur / hi - 1) * 100:.1f}%"
                except Exception:
                    pass
            if "52주 최저" in info:
                facts["low_52w"] = info["52주 최저"]
                try:
                    lo = float(info["52주 최저"].replace(",", ""))
                    hi = float(info["52주 최고"].replace(",", ""))
                    cur = facts.get("close_raw", 0.0)
                    if hi > lo and cur >= lo:
                        pos = (cur - lo) / (hi - lo) * 100
                        facts["range_pos"] = f"{pos:.0f}%"
                except Exception:
                    pass
            if "대금" in info:
                facts["trading_value"] = info["대금"]
            if "PER" in info:
                facts["per"] = info["PER"]
            if "PBR" in info:
                facts["pbr"] = info["PBR"]

            consensus = integ.get("consensus", {})
            if consensus.get("target_price"):
                facts["target_price"] = consensus["target_price"]
            if consensus.get("opinion"):
                facts["consensus_opinion"] = consensus["opinion"]

            if integ.get("researches"):
                facts["researches"] = [f"{r['broker']}: {r['title']}" for r in integ["researches"][:3]]

            # 최신 뉴스 수집
            news_items = naver_finance.fetch_news_naver(ticker, limit=4)
            if news_items:
                facts["news"] = [n["title"] for n in news_items]
                log.debug("%s 네이버 뉴스 %d건 수집", ticker, len(facts["news"]))

            # 4. 네이버 보조지표: 매물대 분석도 (Volume Profile)
            ohlcv = naver_finance.fetch_ohlcv_naver(ticker, count=180)
            if ohlcv:
                vp = naver_finance.calculate_volume_profile(ohlcv)
                if vp:
                    facts["volume_profile"] = vp
                    facts["poc_price"] = vp.get("poc_price")
                    facts["is_above_poc"] = vp.get("is_above_poc")

            return facts
    except Exception as exc:
        log.debug("네이버 팩트 수집 실패 %s: %s", ticker, exc)

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
        ("target_price", "증권사 평균 목표주가"),
        ("per", "PER"),
        ("pbr", "PBR"),
    ]:
        if facts.get(key):
            lines.append(f"- {label}: {facts[key]}")
    vp = facts.get("volume_profile")
    if vp:
        poc_p = vp.get("poc_price", 0)
        poc_pct = vp.get("poc_pct", 0)
        is_above = "상향 돌파(지지선 전환)" if vp.get("is_above_poc") else "하회(상단 매물벽 저항)"
        lines.append(f"- 네이버 증권 매물 분석도: 최대 거래량 매물대 {poc_p:,.0f}원 (누적 {poc_pct}%), 현재 위치 {is_above}")
    if facts.get("researches"):
        lines.append("- 증권사 최신 리포트 및 투자 의견:")
        lines.extend(f"  · {r}" for r in facts["researches"][:3])
    if facts.get("news"):
        lines.append("- 최근 뉴스 헤드라인(참고용, 사실 확인된 것 아님):")
        lines.extend(f"  · {n}" for n in facts["news"][:4])
    return "\n".join(lines)