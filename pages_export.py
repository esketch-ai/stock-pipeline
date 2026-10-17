"""STOCK ANALYSIS / FOLLOW UP 엔진.

유튜브에 실제로 게시된 영상들을 기준으로:
  1. 영상 추천 당시의 기준가격(스냅샷) 및 목표가, 손절선, 5대 스토리 아키타입 수집
  2. 이후 거래일 종가를 매일 자동으로 추적하여 누적 수익률, 최고 수익률, 마일스톤 성과 계산
  3. 목표가 달성 여부(Target Hit) 및 손절선 안전마진 실시간 진단
  4. GitHub Pages 및 관리자 대시보드용 data.json 및 price_tracking.json 자동 갱신
"""

from __future__ import annotations

import argparse
import json
import math
import re
import ssl
import urllib.request
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import config

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state" / "price_tracking.json"
SITE = ROOT / "public-dashboard"
KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")
_SSL_CTX = ssl._create_unverified_context()
_NAVER_HDR = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def is_us_stock(record: dict) -> bool:
    """종목이 미국 주식인지 여부 판별 (영문 티커 또는 NASDAQ/NYSE 마켓)."""
    ticker = str(record.get("ticker", "")).strip().upper()
    market = str(record.get("market", "")).strip().upper()
    if re.match(r"^[A-Z]{1,5}(\.[A-Z])?$", ticker):
        return True
    if any(m in market for m in ("NASDAQ", "NYSE", "AMEX", "US", "미국")):
        return True
    return False


def is_kr_market_open(dt_kst: datetime) -> bool:
    """한국 정규 장 시간 판별: 평일(월~금) 09:00 ~ 17:00 KST."""
    if dt_kst.weekday() >= 5:  # 토요일(5), 일요일(6)
        return False
    t = dt_kst.time()
    return time(9, 0) <= t <= time(17, 0)


def is_us_market_open(dt_et: datetime) -> bool:
    """미국 정규 장 시간 판별: 평일(월~금) 09:30 ~ 16:30 ET (한국시간 야간/새벽)."""
    if dt_et.weekday() >= 5:  # 토요일(5), 일요일(6)
        return False
    t = dt_et.time()
    return time(9, 30) <= t <= time(16, 30)


def fetch_naver_realtime_price(ticker: str) -> float | None:
    """네이버 증권 모바일 API로부터 국내 장중 실시간 현재가/최근 체결가 수집."""
    try:
        url = f"https://m.stock.naver.com/api/stock/{ticker}/basic"
        req = urllib.request.Request(url, headers=_NAVER_HDR)
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            cp = data.get("closePrice")
            if cp:
                return float(str(cp).replace(",", ""))
    except Exception:
        pass
    return None


def fetch_us_realtime_price(ticker: str) -> float | None:
    """미국 주식 실시간 현재가 수집 (네이버 해외증권 API 및 Yahoo Finance 차트 API 폴백)."""
    clean_ticker = ticker.split(".")[0].upper()
    for suffix in (".O", ".N", ".A"):
        try:
            url = f"https://api.stock.naver.com/stock/{clean_ticker}{suffix}/basic"
            req = urllib.request.Request(url, headers=_NAVER_HDR)
            with urllib.request.urlopen(req, context=_SSL_CTX, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                cp = data.get("closePrice")
                if cp:
                    return float(str(cp).replace(",", ""))
        except Exception:
            continue

    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{clean_ticker}?interval=1d&range=5d"
        req = urllib.request.Request(url, headers=_NAVER_HDR)
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            meta = data["chart"]["result"][0]["meta"]
            price_val = meta.get("regularMarketPrice")
            if price_val:
                return float(price_val)
    except Exception:
        pass
    return None


def price(value) -> float | None:
    try:
        val = float(str(value).replace(",", "").replace("원", "").strip())
        return val if math.isfinite(val) and val > 0 else None
    except (ValueError, TypeError):
        return None


def pct(current: float | None, baseline: float | None) -> float | None:
    return round((current / baseline - 1) * 100, 2) if current and baseline else None


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def discover_published(archive_dir: Path, records: dict, only_published: bool = True) -> int:
    """아카이브에서 유튜브에 게시된 종목들을 자동 발굴하여 사후 추적 목록에 등록."""
    new_count = 0
    for path in sorted(archive_dir.glob("????-??-??/??????.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        if not isinstance(item, dict):
            continue

        # 유튜브 게시 영상 기준 필터링
        yt_id = item.get("published_video_id")
        if only_published and not yt_id:
            continue

        if item.get("blocked"):
            continue

        ticker = path.stem
        if not re.fullmatch(r"\d{6}", ticker):
            continue

        key = f"{path.parent.name}-{ticker}"

        # 팩트 및 후보 안전 추출
        facts = item.get("facts") if isinstance(item.get("facts"), dict) else {}
        cand = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
        sc = item.get("script") if isinstance(item.get("script"), dict) else {}
        scene = item.get("scene_data") if isinstance(item.get("scene_data"), dict) else {}

        baseline = (
            price(cand.get("close"))
            or price(facts.get("close_raw"))
            or price(facts.get("close"))
            or price(item.get("close"))
        )

        if not baseline:
            try:
                import sqlite3
                conn = sqlite3.connect(str(ROOT / "data" / "stock_analytics.db"))
                cur = conn.cursor()
                cur.execute("SELECT current_price FROM company_profile WHERE ticker = ?", (ticker,))
                row = cur.fetchone()
                if row and row[0]:
                    baseline = price(row[0])
                conn.close()
            except Exception:
                pass

        date_raw = str(facts.get("trading_day") or cand.get("trading_day") or path.parent.name).replace("-", "")
        if len(date_raw) == 8:
            date_str = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:]}"
        else:
            date_str = path.parent.name

        name = item.get("name") or sc.get("name") or cand.get("name") or facts.get("name") or ticker

        # 목표주가 및 손절선 추출
        target_price = (
            price(item.get("target_price"))
            or price(cand.get("target_price"))
            or price(facts.get("target_price"))
            or price(scene.get("target_price"))
        )
        if not target_price:
            try:
                import sqlite3
                conn = sqlite3.connect(str(ROOT / "data" / "stock_analytics.db"))
                cur = conn.cursor()
                cur.execute("SELECT consensus_target FROM valuation_consensus WHERE ticker = ?", (ticker,))
                row = cur.fetchone()
                if row and row[0]:
                    target_price = price(row[0])
                conn.close()
            except Exception:
                pass

        stop_loss = (
            price(item.get("stop_loss"))
            or price(cand.get("stop_loss"))
            or price(scene.get("support_price"))
        )
        archetype = item.get("archetype") or cand.get("archetype") or "저평가 가치 반등"

        existing = records.get(key)
        if not existing:
            records[key] = {
                "id": key,
                "ticker": ticker,
                "name": name,
                "market": cand.get("market") or facts.get("market") or "KOSPI",
                "createdAt": item.get("video_created_at") or item.get("archived_at") or path.parent.name,
                "baseline": baseline,
                "baselineDate": date_str,
                "baselineSource": "YouTube 영상 추천 당시 종가",
                "targetPrice": target_price,
                "stopLoss": stop_loss,
                "archetype": archetype,
                "youtubeId": yt_id,
                "youtubeUrl": f"https://youtu.be/{yt_id}" if yt_id else None,
                "thumbUrl": f"https://i.ytimg.com/vi/{yt_id}/hqdefault.jpg" if yt_id else None,
                "history": [],
                "checkedAt": None,
                "status": "pending",
            }
            new_count += 1
        else:
            # 기존 레코드 메타데이터 보강 (유튜브 ID, 목표가 등)
            if yt_id and not existing.get("youtubeId"):
                existing["youtubeId"] = yt_id
                existing["youtubeUrl"] = f"https://youtu.be/{yt_id}"
                existing["thumbUrl"] = f"https://i.ytimg.com/vi/{yt_id}/hqdefault.jpg"
            if target_price and not existing.get("targetPrice"):
                existing["targetPrice"] = target_price
            if stop_loss and not existing.get("stopLoss"):
                existing["stopLoss"] = stop_loss
            if archetype and not existing.get("archetype"):
                existing["archetype"] = archetype

    return new_count


def refresh_record(record: dict, fetch_func, end_date, now_iso: str) -> None:
    """개별 종목의 후속 일별 종가를 갱신하고 최고가 및 수익률 지표 계산."""
    if not record.get("baseline") or not record.get("baselineDate"):
        record["status"] = "missing-baseline"
        return

    baseline_date = datetime.fromisoformat(record["baselineDate"]).date()
    start = baseline_date + timedelta(days=1)
    if baseline_date > end_date:
        record["status"] = "waiting"
        record["checkedAt"] = now_iso
        return

    try:
        rows = fetch_func(record["ticker"], baseline_date, end_date)
        merged = {p["date"]: p for p in record.get("history", [])}
        quotes = []
        for date_str, close_val in rows:
            c = price(close_val)
            if c and baseline_date.isoformat() <= date_str <= end_date.isoformat():
                quotes.append({"date": date_str, "close": c})
            if c and start.isoformat() <= date_str <= end_date.isoformat():
                merged[date_str] = {"date": date_str, "close": c}

        if quotes:
            latest = max(quotes, key=lambda p: p["date"])
            record["latestQuote"] = latest

        # 실시간 현재가 보강 (한국 장중: 09:00~17:00 KST, 미국 장중: 09:30~16:30 ET)
        now_dt = datetime.fromisoformat(now_iso)
        today_str = now_dt.strftime("%Y-%m-%d")
        is_us = is_us_stock(record)

        if is_us:
            # 미국 주식: 미국 장중 실시간 현재가 수집
            rt_price = fetch_us_realtime_price(record["ticker"])
            if rt_price:
                record["latestQuote"] = {"date": today_str, "close": rt_price, "isRealtime": True}
                if baseline_date.isoformat() < today_str:
                    merged[today_str] = {"date": today_str, "close": rt_price}
        else:
            # 한국 주식: 평일 09:00~17:00 장중 실시간 현재가 보강
            if now_dt.weekday() < 5 and now_dt.hour >= 9:
                if not any(p["date"] == today_str for p in quotes):
                    rt_price = fetch_naver_realtime_price(record["ticker"])
                    if rt_price:
                        record["latestQuote"] = {"date": today_str, "close": rt_price, "isRealtime": True}
                        if baseline_date.isoformat() < today_str:
                            merged[today_str] = {"date": today_str, "close": rt_price}

        record["history"] = sorted(merged.values(), key=lambda p: p["date"])
        record["status"] = "ok" if (quotes or record.get("latestQuote")) else "no-new-data"
        record["checkedAt"] = now_iso
    except Exception as exc:
        record["status"] = "fetch-error"
        record["error"] = str(exc)


def format_public_item(record: dict) -> dict:
    """공개 대시보드 및 관리자 Follow-up 뷰를 위한 완전한 성과 레코드 생성."""
    out = dict(record)
    base = record["baseline"]

    # 히스토리 수익률 매핑
    hist_with_pct = []
    max_c = base
    min_c = base
    for p in record.get("history", []):
        c = p["close"]
        chg = pct(c, base)
        hist_with_pct.append({**p, "changePct": chg})
        if c > max_c:
            max_c = c
        if c < min_c:
            min_c = c

    out["history"] = hist_with_pct

    # 최신 종가 및 변동률
    candidates = hist_with_pct + ([record["latestQuote"]] if record.get("latestQuote") else [])
    last = max(candidates, key=lambda p: p["date"]) if candidates else None
    if last:
        last = {**last, "changePct": pct(last["close"], base)}
        if last["close"] > max_c:
            max_c = last["close"]
        if last["close"] < min_c:
            min_c = last["close"]

    out["latest"] = last
    out["maxPrice"] = max_c
    out["maxReturnPct"] = pct(max_c, base)
    out["minPrice"] = min_c

    # 목표가 진척도 및 상태 판별
    tgt = record.get("targetPrice")
    cur = last["close"] if last else base
    if tgt and base:
        out["targetUpsidePct"] = pct(tgt, base)
        out["targetProgressPct"] = round(((cur - base) / (tgt - base)) * 100, 1) if tgt != base else 100.0
        if cur >= tgt:
            out["targetStatus"] = "목표가 달성 🎯"
            out["targetStatusClass"] = "hit"
        elif cur >= base * 1.1:
            out["targetStatus"] = "순항 중 🚀"
            out["targetStatusClass"] = "up"
        else:
            out["targetStatus"] = "관찰 중"
            out["targetStatusClass"] = "wait"
    else:
        out["targetStatus"] = "설정 없음"
        out["targetStatusClass"] = "none"

    # 손절선 대비 상태
    sl = record.get("stopLoss")
    if sl and cur:
        out["stopLossMarginPct"] = pct(cur, sl)
        out["stopLossAlert"] = cur <= sl
    else:
        out["stopLossMarginPct"] = None
        out["stopLossAlert"] = False

    # 마일스톤 D+1, D+5, D+10, D+20
    out["milestones"] = {
        str(n): out["history"][n - 1]["changePct"] if len(out["history"]) >= n else None
        for n in (1, 3, 5, 10, 20)
    }

    # 외부 증권 포털 연계 URL (한국 vs 미국 구분)
    ticker = record.get("ticker", "")
    is_us = is_us_stock(record)
    out["isUsStock"] = is_us
    clean = ticker.split(".")[0].upper()
    if is_us:
        out["market"] = record.get("market") or "NASDAQ"
        out["currency"] = "$"
        out["naverFinanceUrl"] = f"https://m.stock.naver.com/worldstock/stock/{clean}"
        out["tossUrl"] = f"https://wts.tossinvest.com/stocks/{clean}"
        out["yahooFinanceUrl"] = f"https://finance.yahoo.com/quote/{clean}"
        out["daumFinanceUrl"] = f"https://finance.daum.net/global/quotes/US.{clean}"
    else:
        out["currency"] = "원"
        out["naverFinanceUrl"] = f"https://finance.naver.com/item/main.naver?code={ticker}"
        out["tossUrl"] = f"https://wts.tossinvest.com/stocks/{ticker}"
        out["yahooFinanceUrl"] = f"https://finance.yahoo.com/quote/{ticker}.KS"
        out["daumFinanceUrl"] = f"https://finance.daum.net/quotes/A{ticker}"
    return out


def main():
    parser = argparse.ArgumentParser(description="YouTube 업로드 영상 기준 사후 시세 추적 및 대시보드 갱신")
    parser.add_argument("--offline", action="store_true", help="저장된 시세 이력으로만 대시보드 재생성")
    parser.add_argument("--all", action="store_true", help="유튜브 미게시 영상도 모두 포함")
    parser.add_argument("--force", action="store_true", help="장 운영시간 여부와 무관하게 전체 강제 갱신")
    args = parser.parse_args()

    now_kst = datetime.now(KST)
    now_et = datetime.now(ET)

    kr_open = is_kr_market_open(now_kst)
    us_open = is_us_market_open(now_et)

    # 1. 정규 거래 시간 게이팅 (한국 09:00~17:00 KST, 미국 09:30~16:30 ET)
    if not args.force and not args.offline and not kr_open and not us_open:
        print(f"⏸️ [1시간 스케줄 스킵] 현재 정규 거래 시간이 아닙니다.")
        print(f"   - 한국 주식 (09:00~17:00 KST): 현재 {now_kst.strftime('%H:%M:%S')} {'(열림 🟢)' if kr_open else '(닫힘 ⏸️)'}")
        print(f"   - 미국 주식 (09:30~16:30 ET): 현재 {now_et.strftime('%H:%M:%S')} {'(열림 🟢)' if us_open else '(닫힘 ⏸️)'}")
        print(f"   ※ 다음 장 시작 시 1시간 단위 갱신이 자동 진행됩니다. (수동 강제 실행: --force)")
        return

    records = {}
    if STATE.exists():
        try:
            records = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            records = {}

    archive_dir = config.DATA_DIR / "archive"
    new_found = discover_published(archive_dir, records, only_published=not args.all)
    print(f"📡 YouTube 게시 영상 검색: 신규 {new_found}건 발굴 (총 {len(records)}개 추적 대상)")

    # 갱신 기준일 계산:
    if now_kst.weekday() < 5 and now_kst.hour >= 9:
        end = now_kst.date()
    else:
        days_back = 1
        if now_kst.weekday() == 6:       # 일요일 -> 2일 전(금)
            days_back = 2
        elif now_kst.weekday() == 0:     # 월요일 아침 -> 3일 전(금)
            days_back = 3
        elif now_kst.weekday() == 5:     # 토요일 -> 1일 전(금)
            days_back = 1
        end = now_kst.date() - timedelta(days=days_back)

    if not args.offline:
        print(f"📈 시세 수집 가동 — 한국장: {'열림 🟢' if kr_open else '닫힘 ⏸️'} | 미국장: {'열림 🟢' if us_open else '닫힘 ⏸️'} (기준일 ~ {end})")
        try:
            from pykrx import stock

            def fetch_ohlcv(ticker: str, start: datetime.date, end_d: datetime.date):
                frame = stock.get_market_ohlcv_by_date(
                    start.strftime("%Y%m%d"), end_d.strftime("%Y%m%d"), ticker, adjusted=False
                )
                return [(d.strftime("%Y-%m-%d"), float(row["종가"])) for d, row in frame.iterrows() if row["거래량"] > 0]
        except ImportError:
            import naver_finance

            def fetch_ohlcv(ticker: str, start: datetime.date, end_d: datetime.date):
                candles = naver_finance.fetch_chart_data(ticker, days=60)
                return [(c["date"], float(c["close"])) for c in candles if start.isoformat() <= c["date"] <= end_d.isoformat()]

        updated_count = 0
        for i, rec in enumerate(records.values(), 1):
            is_us = is_us_stock(rec)
            # 한국 주식은 한국 장중(09:00~17:00 KST) 또는 force 일 때만 갱신
            # 미국 주식은 미국 장중(09:30~16:30 ET) 또는 force 일 때만 갱신
            should_refresh = args.force or (is_us and us_open) or (not is_us and kr_open)
            if not should_refresh:
                continue

            refresh_record(rec, fetch_ohlcv, end, now_kst.isoformat(timespec="seconds"))
            updated_count += 1
            if updated_count % 5 == 0 or i == len(records):
                print(f"  [{updated_count}/{len(records)}] {rec.get('name', rec['ticker'])} 시세 갱신 완료 ({'US' if is_us else 'KR'})")

    write_json(STATE, records)

    formatted_items = [
        format_public_item(r)
        for r in sorted(records.values(), key=lambda r: r.get("createdAt", ""), reverse=True)
    ]

    # 종합 통계 계산
    with_return = [it for it in formatted_items if it.get("latest") and it["latest"].get("changePct") is not None]
    avg_return = round(sum(it["latest"]["changePct"] for it in with_return) / len(with_return), 2) if with_return else 0.0
    positive_count = sum(1 for it in with_return if it["latest"]["changePct"] > 0)
    win_rate = round((positive_count / len(with_return)) * 100, 1) if with_return else 0.0
    target_hits = sum(1 for it in formatted_items if "달성" in it.get("targetStatus", ""))

    session_desc = []
    if kr_open:
        session_desc.append("한국 시장 장중 (09:00~17:00 KST)")
    if us_open:
        session_desc.append("미국 시장 장중 (09:30~16:30 ET)")
    if not session_desc:
        session_desc.append("정규 시장 마감 (대기)")

    summary_stats = {
        "totalTracked": len(formatted_items),
        "activeQuotes": len(with_return),
        "avgReturnPct": avg_return,
        "winRatePct": win_rate,
        "targetHitsCount": target_hits,
        "marketThrough": end.isoformat(),
        "generatedAt": now_kst.isoformat(timespec="seconds"),
        "krMarketOpen": kr_open,
        "usMarketOpen": us_open,
        "marketSessionText": " / ".join(session_desc),
    }

    output_data = {
        "summary": summary_stats,
        "pricePolicy": "YouTube 영상 추천 당시 종가 대비 미조정 일별 종가 수익률입니다. 한국 주식은 09:00~17:00 KST, 미국 주식은 09:30~16:30 ET 동안 1시간마다 갱신됩니다.",
        "items": formatted_items,
    }
    write_json(SITE / "data.json", output_data)

    print(f"✅ STOCK ANALYSIS / FOLLOW UP 대시보드 갱신 완료: {len(formatted_items)}건 (평균 수익률: {avg_return}%, 목표달성: {target_hits}건)")


if __name__ == "__main__":
    main()
