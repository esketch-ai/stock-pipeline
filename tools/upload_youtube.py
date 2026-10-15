"""QC 통과 영상 YouTube 업로드 (기본 비공개).

사용 방법:
    venv/bin/python tools/upload_youtube.py 015260 002820 014990
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
import stage5_publish as s5  # noqa: E402
from logger import log  # noqa: E402
from video_files import video_ticker  # noqa: E402


def build_description(video: Path, ticker: str, name: str) -> str:
    """아카이브 대본과 화면 구성을 반영한 설명서."""
    item = None
    for date_dir in sorted((config.DATA_DIR / "archive").glob("*"), reverse=True):
        candidate = date_dir / f"{ticker}.json"
        if candidate.exists():
            item = json.loads(candidate.read_text(encoding="utf-8"))
            break

    lines = [f"{name}({ticker}) 주가 분석입니다."]
    long_text = (item or {}).get("long_text") or ""
    if long_text:
        paragraphs = [p.strip() for p in long_text.split("\n") if p.strip()]
        lines.append("")
        lines.append("📌 오늘의 요약")
        lines.extend(f"{i}. {p}" for i, p in enumerate(paragraphs[:8], 1))
    facts = (item or {}).get("facts") or {}
    lines += [
        "",
        f"▪ 현재가: {facts.get('close', '-')} ({facts.get('change_rate', '-')})",
        f"▪ 시가총액: {facts.get('market_cap', '-')}",
        f"▪ 52주 신고가: {facts.get('high_52w', '-')} (신고가 대비 {facts.get('from_high', '-')})",
        f"▪ 데이터 출처: 한국거래소(KRX), {facts.get('trading_day', '-')}",
        "",
        "본 영상은 투자 권유가 아닙니다. 투자 판단과 그 결과에 대한 책임은 본인에게 있습니다.",
    ]
    contact = config.PROJECT_DIR / "contact.txt"
    if contact.exists() and (raw := contact.read_text(encoding="utf-8", errors="replace")):
        phone = next((line.split(":", 1)[1].strip() for line in raw.splitlines()
                      if line.lower().startswith("phone:") and ":" in line), "")
        if phone:
            lines.append(f"▪ 문의: {phone}")
    return "\n".join(lines)


def main() -> int:
    tickers = [t.strip() for t in sys.argv[1:]] or []
    videos = sorted(config.OUTPUT_DIR.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not videos:
        print("업로드할 영상이 없습니다.")
        return 1

    selected = [p for p in videos if not tickers or video_ticker(p) in tickers]
    selected = [p for p in selected if not p.with_suffix(".published").exists()][:len(tickers) or 3]
    if not selected:
        print("선택된 영상이 없습니다 (이미 게시되었거나 ticker 불일치).")
        return 1

    print(f"업로드 {len(selected)}편 · 공개 상태 {config.YOUTUBE_VISIBILITY}\n", flush=True)
    failed = []
    for video in selected:
        ticker = video_ticker(video)
        name = video.stem.split("_")[1] if len(video.stem.split("_")) > 1 else ticker
        title = f"{name} 주가 분석 | {datetime.now():%Y-%m-%d}"
        tags = ["한국주식", "주가분석", name, "투자정보", "stock", ticker]
        log.info("업로드 시작 %s", video.name)
        video_id = s5.publish(video, title, build_description(video, ticker, name), tags)
        if video_id:
            video.with_suffix(".published").write_text(video_id, encoding="utf-8")
            print(f"  ✔ {video.name}\n    https://youtu.be/{video_id}\n", flush=True)
        else:
            failed.append(video.name)
    print("실패:", failed if failed else "없음")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())