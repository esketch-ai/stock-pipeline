"""저장된 제작 자산으로 렌더링 + QC. LLM/TTS 재호출 및 게시 없음."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import archive
import config
import stage4_render
import stage5_publish


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=config.DATA_DIR / "audio_manifest.json")
    parser.add_argument("--tickers", help="쉼표로 구분한 종목 코드 (생략하면 manifest 전체)")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.tickers:
        wanted = [t.strip() for t in args.tickers.split(",") if t.strip()]
        missing = set(wanted) - manifest.keys()
        if missing:
            parser.error(f"manifest에 없는 종목: {sorted(missing)}")
        manifest = {t: manifest[t] for t in wanted}
    if not manifest:
        parser.error("렌더링할 항목이 없습니다.")
    for ticker, item in manifest.items():
        if not Path(item.get("audio", "")).is_file():
            parser.error(f"{ticker}: 음성 파일 없음")
        if not item.get("timestamps"):
            parser.error(f"{ticker}: 자막 타임스탬프 없음")
    print(f"실제 영상 {len(manifest)}편 렌더링 → {config.OUTPUT_DIR}", flush=True)
    videos = stage4_render.render(manifest)
    results = stage5_publish.run_qc(videos)
    report = config.DATA_DIR / "local_render_qc.json"
    report.write_text(json.dumps(archive._jsonable(results), ensure_ascii=False, indent=2), encoding="utf-8")
    for result in results:
        print(f"{'PASS' if result.ok else 'FAIL'} {result.path} ({result.duration:.1f}초)", flush=True)
    return 0 if len(results) == len(manifest) and all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
