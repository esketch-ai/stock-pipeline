"""6단계(SVG 차트) 통합 검증 — Python 레이어만."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import chart_data
import cues
import stage4_render
from config import DATA_DIR
from logger import log

TICKER = "084670"
FAILS = []


def check(name, cond, detail=""):
    print(f"  {'✓' if cond else '✖'} {name}" + (f"  — {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def main() -> int:
    from pykrx import stock
    import screening as _scr

    print("\n[1] chart_data 직렬화")
    tday = _scr.last_trading_day(stock)
    end = datetime.strptime(tday, "%Y%m%d")
    hist = stock.get_market_ohlcv_by_date(
        (end - timedelta(days=365)).strftime("%Y%m%d"), tday, TICKER
    )
    series = chart_data.to_series(hist)
    check("series 생성", series is not None)
    check("봉 수 180", len(series["c"]) == 180, f"{len(series['c'])}")
    check("키 완비", all(k in series for k in ("d", "o", "h", "l", "c", "v", "rsi", "ret", "pts")))
    check("JSON 직렬화 가능", bool(json.dumps(series, ensure_ascii=False)))
    check("의미 포인트", set(series["pts"]) >= {"volMax", "high52", "low52", "last", "retMax", "retMin"})

    print("\n[2] cues — 의미 기반 포인터")
    for kind in ("price", "trend", "momentum", "return"):
        specs = cues.build_pointer_positions(series, kind)
        ok = bool(specs) and all("index" in s and "panel" in s for s in specs)
        no_xy = all("x" not in s and "y" not in s for s in specs)
        check(f"{kind}: index/panel 스펙", ok, f"{len(specs)}개")
        check(f"{kind}: 매직 x/y 없음", no_xy)

    print("\n[3] build_cues — series 경로")
    props = json.loads((DATA_DIR / f"props_{TICKER}.json").read_text(encoding="utf-8"))
    item = props["items"][0]
    built = cues.build_cues(
        item["script"].get("hook", "") or "테스트 대본입니다.",
        item["timestamps"],
        None,
        series,
        ["price", "trend", "momentum", "return"],
    )
    check("cue 생성", len(built) > 0, f"{len(built)}개")
    withptr = [c for c in built if c.get("pointer")]
    check("포인터 부착", len(withptr) > 0, f"{len(withptr)}개")
    check("포인터에 from/to 존재", all("from" in c["pointer"] and "to" in c["pointer"] for c in withptr))

    print("\n[4] stage4_render._item_props — series 전달")
    manifest_item = {
        "name": "동양고속",
        "audio": item["audioSrc"],
        "timestamps": item["timestamps"],
        "script": item["script"],
        "long_text": "테스트 대본. 현재가 37,200원입니다.",
        "chart_paths": ["cache/x/chart_price.png", "cache/x/chart_momentum.png"],
        "facts": None,
        "series": series,
    }
    out = stage4_render._item_props(TICKER, manifest_item)
    check("props 에 series 포함", out.get("series") is not None)
    check("series 봉 수 보존", len(out["series"]["c"]) == 180)
    check("cue 생성됨", len(out.get("cues") or []) > 0)
    check("props 직렬화 가능", bool(json.dumps(out, ensure_ascii=False)))

    print("\n[5] PNG 폴백 — series 없음")
    no_series = dict(manifest_item)
    no_series.pop("series")
    out2 = stage4_render._item_props(TICKER, no_series)
    check("series = None", out2.get("series") is None)
    check("레거시 x/y 폴백 좌표 사용",
          all(("x" in c["pointer"] and "y" in c["pointer"])
              for c in (out2.get("cues") or []) if c.get("pointer")))

    print("\n[6] JSON 크기 (props 실사용 시)")
    kb = len(json.dumps(out, ensure_ascii=False)) / 1024
    check("props 1MB 미만", kb < 1024, f"{kb:.0f} KB")

    print("\n" + "=" * 50)
    print(f"통과 {18 - len(FAILS)}  실패 {len(FAILS)}")
    if FAILS:
        for f in FAILS:
            print(f"  · {f}")
    print("=" * 50)
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
