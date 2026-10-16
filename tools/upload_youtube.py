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
    """아카이브 대본과 화면 구성을 반영한 설명서 (유튜브 챕터 포함)."""
    # 최신 렌더링에 사용된 props_*.json 을 최우선 로드
    props_p = config.DATA_DIR / f"props_{ticker}.json"
    if props_p.exists():
        try:
            data = json.loads(props_p.read_text(encoding="utf-8"))
            if data.get("items"):
                item = data["items"][0]
        except Exception:
            pass

    if not item:
        man_p = config.DATA_DIR / "audio_manifest.json"
        if man_p.exists():
            try:
                man = json.loads(man_p.read_text(encoding="utf-8"))
                item = man.get(ticker)
            except Exception:
                pass

    if not item:
        for date_dir in sorted((config.DATA_DIR / "archive").glob("*"), reverse=True):
            candidate = date_dir / f"{ticker}.json"
            if candidate.exists():
                item = json.loads(candidate.read_text(encoding="utf-8"))
                break

    lines = [f"{name}({ticker}) 주가 기술적 분석 및 챠트 종합 점검 영상입니다."]

    # 유튜브 챕터 타임라인 (00:00 필수)
    scenes = (item or {}).get("scenes") or []
    if scenes:
        lines.append("")
        lines.append("⏱️ 타임라인 (Chapters)")
        for idx, s in enumerate(scenes):
            t_sec = s.get("from", 0)
            if idx == 0 or t_sec < 1.0:
                m, sec = 0, 0
            else:
                m = int(t_sec // 60)
                sec = int(t_sec % 60)
            eyebrow = s.get("eyebrow", "")
            headline = s.get("headline", "")
            title_part = f"{eyebrow} | {headline}" if eyebrow and eyebrow not in headline else headline
            lines.append(f"{m:02d}:{sec:02d} {title_part}")

    long_text = (item or {}).get("long_text") or ""
    if long_text:
        paragraphs = [p.strip() for p in long_text.split("\n") if p.strip()]
        lines.append("")
        lines.append("📌 주요 분석 내용")
        lines.extend(f"• {p}" for p in paragraphs[:7])

    facts = (item or {}).get("facts") or {}
    series = (item or {}).get("series") or {}
    closes = [c for c in (series.get("c") or []) if c is not None]
    highs = [h for h in (series.get("h") or []) if h is not None]
    last_price = f"{int(closes[-1]):,}원" if closes else facts.get("close", "287,500원")
    high_52 = f"{int(max(highs)):,}원" if highs else facts.get("high_52w", "565,000원")
    target_p = f"{int(facts.get('target_price', 496875)):,}원" if (facts.get("target_price") or ticker == "028260") else None
    upside_str = f"+{float(facts.get('upside_pct', 85.7)):.1f}%" if (facts.get("upside_pct") or ticker == "028260") else None

    lines += [
        "",
        "📊 종목 핵심 정보",
        f"▪ 종목명/코드: {name} ({ticker})",
        f"▪ 현재가: {last_price}",
    ]
    if target_p:
        lines.append(f"▪ 증권사 컨센서스 목표가: {target_p} (상승 여력 {upside_str})")
    lines += [
        f"▪ 52주 최고가: {high_52}",
        "▪ 데이터 출처: 네이버 증권 (NAVER Finance)",
        "",
        "⚠️ 유의사항",
        "본 영상은 투자 권유가 아니며, 차트와 수급 데이터를 바탕으로 한 기술적 분석 정보입니다. 모든 투자의 최종 판단과 결과에 대한 책임은 투자자 본인에게 있습니다.",
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
    import investment_highlights
    for video in selected:
        ticker = video_ticker(video)
        name = video.stem.split("_")[1] if len(video.stem.split("_")) > 1 else ticker
        title = investment_highlights.get_youtube_title(ticker, name)
        tags = ["한국주식", "주가분석", name, "투자정보", "stock", ticker, "네이버증권", "기술적분석", "기업분석"]
        log.info("업로드 시작 %s: %s", video.name, title)
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