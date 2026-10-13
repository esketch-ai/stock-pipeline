"""영상 제작가격 스냅샷과 후속 종가를 GitHub Pages용으로 내보낸다."""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import config

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "state" / "price_tracking.json"
SITE = ROOT / "public-dashboard"
KST = ZoneInfo("Asia/Seoul")


def price(value):
    try:
        value = float(str(value).replace(",", ""))
        return value if math.isfinite(value) and value > 0 else None
    except (ValueError, TypeError):
        return None


def pct(current, baseline):
    return round((current / baseline - 1) * 100, 2) if current and baseline else None


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def discover(archive_dir, records):
    for path in sorted(archive_dir.glob("????-??-??/??????.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        if not item.get("video") or item.get("blocked"):
            continue
        ticker = path.stem
        if not re.fullmatch(r"\d{6}", ticker):
            continue
        key = f"{path.parent.name}-{ticker}"
        if key in records:
            continue  # 제작 기준가격은 후속 조회·재생성으로 덮어쓰지 않는다.
        facts = item.get("facts") or {}
        baseline = price(facts.get("close_raw") or facts.get("close"))
        date = str(facts.get("trading_day") or "").replace("-", "")
        if len(date) == 8:
            date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        else:
            date = None
        records[key] = {
            "id": key, "ticker": ticker,
            "name": facts.get("name") or (item.get("candidate") or {}).get("name") or ticker,
            "createdAt": item.get("video_created_at") or item.get("archived_at") or path.parent.name,
            "createdAtSource": "render" if item.get("video_created_at") else "archive",
            "baseline": baseline, "baselineDate": date,
            "baselineSource": "영상 제작 팩트 스냅샷",
            "history": [], "checkedAt": None, "status": "pending",
        }


def refresh(record, fetch, end, now):
    if not record["baseline"] or not record["baselineDate"]:
        record["status"] = "missing-baseline"
        return
    # 최신 종가는 기준일도 조회한다. 제작 스냅샷과 D+N 이력은 별도로 유지.
    baseline_date = datetime.fromisoformat(record["baselineDate"]).date()
    start = baseline_date + timedelta(days=1)
    created = record.get("createdAt")
    if created:
        start = max(start, datetime.fromisoformat(created).date())
    if baseline_date > end:
        record["status"] = "waiting"
        record["checkedAt"] = now
        return
    try:
        rows = fetch(record["ticker"], baseline_date, end)
        merged = {p["date"]: p for p in record["history"]}
        quotes = []
        for date, close in rows:
            close = price(close)
            if close and baseline_date.isoformat() <= date <= end.isoformat():
                quotes.append({"date": date, "close": close})
            if close and start.isoformat() <= date <= end.isoformat():
                merged[date] = {"date": date, "close": close}
        if quotes:
            latest = max(quotes, key=lambda p: p["date"])
            if latest["date"] >= (record.get("latestQuote") or {}).get("date", ""):
                record["latestQuote"] = latest
        record["history"] = sorted(merged.values(), key=lambda p: p["date"])
        record["status"] = "ok" if quotes else "no-new-data"
        record["checkedAt"] = now
    except Exception:
        # 조회 실패를 0% 또는 새 시세로 위장하지 않는다. 기존 이력 보존.
        record["status"] = "fetch-error"


def public_record(record):
    out = dict(record)
    out["history"] = [{**p, "changePct": pct(p["close"], record["baseline"])} for p in record["history"]]
    candidates = record["history"] + ([record["latestQuote"]] if record.get("latestQuote") else [])
    last = max(candidates, key=lambda p: p["date"]) if candidates else None
    if last:
        last = {**last, "changePct": pct(last["close"], record["baseline"])}
    out["latest"] = last
    out["milestones"] = {str(n): out["history"][n-1]["changePct"] if len(out["history"]) >= n else None for n in (1, 5, 20)}
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="저장된 이력으로만 생성")
    args = parser.parse_args()
    now = datetime.now(KST)
    records = json.loads(STATE.read_text()) if STATE.exists() else {}
    discover(config.DATA_DIR / "archive", records)
    # 장중 가격을 확정 종가로 기록하지 않는다. 18시 이후 당일 조회.
    end = now.date() if now.hour >= 18 else now.date() - timedelta(days=1)
    if not args.offline:
        from pykrx import stock

        def fetch(ticker, start, end):
            frame = stock.get_market_ohlcv_by_date(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), ticker, adjusted=False)
            return [(d.strftime("%Y-%m-%d"), float(row["종가"])) for d, row in frame.iterrows() if row["거래량"] > 0]

        for record in records.values():
            refresh(record, fetch, end, now.isoformat(timespec="seconds"))
    write_json(STATE, records)
    write_json(SITE / "data.json", {
        "generatedAt": now.isoformat(timespec="seconds"),
        "marketThrough": end.isoformat(), "offline": args.offline,
        "pricePolicy": "제작 팩트 가격 대비 최신 미조정 종가의 단순 증감률(기준일 종가 포함). D+N은 기준일 이후 관측 거래일만 집계합니다. 배당·수수료 제외. 분할·병합 등 권리변동은 보정하지 않습니다.",
        "items": [public_record(r) for r in sorted(records.values(), key=lambda r: r["createdAt"], reverse=True)],
    })
    print(f"공개 대시보드 생성: {len(records)}건 → {SITE}")


if __name__ == "__main__":
    main()
