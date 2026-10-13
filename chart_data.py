"""차트 데이터 직렬화 — matplotlib PNG 대신 Remotion SVG 로 넘길 데이터.

왜 이 모듈이 필요한가:
    pykrx 가 주는 OHLCV 는 pandas DataFrame 이라 JSON 으로 바로 못 쓴다.
    이전에는 stage4_render 가 item["hist"] 를 기대했지만 실제론 항상 None 이었고,
    그 결과 포인터 좌표가 하드코딩 값으로 폴백했다.
    여기서 명시적으로 직렬화해 props 에 실어 보낸다.

출력 스키마 (Remotion src/charts 가 그대로 소비):
    {
      "d": ["2025-03-24", ...],   # 거래일 (ISO)
      "o": [..], "h": [..], "l": [..], "c": [..], "v": [..],
      "ma5": [.., null, ...], "ma20": [..], "ma60": [..],
      "rsi": [.., null, ...],     # 14일 RSI
      "ret": [..]                 # 기간 누적 수익률(%)
    }

결측치는 None 으로 남긴다. Remotion 쪽 path 빌더가 끊어 그린다
(0 으로 채우면 이동평균 선이 바닥에 붙어 lying 한다).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from logger import log

# Remotion 이 한 번에 그리기 편하도록 막대 수를 제한한다.
# 180봉이면 1년치 대략치가 되며 SVG 요소 수도 프레임당 감당이 가능하다.
MAX_BARS = 180

_KOREAN_COLUMNS = {
    "시가": "o",
    "고가": "h",
    "저가": "l",
    "종가": "c",
    "거래량": "v",
}

# 이동평균 — charts_extended 의 mav=(5, 20, 60) 와 동일하게 맞춘다
_MA_WINDOWS = (("ma5", 5), ("ma20", 20), ("ma60", 60))
_RSI_WINDOW = 14


def _round_list(values, digits: int = 2) -> list[float | None]:
    """NaN/inf 를 None 으로 정규화한다 (JSON 은 NaN 을 못 쓴다)."""
    out: list[float | None] = []
    for x in values:
        if x is None:
            out.append(None)
            continue
        try:
            f = float(x)
        except (TypeError, ValueError):
            out.append(None)
            continue
        if f != f or f in (float("inf"), float("-inf")):  # NaN / inf
            out.append(None)
        else:
            out.append(round(f, digits))
    return out


def _rsi(close, window: int = _RSI_WINDOW) -> list[float | None]:
    """Wilder 평활이 아닌 단순 이동평균 방식 RSI.

    차트 표시 목적이라 표준 Wilder 와 차이가 수십 ms 수준이며,
    Python/JS 양쪽에서 동일 공식을 쓰도록 여기서 한 번만 계산한다.
    """
    n = len(close)
    out: list[float | None] = [None] * n
    gains = losses = 0.0
    for i in range(1, n):
        delta = close[i] - close[i - 1]
        gain = delta if delta > 0 else 0.0
        loss = -delta if delta < 0 else 0.0
        if i <= window:
            gains += gain
            losses += loss
            if i < window:
                continue
            gains /= window
            losses /= window
        else:
            gains = (gains * (window - 1) + gain) / window
            losses = (losses * (window - 1) + loss) / window
        if losses == 0:
            out[i] = 100.0 if gains > 0 else 50.0
        else:
            rs = gains / losses
            out[i] = 100 - (100 / (1 + rs))
    return out


def to_series(hist, max_bars: int = MAX_BARS) -> dict[str, Any] | None:
    """pykrx OHLCV DataFrame → Remotion 차트용 dict.

    데이터가 부족하거나 컬럼이 없으면 None 을 돌려준다
    (호출측은 PNG 폴백으로 넘어간다).
    """
    if hist is None or len(hist) < 30:
        return None

    try:
        import pandas as pd
    except ImportError:  # pragma: no cover - pandas 는 항상 있음
        return None

    df = hist.copy()
    missing = [k for k in _KOREAN_COLUMNS if k not in df.columns]
    if missing:
        log.debug("차트 데이터 컬럼 누락: %s", missing)
        return None

    df = df[list(_KOREAN_COLUMNS)].rename(columns=_KOREAN_COLUMNS)

    # 최근 구간만 남긴다 (오래된 봉은 화면 밖)
    if len(df) > max_bars:
        df = df.tail(max_bars)

    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index, format="%Y%m%d")
        except Exception:
            df.index = pd.to_datetime(df.index)

    dates = [d.strftime("%Y-%m-%d") for d in df.index]

    close = df["c"].astype(float)
    volume = df["v"].astype(float)

    ma: dict[str, list[float | None]] = {}
    for key, window in _MA_WINDOWS:
        ma[key] = _round_list(close.rolling(window).mean())

    base = close.iloc[0]
    ret = _round_list((close / base - 1) * 100) if base else [None] * len(df)

    series: dict[str, Any] = {
        "d": dates,
        "o": _round_list(df["o"].astype(float)),
        "h": _round_list(df["h"].astype(float)),
        "l": _round_list(df["l"].astype(float)),
        "c": _round_list(close),
        "v": _round_list(volume, 0),
        "rsi": _round_list(_rsi(close.tolist())),
        "ret": ret,
    }
    series.update(ma)

    # 포인터 좌표는 여기서 "어느 봉인가" 만 정해 둔다.
    # 정확한 x/y 는 Remotion 이 각 차트의 스케일로 계산한다
    # (Python 과 TS 에 레이아웃 상수를 두 벌 두면 반드시 어긋난다).
    series["pts"] = _semantic_points(df, ret)

    log.info("차트 데이터 직렬화: %d봉 (%s ~ %s)", len(df), dates[0], dates[-1])
    return series


def _semantic_points(df, ret) -> dict[str, int]:
    """차트 종류별 '주목할 봉'의 인덱스.

    Remotion 의 ChartPointer 가 이 인덱스를 받아 자기 스케일로 좌표를 만든다.
    """
    n = len(df)
    hi = df["h"].astype(float)
    lo = df["l"].astype(float)
    vol = df["v"].astype(float)

    def _argmax(values) -> int:
        return max(range(n), key=lambda i: float(values.iloc[i]))

    def _argmin(values) -> int:
        return min(range(n), key=lambda i: float(values.iloc[i]))

    ret_vals = [(-1e18 if x is None else x) for x in ret]
    return {
        "volMax": _argmax(vol),
        "high52": _argmax(hi),
        "low52": _argmin(lo),
        "last": n - 1,
        "retMax": max(range(n), key=lambda i: ret_vals[i]),
        "retMin": min(range(n), key=lambda i: ret_vals[i]),
    }


def series_from_manifest(item: dict) -> dict[str, Any] | None:
    """manifest item 에서 series 를 안전하게 꺼낸다."""
    s = item.get("series")
    if isinstance(s, dict) and s.get("c"):
        return s
    return None


# ─────────────────────────────────────────────────────────────
# 수급 (투자자별 순매수) — 참고 영상이 가장 강조하는 축
# ─────────────────────────────────────────────────────────────


def fetch_supply(ticker: str, days: int = 60, end: str | None = None) -> dict[str, Any] | None:
    """투자자별 순매수 시계열 (기관 / 개인 / 외국인), 억 단위.

    pykrx 는 금액을 원 단위로 준다. 데이터가 없으면 None 을 돌려준다 —
    씬이 차트 없이 텍스트로만 진행된다.
    """
    try:
        from pykrx import stock
    except ImportError:  # pragma: no cover
        return None

    try:
        import screening as _scr

        end = end or _scr.last_trading_day(stock)
        start = (datetime.strptime(end, "%Y%m%d") - timedelta(days=days)).strftime("%Y%m%d")
        df = stock.get_market_trading_value_by_date(start, end, ticker)
    except Exception as exc:
        log.debug("수급 조회 실패 %s: %s", ticker, exc)
        return None

    if df is None or len(df) < 3:
        return None

    df = df.drop(columns=["전체"], errors="ignore").fillna(0)

    def col(name: str) -> list[float]:
        if name not in df.columns:
            return [0.0] * len(df)
        return [round(float(v) / 1e8, 2) for v in df[name]]

    return {
        "d": [d.strftime("%Y-%m-%d") for d in df.index],
        "institution": col("기관합계"),
        "retail": col("개인"),
        "foreign": col("외국인합계"),
        "other": col("기타법인"),
    }


# ─────────────────────────────────────────────────────────────
# 가격대 (지지 / 저항) — 매수·매도 가격을 구체적으로 말하기 위해
# ─────────────────────────────────────────────────────────────


def support_resistance(series: dict[str, Any], lookback: int = 90) -> dict[str, Any] | None:
    """지지선 · 저항선 — 스윙 저점/고점 기준.

    밴드 방식(하위 30% 의 최고가 등)은 상승추세에서 현재가보다 낮은
    '지지'를 만들어낼 수 있다. 실제 해석에 맞는 기준으로 바꾼다:

      지지 = 현재가 아래에 있는 스윙 저점 중 가장 가까운 것
      저항 = 현재가 위에 있는 스윙 고점 중 가장 가까운 것
              (없으면 '윗꼭지突破 시도' — 저항이 없다는 뜻)

    지지까지 여유 % 는 (현재가-지지)/현재가 로 계산하므로 항상 0~100 이다.
    """
    closes = [x for x in (series.get("c") or [])[-lookback:] if x is not None]
    lows = [x for x in (series.get("l") or [])[-lookback:] if x is not None]
    highs = [x for x in (series.get("h") or [])[-lookback:] if x is not None]
    if len(closes) < 20 or len(lows) != len(closes) or len(highs) != len(closes):
        return None

    last = closes[-1]

    # 스윙 저점: 양옆보다 낮은 봉 → 되돌아온 지점
    swing_lows = [
        lows[i] for i in range(1, len(lows) - 1)
        if lows[i] <= lows[i - 1] and lows[i] < lows[i + 1] and lows[i] < last
    ]
    swing_highs = [
        highs[i] for i in range(1, len(highs) - 1)
        if highs[i] >= highs[i - 1] and highs[i] > highs[i + 1] and highs[i] > last
    ]

    support = round(max(swing_lows)) if swing_lows else round(min(lows))
    resistance = round(min(swing_highs)) if swing_highs else None

    out = {
        "support": support,
        "resistance": resistance,
        "recent_high": round(max(highs)),
        "recent_low": round(min(lows)),
        "last": round(last),
        "room_to_support": round(max(0.0, (last - support) / last * 100), 1) if last else None,
        "room_to_resistance": round(max(0.0, (resistance - last) / last * 100), 1)
        if resistance else None,
        "at_high": resistance is None,
    }
    return out
