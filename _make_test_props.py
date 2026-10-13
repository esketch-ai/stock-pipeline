"""SVG 차트 검증용 props 생성 (실제 KRX 데이터)."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import chart_data
from config import DATA_DIR
from logger import log

TICKER = sys.argv[1] if len(sys.argv) > 1 else "084670"
OUT = DATA_DIR / "props_svg_test.json"


def main() -> int:
    log.info("테스트 props 생성: %s", TICKER)

    # 실제 props 를 베이스로 쓰되 series 만 주입한다
    base_path = DATA_DIR / f"props_{TICKER}.json"
    if not base_path.exists():
        print(f"베이스 props 없음: {base_path}")
        return 1
    props = json.loads(base_path.read_text(encoding="utf-8"))

    # 필요하면 KRX 에서 직접 히스토리
    try:
        from pykrx import stock
        import screening as _scr

        tday = _scr.last_trading_day(stock)
        end = datetime.strptime(tday, "%Y%m%d")
        hist = stock.get_market_ohlcv_by_date(
            (end - timedelta(days=365)).strftime("%Y%m%d"), tday, TICKER
        )
    except Exception as exc:
        print(f"KRX 조회 실패: {exc}")
        return 1

    series = chart_data.to_series(hist)
    if not series:
        print("직렬화 실패")
        return 1

    for item in props["items"]:
        item["series"] = series
        item["name"] = item.get("name") or TICKER

    OUT.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    size_kb = OUT.stat().st_size / 1024
    print(f"OK {OUT} ({size_kb:.0f} KB, {len(series['d'])}봉)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
