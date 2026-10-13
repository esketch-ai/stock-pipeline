"""장면 시스템 확인 — 기존 산출물 3편으로 7장면 구성이 재현되는지."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import chart_data as cd
import scene_data as sd
from pykrx import stock

import screening as sc

FAILS = []


def check(name, cond, detail=""):
    print(f"  {'✓' if cond else '✖'} {name}" + (f"  — {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def main() -> int:
    man = json.loads(Path("data/long_manifest.json").read_text(encoding="utf-8"))
    tday = sc.last_trading_day(stock)
    end = datetime.strptime(tday, "%Y%m%d")

    for tk, it in man.items():
        print(f"\n{'=' * 74}\n{tk} {it.get('name')}\n{'=' * 74}")

        hist = stock.get_market_ohlcv_by_date(
            (end - timedelta(days=365)).strftime("%Y%m%d"), tday, tk)
        series = cd.to_series(hist)
        supply = cd.fetch_supply(tk, days=60)
        levels = cd.support_resistance(series) if series else None

        # 섹션 텍스트 복원
        secs = it.get("sections") or []
        if secs and "text" not in secs[0]:
            paras = [p.strip() for p in (it.get("long_text") or "").split("\n\n") if p.strip()]
            if len(paras) == len(secs):
                for s, para in zip(secs, paras):
                    s["text"] = para

        ts = it.get("timestamps") or []
        scenes = sd.build_scenes(
            name=it.get("name", tk), ticker=tk, sections=secs, timestamps=ts,
            series=series, supply=supply, levels=levels,
            facts=it.get("facts") or {}, total=ts[-1]["end"] if ts else None,
        )

        check("장면 7개", len(scenes) == 7, f"{len(scenes)}개")
        check("시간 오름차순", all(scenes[i]["from"] <= scenes[i + 1]["from"]
                              for i in range(len(scenes) - 1)))
        check("구간 겹침 없음", all(scenes[i]["to"] <= scenes[i + 1]["from"] + 0.01
                              for i in range(len(scenes) - 1)))
        check("헤드라인 전부 존재", all(s["headline"] for s in scenes))
        check("헤드라인이 stats 를 복붙하지 않음",
              all(s["headline"] not in " ".join(x["value"] for x in s["stats"])
                  or not s["stats"] for s in scenes),
              next((s["headline"] for s in scenes
                    if s["stats"] and s["headline"] in " ".join(x["value"] for x in s["stats"])),
                   "중복 없음"))
        total = sum(s["to"] - s["from"] for s in scenes)
        check("장면 합계 ≈ 영상 길이", abs(total - scenes[-1]["to"]) < 2.0,
              f"{total:.0f}초")

        print()
        for s in scenes:
            dur = s["to"] - s["from"]
            print(f"  [{s['point']}] {s['eyebrow']:6} {s['from']:6.1f}~{s['to']:6.1f}s ({dur:5.1f}초) {s['chart']}")
            print(f"       {s['headline']}")
            if s["sub"]:
                print(f"       └ {s['sub']}")
            if s["stats"]:
                print(f"       · " + "  ".join(f"{x['label']} {x['value']}" for x in s["stats"]))

    print("\n" + "=" * 74)
    print(f"실패 {len(FAILS)}건" + ("" if not FAILS else ": " + ", ".join(FAILS)))
    print("=" * 74)
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
