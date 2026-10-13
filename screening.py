"""단계 1 — 종목 스크리닝 및 쿨다운 필터링 (pykrx).

pykrx 1.2.x API 기준:
    stock.get_nearest_business_day_in_a_week(date, prev=True) -> str
    stock.get_market_ohlcv_by_ticker(date, market)           -> DataFrame(전 종목)
    stock.get_market_ohlcv_by_date(from, to, ticker)         -> DataFrame(개별 종목)

성능/안정성 설계:
  * 종목별 OHLCV 를 120회 호출하면 KRX 연결이 30~85초 지연 후 reset 되기 쉽다.
    → 대신 '거래일 스냅샷'을 6회만 호출해 전 종목(942개)의 시세를 한 번에 확보한다.
  * 스냅샷끼리 결합하면 1일/3일 수익률과 거래량 배율이 종목별 요청 없이 계산된다.
  * 상세 히스토리는 최종 선정 종목(상위 N개)에 대해서만 1회씩 조회한다.
  * 모든 네트워크 호출은 재시도/백오프를 거친다.

주의: 야간 배치(02:00) 는 주말/공휴일에도 발동하므로 반드시 가장 가까운
거래일로 되돌린 뒤 조회해야 한다.

tradingday 마다 이미 게시한 종목은 쿨다운 기간(기본 7일) 동안 재투입되지 않는다.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from config import DAILY_VIDEO_COUNT, STATE_DIR
from logger import log

COOLDOWN_FILE = STATE_DIR / "cooldown.json"
COOLDOWN_DAYS = 7

LOOKBACK_DAYS = 6      # 스냅샷으로 확보할 거래일 수
HISTORY_DAYS = 180     # 차트/상세용个股 히스토리
SHORTLIST_TOP_N = 40   # 점수 상위 N개만 상세 히스토리 조회
REQUEST_RETRIES = 3
RETRY_BACKOFF = 2.0


@dataclass
class Candidate:
    ticker: str
    name: str
    market: str
    close: float
    change_rate: float
    volume: int
    trading_value: int
    score: float
    reason: str
    selected_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


# ── 네트워크 재시도 헬퍼 ────────────────────────────────

def _with_retry(fn, *args, label: str = "", retries: int = REQUEST_RETRIES, **kwargs):
    """KRX 연결 reset/지연을 재시도로 흡수한다."""
    last = None
    for attempt in range(1, retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — 네트워크 예외 전반
            last = exc
            if attempt == retries:
                break
            wait = RETRY_BACKOFF ** attempt
            log.debug("%s 실패(%s) — %.1fs 후 재시도 %d/%d",
                      label or fn.__name__, type(exc).__name__, wait, attempt, retries)
            time.sleep(wait)
    raise last


def _check_krx_credentials() -> None:
    """pykrx 1.2.x 는 KRX 로그인이 필수. 미설정 시 즉시 명확히 실패."""
    if not (os.getenv("KRX_ID", "").strip() and os.getenv("KRX_PW", "").strip()):
        raise RuntimeError(
            "KRX_ID / KRX_PW 미설정 — pykrx 1.2 이상은 KRX 로그인이 필요합니다.\n"
            "  1) https://www.krx.co.kr 에서 무료 회원가입\n"
            "  2) ~/.local/share/stock-pipeline/.env 의 KRX_ID / KRX_PW 에 계정 정보를 입력\n"
            "  3) 다시 실행"
        )


# ── 쿨다운 ─────────────────────────────────────────────

def _load_cooldown() -> dict[str, str]:
    if not COOLDOWN_FILE.exists():
        return {}
    try:
        return json.loads(COOLDOWN_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("쿨다운 파일 손상 — 초기화합니다: %s", exc)
        return {}


def _save_cooldown(data: dict[str, str]) -> None:
    COOLDOWN_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def in_cooldown(ticker: str, cooldown: dict[str, str]) -> bool:
    stamp = cooldown.get(ticker)
    if not stamp:
        return False
    try:
        last = datetime.fromisoformat(stamp)
    except ValueError:
        return False
    return datetime.now() - last < timedelta(days=COOLDOWN_DAYS)


def mark_published(tickers: list[str]) -> None:
    cooldown = _load_cooldown()
    now = datetime.now().isoformat(timespec="seconds")
    for ticker in tickers:
        cooldown[ticker] = now
    _save_cooldown(cooldown)
    log.info("쿨다운 등록: %s", ", ".join(tickers))


# ── 거래일/스냅샷 ───────────────────────────────────────

def last_trading_day(stock, ref: datetime | None = None) -> str:
    """오늘이 거래일이 아니면 직전 거래일로 되돌린다 (주말/공휴일 대응)."""
    ref = ref or datetime.now()
    return stock.get_nearest_business_day_in_a_week(ref.strftime("%Y%m%d"), prev=True)


def _recent_trading_days(stock, end_date: str, count: int = LOOKBACK_DAYS) -> list[str]:
    """end_date 를 포함해 직전 count 개 거래일을 최신순으로 반환."""
    days: list[str] = []
    cur = end_date
    for _ in range(count):
        if cur not in days:
            days.append(cur)
        prev = (datetime.strptime(cur, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
        nxt = stock.get_nearest_business_day_in_a_week(prev, prev=True)
        if nxt == cur:
            break
        cur = nxt
    return days


def drop_untraded(df):
    """거래정지·미갱신 행을 제거한다.

    KRX 는 그날 거래가 없던 종목에 대해 시가/고가/저가/거래량을 0 으로 채워
    종가만 이전 값을 그대로 실어 보낸다. 이 행을 점수 계산에 넣으면
    0 원대를 분모로 등락률이 수백 % 로 튀어, 실제로는 존재하지 않는
    급등 종목이 후보로 올라온다.

    (2026-10-12 실제 사례: 대영포장(014160) 이 거래정지 구간 때문에
     '3일 +360%' 로 1위가 되어 있었다)
    """
    if df is None or len(df) == 0:
        return df
    mask = (df["거래량"].fillna(0) > 0) & (df["종가"].fillna(0) > 0)
    return df[mask]


def _fetch_snapshots(stock, days: list[str], market: str) -> dict[str, "object"]:
    snaps: dict[str, object] = {}
    for day in days:
        df = _with_retry(
            stock.get_market_ohlcv_by_ticker, day, market=market, label=f"snapshot {day}"
        )
        if df is None or len(df) == 0:
            log.warning("거래일 %s 스냅샷 비어있음 — 건너뜀", day)
            continue
        cleaned = drop_untraded(df)
        dropped = len(df) - len(cleaned)
        if dropped:
            log.debug("거래일 %s 미거래 %d종목 제외", day, dropped)
        if len(cleaned) == 0:
            continue
        snaps[day] = cleaned
    return snaps


# ── 점수 계산 ───────────────────────────────────────────

def _score_from_snapshots(snaps: dict[str, "object"]) -> list[tuple[str, float, str]]:
    """스냅샷(최신순 dict)으로부터 종목별 점수를 계산한다. 종목별 요청 없음."""
    if not snaps:
        return []
    ordered = sorted(snaps.keys(), reverse=True)  # 최신순
    latest = snaps[ordered[0]]

    # 3일 전 종가 (최신 대비 3거래일 전)
    closes = {}
    for day in ordered:
        closes[day] = latest["종가"] if day == ordered[0] else snaps[day]["종가"]
    # 각 날짜의 종가를 종목별로 합치기 위한 정렬된 날짜 목록
    dates = ordered

    scored: list[tuple[str, float, str]] = []
    for ticker in latest.index:
        try:
            c_today = float(latest.at[ticker, "종가"])
            c_prev = float(snaps[dates[1]].at[ticker, "종가"]) if len(dates) > 1 else c_today
            c_3ago = float(snaps[dates[3]].at[ticker, "종가"]) if len(dates) > 3 else c_prev

            ret_1d = c_today / c_prev - 1 if c_prev else 0.0
            ret_3d = c_today / c_3ago - 1 if c_3ago else 0.0

            v_today = float(latest.at[ticker, "거래량"])
            vols = [float(snaps[d].at[ticker, "거래량"]) for d in dates[:5] if ticker in snaps[d].index]
            avg_v = sum(vols) / len(vols) if vols else 0.0
            vol_ratio = v_today / avg_v if avg_v else 0.0

            score = ret_3d * 60 + ret_1d * 20 + min(vol_ratio, 4.0) * 5
            if score <= 0:
                continue
            reason = f"3일 {ret_3d:+.2%} / 1일 {ret_1d:+.2%} / 거래량 {vol_ratio:.2f}배"
            scored.append((str(ticker), round(score, 2), reason))
        except (KeyError, ValueError, ZeroDivisionError):
            continue

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def _fetch_history(stock, ticker: str, end_date: str, days: int = HISTORY_DAYS):
    """상세 히스토리(차트용). name_display=True 로 인덱스 이름이 종목명."""
    end = datetime.strptime(end_date, "%Y%m%d")
    start = (end - timedelta(days=days)).strftime("%Y%m%d")
    df = _with_retry(
        stock.get_market_ohlcv_by_date, start, end_date, ticker,
        name_display=True, label=f"history {ticker}",
    )
    # 거래정지 구간에 0 원짜리 봉이 들어가면 차트 Y축과 등락률이 함께 망가진다
    return drop_untraded(df)


def screen(market: str = "KOSPI", count: int | None = None) -> list[Candidate]:
    """상승 후보를 수집하고 쿨다운으로 걸러낸다."""
    _check_krx_credentials()
    from pykrx import stock

    count = count or DAILY_VIDEO_COUNT
    cooldown = _load_cooldown()

    tday = last_trading_day(stock)
    log.info("기준 거래일: %s (시장: %s)", tday, market)

    days = _recent_trading_days(stock, tday)
    snaps = _fetch_snapshots(stock, days, market)
    if not snaps:
        log.error("스냅샷 조회 실패 — KRX 세션/네트워크 확인 필요.")
        return []

    latest = snaps[sorted(snaps.keys(), reverse=True)[0]]
    scored = _score_from_snapshots(snaps)
    log.info("점수 산출 완료 — 유효 후보 %d종목", len(scored))

    # 쿨다운 + 상위 N개만 상세 히스토리/이름 조회
    picked = [s for s in scored if not in_cooldown(s[0], cooldown)][:SHORTLIST_TOP_N]
    log.info("상세 조회 대상 %d종목 (쿨다운 제외 후 상위 %d)", len(picked), SHORTLIST_TOP_N)

    candidates: list[Candidate] = []
    for ticker, score, reason in picked:
        try:
            hist = _fetch_history(stock, ticker, tday)
            if hist is None or len(hist) < 20:
                continue
            # name_display=True 일 때 종목명은 columns.name 에 들어가고
            # index.name 은 항상 '날짜' 이다.
            name = (hist.columns.name or "").strip() if hist.columns.name else ""
            if not name or name == "날짜" or name.isdigit():
                name = _with_retry(stock.get_market_ticker_name, ticker, label=f"name {ticker}")
            row = latest.loc[ticker] if ticker in latest.index else {}
            candidates.append(
                Candidate(
                    ticker=ticker,
                    name=str(name),
                    market=market,
                    close=float(row.get("종가", hist["종가"].iloc[-1])),
                    change_rate=float(row.get("등락률", 0.0)),
                    volume=int(row.get("거래량", 0)),
                    trading_value=int(row.get("거래대금", 0)),
                    score=score,
                    reason=reason,
                )
            )
        except Exception as exc:
            log.debug("%s 상세 조회 스킵: %s", ticker, exc)
            continue

    selected = candidates[:count]

    log.info("스크리닝 완료 — 후보 %d종목 중 상위 %d종목 선정", len(candidates), len(selected))
    for c in selected:
        log.info("  · %s (%s) score=%s — %s", c.ticker, c.name, c.score, c.reason)

    (STATE_DIR / "candidates.json").write_text(
        json.dumps([asdict(c) for c in selected], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return selected


def screen_by_tickers(tickers: list[str], market: str = "KOSPI") -> list[Candidate]:
    """지정 종목만 후보로 만든다.

    스크리닝 순위를 따르지 않고 특정 종목을 다시 만들 때 쓴다
    (--tickers). 점수와 사유는 조회 시점으로 다시 계산한다.
    """
    _check_krx_credentials()
    from pykrx import stock

    tday = last_trading_day(stock)
    log.info("지정 종목 조회: %s (기준일 %s)", ", ".join(tickers), tday)

    snaps = _fetch_snapshots(stock, _recent_trading_days(stock, tday), market)
    scores = {t: (sc, rs) for t, sc, rs in _score_from_snapshots(snaps)}
    latest = snaps[max(snaps)] if snaps else None

    out: list[Candidate] = []
    for ticker in tickers:
        ticker = ticker.strip()
        if not ticker:
            continue
        try:
            hist = _fetch_history(stock, ticker, tday)
            if hist is None or len(hist) < 20:
                log.error("%s 히스토리 부족 — 건너뜀", ticker)
                continue
            name = (hist.columns.name or "").strip() if hist.columns.name else ""
            if not name or name == "날짜" or name.isdigit():
                name = _with_retry(stock.get_market_ticker_name, ticker, label=f"name {ticker}")
            score, reason = scores.get(ticker, (0.0, "지정 종목"))
            row = latest.loc[ticker] if latest is not None and ticker in latest.index else {}
            out.append(
                Candidate(
                    ticker=ticker,
                    name=str(name),
                    market=market,
                    close=float(row.get("종가", hist["종가"].iloc[-1])),
                    change_rate=float(row.get("등락률", 0.0)),
                    volume=int(row.get("거래량", 0)),
                    trading_value=int(row.get("거래대금", 0)),
                    score=score,
                    reason=reason,
                )
            )
            log.info("  · %s (%s) score=%s — %s", ticker, name, score, reason)
        except Exception as exc:
            log.error("%s 지정 조회 실패: %s", ticker, exc)

    (STATE_DIR / "candidates.json").write_text(
        json.dumps([asdict(c) for c in out], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out