"""영상 파일명: 종목코드_종목명_생성일자(YYYYMMDD).mp4."""
import re
from datetime import datetime
from pathlib import Path


def video_filename(ticker: str, name: str, created: datetime | None = None) -> str:
    if not re.fullmatch(r"[A-Za-z0-9]+", ticker):
        raise ValueError(f"잘못된 종목코드: {ticker}")
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', name).strip().strip('.')
    if not safe_name:
        raise ValueError("종목명이 필요합니다.")
    date = (created or datetime.now()).strftime("%Y%m%d")
    return f"{ticker}_{safe_name}_{date}.mp4"


def video_ticker(path: Path) -> str:
    return Path(path).stem.split("_", 1)[0]


def latest_video(directory: Path, ticker: str) -> Path | None:
    paths = [p for p in directory.glob("*.mp4") if video_ticker(p) == ticker and p.is_file()]
    return max(paths, key=lambda p: p.stat().st_mtime_ns) if paths else None
