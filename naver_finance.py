"""네이버 증권(stock.naver.com) 서비스 정보 수집 모듈.

pykrx / KRX 스크래핑 의존성을 완전히 대체하여
네이버 증권 공식 서비스 API로부터 다음 정보를 고속 수집합니다:
  1. OHLCV 캔들스틱 시세 (siseJson / chart API)
  2. 일자별 투자자 매매동향 (기관 / 외국인 / 개인 순매수)
  3. 종목 기본 정보 (현재가, 등락률, 시가총액, 52주 최고/최저, PER, PBR 등)
  4. 증권사 컨센서스 (목표주가 평균, 투자의견)
  5. 최신 증권사 분석 리포트
  6. 최신 뉴스 헤드라인 및 요약
"""

from __future__ import annotations

import ast
import json
import ssl
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from logger import log

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://stock.naver.com/",
}

_SSL_CTX = ssl._create_unverified_context()


def _request_get(url: str, timeout: int = 10) -> Optional[str]:
    """네이버 API에 HTTP GET 요청을 보내고 텍스트를 반환한다."""
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace").strip()
    except Exception as exc:
        log.debug("네이버 API 요청 실패 (%s): %s", url, exc)
        return None


def _request_json(url: str, timeout: int = 10) -> Optional[Any]:
    """네이버 API에 HTTP GET 요청을 보내고 JSON 객체를 반환한다."""
    raw = _request_get(url, timeout=timeout)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception as exc:
        log.debug("네이버 JSON 파싱 실패 (%s): %s", url, exc)
        return None


# ─────────────────────────────────────────────────────────────
# 1. 차트 캔들 데이터 (OHLCV)
# ─────────────────────────────────────────────────────────────


def fetch_ohlcv_naver(ticker: str, count: int = 180) -> Optional[Dict[str, List[Any]]]:
    """네이버 증권 시세 API로 일별 OHLCV 캔들 데이터를 수집한다.

    반환:
        {
            "d": ["2026-04-01", ...], # 날짜 ISO
            "o": [179000.0, ...],      # 시가
            "h": [190800.0, ...],      # 고가
            "l": [178000.0, ...],      # 저가
            "c": [189600.0, ...],      # 종가
            "v": [32390251.0, ...],    # 거래량
            "foreign_rate": [48.43, ...] # 외인소진율
        }
    """
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=int(count * 1.8))
    start_str = start_dt.strftime("%Y%m%d")
    end_str = end_dt.strftime("%Y%m%d")

    url = (
        f"https://api.finance.naver.com/siseJson.naver?"
        f"symbol={ticker}&requestType=1&startTime={start_str}&endTime={end_str}&timeframe=day"
    )
    raw = _request_get(url)

    rows: List[List[Any]] = []
    if raw:
        try:
            # siseJson 은 JS 배열 형식
            rows = ast.literal_eval(raw)
        except Exception as exc:
            log.debug("%s siseJson literal_eval 실패: %s", ticker, exc)

    # 폴백: api.stock.naver.com dayCandle
    if not rows or len(rows) < 2:
        fallback_url = f"https://api.stock.naver.com/chart/domestic/item/{ticker}?periodType=dayCandle"
        data = _request_json(fallback_url)
        if data and "priceInfos" in data:
            price_infos = data["priceInfos"]
            dates, opens, highs, lows, closes, vols, frates = [], [], [], [], [], [], []
            for item in price_infos:
                raw_d = str(item.get("localDate", ""))
                if len(raw_d) == 8:
                    iso_d = f"{raw_d[:4]}-{raw_d[4:6]}-{raw_d[6:]}"
                else:
                    iso_d = raw_d
                dates.append(iso_d)
                opens.append(float(item.get("openPrice", 0)))
                highs.append(float(item.get("highPrice", 0)))
                lows.append(float(item.get("lowPrice", 0)))
                closes.append(float(item.get("closePrice", 0)))
                vols.append(float(item.get("accumulatedTradingVolume", 0)))
                frates.append(float(item.get("foreignRetentionRate", 0)))

            if len(dates) > count:
                dates = dates[-count:]
                opens = opens[-count:]
                highs = highs[-count:]
                lows = lows[-count:]
                closes = closes[-count:]
                vols = vols[-count:]
                frates = frates[-count:]

            return {
                "d": dates,
                "o": opens,
                "h": highs,
                "l": lows,
                "c": closes,
                "v": vols,
                "foreign_rate": frates,
            }
        return None

    # 헤더 제외
    data_rows = rows[1:] if len(rows) > 1 else []
    if not data_rows:
        return None

    # 최근 count 봉만 유지
    if len(data_rows) > count:
        data_rows = data_rows[-count:]

    dates, opens, highs, lows, closes, vols, frates = [], [], [], [], [], [], []
    for r in data_rows:
        if len(r) < 6:
            continue
        raw_d = str(r[0]).strip().replace('"', "").replace("'", "")
        if len(raw_d) == 8:
            iso_d = f"{raw_d[:4]}-{raw_d[4:6]}-{raw_d[6:]}"
        else:
            iso_d = raw_d

        try:
            o_val = float(r[1])
            h_val = float(r[2])
            l_val = float(r[3])
            c_val = float(r[4])
            v_val = float(r[5])
            f_val = float(r[6]) if len(r) > 6 else 0.0
        except (ValueError, TypeError):
            continue

        dates.append(iso_d)
        opens.append(o_val)
        highs.append(h_val)
        lows.append(l_val)
        closes.append(c_val)
        vols.append(v_val)
        frates.append(f_val)

    if len(closes) < 10:
        return None

    return {
        "d": dates,
        "o": opens,
        "h": highs,
        "l": lows,
        "c": closes,
        "v": vols,
        "foreign_rate": frates,
    }


# ─────────────────────────────────────────────────────────────
# 2. 종목 통합 정보 (Facts, Consensus, Reports, Supply)
# ─────────────────────────────────────────────────────────────


def fetch_stock_integration(ticker: str) -> Dict[str, Any]:
    """네이버 증권 모바일 통합 정보 API 수집.

    반환 정보:
      - info: 현재가, 시가, 고가, 저가, 전일비, 등락률, 시총, 거래량, 대금, 52주 최고/최저, PER, PBR 등
      - consensus: 목표주가 평균, 투자의견
      - supply: 투자자별(기관/외인/개인) 최근 순매수 데이터
      - researches: 최신 증권사 분석 리포트 목록
    """
    url = f"https://m.stock.naver.com/api/stock/{ticker}/integration"
    data = _request_json(url) or {}

    stock_name = data.get("stockName", "")

    # 1. totalInfos 파싱 (key -> value 매핑)
    total_infos = data.get("totalInfos", [])
    info_map: Dict[str, str] = {}
    for item in total_infos:
        k = item.get("key") or item.get("code")
        v = item.get("value")
        if k and v is not None:
            info_map[k] = str(v)

    # 2. consensusInfo 파싱
    consensus_raw = data.get("consensusInfo") or {}
    consensus = {
        "target_price": consensus_raw.get("priceTargetMean"),
        "opinion": consensus_raw.get("recommMean"),
        "date": consensus_raw.get("createDate"),
    }

    # 3. dealTrendInfos (투자자별 매매동향) 파싱
    deal_trends = data.get("dealTrendInfos", [])
    supply_records = []
    for dt in deal_trends:
        try:
            bizdate = str(dt.get("bizdate", ""))
            iso_d = (
                f"{bizdate[:4]}-{bizdate[4:6]}-{bizdate[6:]}"
                if len(bizdate) == 8
                else bizdate
            )
            f_buy = int(str(dt.get("foreignerPureBuyQuant", "0")).replace(",", "").replace("+", ""))
            o_buy = int(str(dt.get("organPureBuyQuant", "0")).replace(",", "").replace("+", ""))
            i_buy = int(str(dt.get("individualPureBuyQuant", "0")).replace(",", "").replace("+", ""))
            c_price = int(str(dt.get("closePrice", "0")).replace(",", ""))
            vol = int(str(dt.get("accumulatedTradingVolume", "0")).replace(",", ""))
            hold_ratio = str(dt.get("foreignerHoldRatio", ""))
            supply_records.append({
                "date": iso_d,
                "foreign": f_buy,
                "institution": o_buy,
                "retail": i_buy,
                "close": c_price,
                "volume": vol,
                "foreign_ratio": hold_ratio,
            })
        except Exception:
            continue

    # 4. researches (증권사 리포트) 파싱
    researches_raw = data.get("researches", [])
    researches = []
    for r in researches_raw:
        tit = r.get("tit")
        broker = r.get("bnm")
        wdt = str(r.get("wdt", ""))
        date_str = f"{wdt[:4]}-{wdt[4:6]}-{wdt[6:]}" if len(wdt) == 8 else wdt
        if tit:
            researches.append({
                "title": tit,
                "broker": broker,
                "date": date_str,
            })

    return {
        "name": stock_name,
        "ticker": ticker,
        "info": info_map,
        "consensus": consensus,
        "deal_trends": supply_records,
        "researches": researches,
    }


# ─────────────────────────────────────────────────────────────
# 3. 최신 뉴스 수집
# ─────────────────────────────────────────────────────────────


def fetch_news_naver(ticker: str, limit: int = 5) -> List[Dict[str, str]]:
    """네이버 증권 종목 뉴스 API 수집."""
    url = f"https://m.stock.naver.com/api/news/stock/{ticker}?page=1&pageSize={limit}"
    data = _request_json(url) or {}
    items = []
    if isinstance(data, list):
        for group in data:
            if isinstance(group, dict):
                items.extend(group.get("items", []))
    elif isinstance(data, dict):
        items.extend(data.get("items", []))
    news_list = []
    for it in items[:limit]:
        title = it.get("titleFull") or it.get("title", "")
        body = it.get("body", "")
        office = it.get("officeName", "")
        dt = it.get("datetime", "")
        url_link = it.get("mobileNewsUrl", "")
        if title:
            news_list.append({
                "title": title,
                "body": body,
                "office": office,
                "datetime": dt,
                "url": url_link,
            })
    return news_list


# ─────────────────────────────────────────────────────────────
# 4. 종목 스크리닝 (시가총액 상위 등)
# ─────────────────────────────────────────────────────────────


def fetch_top_stocks(market: str = "KOSPI", count: int = 20) -> List[Dict[str, Any]]:
    """네이버 증권 시가총액 상위 종목 수집."""
    m_code = "KOSPI" if market.upper() == "KOSPI" else "KOSDAQ"
    url = f"https://m.stock.naver.com/api/stocks/marketValue/{m_code}?page=1&pageSize={count}"
    data = _request_json(url) or {}
    stocks = data.get("stocks", [])
    results = []
    for s in stocks[:count]:
        ticker = s.get("itemCode")
        name = s.get("stockName")
        price = s.get("closePriceRaw") or s.get("closePrice")
        diff_rate = s.get("fluctuationsRatio")
        m_val = s.get("marketValueHangeul") or s.get("marketValue")
        if ticker and name:
            results.append({
                "ticker": ticker,
                "name": name,
                "price": price,
                "change_rate": diff_rate,
                "market_cap": m_val,
            })
    return results


# ─────────────────────────────────────────────────────────────
# 5. 네이버 증권 보조지표: 매물대 분석도 (Volume Profile / Volume by Price)
# ─────────────────────────────────────────────────────────────


def calculate_volume_profile(series: Dict[str, List[Any]], bins: int = 12) -> Dict[str, Any]:
    """네이버 증권 차트의 [보조지표 -> 매물 분석도]와 동일한 수평 매물대 계산.

    180봉 기간 내 각 가격대별 누적 거래량을 계산하여,
    가장 거래가 집중된 최대 매물대(POC), 하단 지지 매물대, 상단 저항 매물벽을 산출합니다.

    반환:
        {
            "zones": [{"price_min": ..., "price_max": ..., "volume": ..., "pct": ...}],
            "poc_price": float,        # 최대 거래량 집중 가격대 중심값
            "support_zone": float,     # 현재가 하단 최대 매물대 (강력한 지지벽)
            "resistance_zone": float,  # 현재가 상단 최대 매물대 (강력한 매도벽)
            "is_above_poc": bool,      # 최대 매물대를 상향 돌파하여 위에서 노는지 여부
        }
    """
    if not series or not series.get("c") or not series.get("v"):
        return {}

    closes = [c for c in series["c"] if c is not None]
    highs = [h for h in (series.get("h") or closes) if h is not None]
    lows = [l for l in (series.get("l") or closes) if l is not None]
    vols = [v for v in (series.get("v") or []) if v is not None]

    if len(closes) < 10 or len(vols) < 10:
        return {}

    min_p = min(lows)
    max_p = max(highs)
    if min_p >= max_p:
        return {}

    step = (max_p - min_p) / bins
    bucket_vols = [0.0] * bins

    for h_val, l_val, c_val, v_val in zip(highs, lows, closes, vols):
        # 전형 가격 (Typical Price)
        typ = (h_val + l_val + c_val) / 3.0
        idx = int((typ - min_p) / step)
        idx = max(0, min(bins - 1, idx))
        bucket_vols[idx] += v_val

    total_v = sum(bucket_vols) or 1.0
    zones = []
    for i in range(bins):
        p_lo = min_p + i * step
        p_hi = min_p + (i + 1) * step
        v_amt = bucket_vols[i]
        zones.append({
            "price_min": round(p_lo),
            "price_max": round(p_hi),
            "price_mid": round((p_lo + p_hi) / 2),
            "volume": round(v_amt),
            "pct": round((v_amt / total_v) * 100, 1),
        })

    # 최대 거래량 매물대 (POC)
    max_zone = max(zones, key=lambda z: z["volume"])
    poc_price = max_zone["price_mid"]

    last_close = closes[-1]
    # 현재가 하단 매물대 중 가장 큰 곳 (지지선)
    under_zones = [z for z in zones if z["price_mid"] <= last_close]
    support_zone = max(under_zones, key=lambda z: z["volume"])["price_mid"] if under_zones else None

    # 현재가 상단 매물대 중 가장 큰 곳 (저항선)
    above_zones = [z for z in zones if z["price_mid"] > last_close]
    resistance_zone = max(above_zones, key=lambda z: z["volume"])["price_mid"] if above_zones else None

    return {
        "zones": zones,
        "poc_price": poc_price,
        "support_zone": support_zone,
        "resistance_zone": resistance_zone,
        "is_above_poc": last_close >= poc_price,
        "poc_pct": max_zone["pct"],
    }


# ─────────────────────────────────────────────────────────────
# 6. 거래량 폭발일과 네이버 뉴스 매칭 (Volume Surge News Link)
# ─────────────────────────────────────────────────────────────


def match_surge_news(ticker: str, surge_date: str, news_list: Optional[List[Dict[str, str]]] = None) -> Optional[Dict[str, str]]:
    """거래량이 비정상적으로 급증한 날(surge_date) 전후의 네이버 뉴스를 매칭합니다.

    유튜브 강의 핵심 원칙:
      "차트에서 거래량이 번쩍 뜬 날은 반드시 네이버 뉴스를 확인해 그 이유를 알아야 한다."
    """
    if news_list is None:
        news_list = fetch_news_naver(ticker, limit=10)

    if not news_list or not surge_date:
        return None

    # 날짜 정규화: "2026-02-13" -> "20260213"
    target_clean = surge_date.replace("-", "")

    # 1순위: 날짜가 일치하거나 ±2일 이내인 뉴스 탐색
    matched_news = None
    for n in news_list:
        n_dt = (n.get("datetime") or "").replace("-", "")[:8]
        if n_dt:
            try:
                d1 = datetime.strptime(target_clean, "%Y%m%d")
                d2 = datetime.strptime(n_dt, "%Y%m%d")
                diff = abs((d1 - d2).days)
                if diff <= 3:
                    matched_news = n
                    break
            except Exception:
                pass

    # 2순위: 날짜 매칭이 안 되면 가장 연관도 높은 최신 뉴스 헤드라인 반환
    if not matched_news and news_list:
        matched_news = news_list[0]

    return matched_news


# ─────────────────────────────────────────────────────────────
# 7. 기업 재무제표 수집 (연간/분기 F-Score, M-Score, 해자 분석용)
# ─────────────────────────────────────────────────────────────


def fetch_finance_naver(ticker: str, period_type: str = "annual") -> Dict[str, Any]:
    """네이버 증권 기업 재무제표 API 수집 (연간 또는 분기).

    반환 정보:
        {
            "periods": ["202312", "202412", "202512"],
            "metrics": {
                "매출액": {"202312": 2589355.0, ...},
                "영업이익": {...},
                "당기순이익": {...},
                "ROE": {...},
                "부채비율": {...},
                "당좌비율": {...},
                "유보율": {...},
                "EPS": {...},
                "BPS": {...},
            }
        }
    """
    mode = "quarter" if period_type == "quarter" else "annual"
    url = f"https://m.stock.naver.com/api/stock/{ticker}/finance/{mode}"
    data = _request_json(url) or {}

    fi = data.get("financeInfo") or {}
    tr_list = fi.get("trTitleList") or []
    row_list = fi.get("rowList") or []

    # 확정 실적 기간 키 목록 (컨센서스 제외 우선)
    periods = [t.get("key") for t in tr_list if t.get("key")]

    metrics_map: Dict[str, Dict[str, Optional[float]]] = {}
    for row in row_list:
        title = row.get("title", "").strip()
        cols = row.get("columns", {})
        val_dict: Dict[str, Optional[float]] = {}
        for p_key in periods:
            c_info = cols.get(p_key) or {}
            raw_v = c_info.get("value")
            if raw_v and raw_v != "-":
                try:
                    val_dict[p_key] = float(str(raw_v).replace(",", ""))
                except (ValueError, TypeError):
                    val_dict[p_key] = None
            else:
                val_dict[p_key] = None
        metrics_map[title] = val_dict

    return {
        "ticker": ticker,
        "periods": periods,
        "metrics": metrics_map,
        "summary": data.get("corporationSummary", ""),
    }


# ─────────────────────────────────────────────────────────────
# 8. 시장 지수 시세 수집 (하워드 막스 시장 사이클 및 이격도 분석용)
# ─────────────────────────────────────────────────────────────


def fetch_market_index(index_symbol: str = "KOSPI", count: int = 60) -> List[Dict[str, Any]]:
    """네이버 증권 시장 지수(KOSPI / KOSDAQ) 일별 시세 수집.

    반환:
        [{"date": "2026-10-15", "close": 2554.22, "change_rate": -1.2, "open": ..., "high": ..., "low": ...}, ...]
    """
    sym = index_symbol.upper()
    url = f"https://m.stock.naver.com/api/index/{sym}/price?page=1&pageSize={count}"
    data = _request_json(url) or []

    results = []
    if isinstance(data, list):
        for item in data:
            dt = item.get("localTradedAt", "")
            c_raw = str(item.get("closePrice", "0")).replace(",", "")
            diff_raw = str(item.get("fluctuationsRatio", "0")).replace(",", "")
            try:
                results.append({
                    "date": dt,
                    "close": float(c_raw),
                    "change_rate": float(diff_raw),
                })
            except Exception:
                continue
    return results
