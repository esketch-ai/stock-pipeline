"""단계 5 — 파일 무결성 QC(ffprobe) + YouTube Data API 예약 발행 + 7일 디스크 클린업."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
from config import CACHE_DIR, OUTPUT_DIR, STATE_DIR
from googleapiclient.http import MediaFileUpload
from logger import log
from video_files import video_ticker

RETENTION_DAYS = 7


@dataclass
class QCResult:
    path: Path
    ok: bool
    duration: float
    width: int
    height: int
    size_mb: float
    reason: str


def probe(video: Path) -> QCResult:
    """ffprobe 로 무결성 검증. 재생 불가능·해상도 불일치·용량 이상을 검출."""
    if not video.exists():
        return QCResult(video, False, 0, 0, 0, 0, "파일 없음")

    size_mb = video.stat().st_size / (1024 * 1024)
    if size_mb < 1:
        return QCResult(video, False, 0, 0, 0, size_mb, "파일 크기 비정상 (<1MB)")

    if not shutil.which("ffprobe"):
        return QCResult(video, False, 0, 0, 0, size_mb, "ffprobe 미설치")

    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,duration:format=duration",
             "-of", "json", str(video)],
            capture_output=True, text=True, check=True,
        )
        data = json.loads(proc.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        return QCResult(video, False, 0, 0, 0, size_mb, f"ffprobe 실패: {exc}")

    streams = data.get("streams", [])
    if not streams:
        return QCResult(video, False, 0, 0, 0, size_mb, "비디오 스트림 없음")

    s = streams[0]
    width, height = int(s.get("width", 0)), int(s.get("height", 0))
    duration = float(data.get("format", {}).get("duration", 0))

    if width == 0 or height == 0:
        return QCResult(video, False, duration, width, height, size_mb, "해상도 판독 불가")
    if duration < 10:
        return QCResult(video, False, duration, width, height, size_mb, "길이가 너무 짧음 (<10s)")

    expected = config.resolution()
    if (width, height) != expected:
        return QCResult(video, False, duration, width, height, size_mb, f"해상도 불일치 (기대 {expected[0]}x{expected[1]})")

    return QCResult(video, True, duration, width, height, size_mb, "OK")


def run_qc(videos: list[Path]) -> list[QCResult]:
    results = [probe(v) for v in videos]
    for r in results:
        level = "✔" if r.ok else "✖"
        log.info("%s QC %s — %s (%.1fMB, %.1fs, %dx%d)",
                 level, r.path.name, r.reason, r.size_mb, r.duration, r.width, r.height)
    passed = [r.path for r in results if r.ok]
    log.info("QC 결과: %d/%d 통과", len(passed), len(results))
    return results


# ── YouTube ─────────────────────────────────────────────

def _youtube_service():
    import google.auth.transport.requests
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = None
    if config.YOUTUBE_TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(config.YOUTUBE_TOKEN_PATH))

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(google.auth.transport.requests.Request())
        config.YOUTUBE_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        config.YOUTUBE_TOKEN_PATH.chmod(0o600)

    if not creds or not creds.valid:
        raise RuntimeError(
            "YouTube OAuth 토큰이 없거나 만료되었습니다. "
            f"{config.YOUTUBE_TOKEN_PATH} 확인 또는 token_auth.py 를 1회 실행하세요."
        )

    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _next_day_2am() -> datetime:
    """다음 날 02:00 KST 예약 시각."""
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    target = (now + timedelta(days=1)).replace(hour=2, minute=0, second=0, microsecond=0)
    return target


def publish(video: Path, title: str, description: str, tags: list[str],
            immediate: bool = False) -> str | None:
    """YouTube Data API v3 로 예약/즉시 게시. 실패 시 None.

    immediate=True 이면 예약 없이 지금 바로 게시한다.
    (private 공개는 검토 후 수동 공개하는 용도이므로 예약이 의미 없다)
    """
    if not config.YOUTUBE_CLIENT_ID or not config.YOUTUBE_CLIENT_SECRET:
        log.error("YouTube 자격증명 미설정 (.env 의 YOUTUBE_CLIENT_ID/SECRET 확인)")
        return None

    service = _youtube_service()

    body = {
        "snippet": {
            "title": title[:100],
            "description": (description + "\n\n#이 영상은 투자 권유가 아니며, 투자 판단과 책임은 본인에게 있습니다.")[:5000],
            "tags": tags[:30],
            "categoryId": "27",  # Education
        },
        "status": {"privacyStatus": config.YOUTUBE_VISIBILITY, "selfDeclaredMadeForKids": False},
    }

    # 예약은 public/unlisted 에서만 의미가 있다.
    # private 은 예약해도 공개되지 않으므로 즉시 게시로 처리한다.
    schedule = config.YOUTUBE_SCHEDULE_ENABLED and not immediate
    if schedule and config.YOUTUBE_VISIBILITY != "private":
        when = _next_day_2am()
        body["status"]["publishAt"] = when.astimezone(timezone.utc).isoformat()
        log.info("예약 게시: %s (%s KST)", video.name, when.strftime("%Y-%m-%d %H:%M"))
    else:
        log.info("즉시 게시 (%s): %s", config.YOUTUBE_VISIBILITY, video.name)

    try:
        # media_body 는 str 경로여야 한다 (Path 를 넘기면 'must be str or MediaUpload' 오류).
        # 대용량(수백 MB) 업로드에는 MediaFileUpload 로 청크/재개 지원을 켠다.
        media = MediaFileUpload(
            str(video),
            mimetype="video/mp4",
            chunksize=8 * 1024 * 1024,
            resumable=True,
        )
        request = service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )
        response = request.execute()
        log.info("✔ YouTube 게시 완료: %s (id=%s)", video.name, response["id"])
        return response["id"]
    except Exception as exc:
        log.error("✖ YouTube 게시 실패 %s: %s", video.name, exc)
        return None


def build_description(meta: dict, ticker: str) -> str:
    """대본 전체로 영상 설명서를 구성한다."""
    name = meta.get("name", ticker)
    hook = meta.get("hook", "")
    body = meta.get("body") or []
    closing = meta.get("closing", "")

    lines = [hook] if hook else []
    if body:
        lines.append("")
        lines.append("📌 오늘의 포인트")
        lines.extend(f"{i}. {b}" for i, b in enumerate(body, 1))
    if closing:
        lines.append("")
        lines.append(closing)
    lines.append("")
    lines.append(f"▪ 종목: {name} ({ticker})")
    lines.append("▪ 데이터 출처: 한국거래소(KRX)")
    return "\n".join(lines)


def publish_all(qc_results: list[QCResult], scripts_meta: dict[str, dict]) -> dict[str, str]:
    """QC 통과분만 게시."""
    published: dict[str, str] = {}
    for result in qc_results:
        if not result.ok:
            continue
        ticker = video_ticker(result.path)
        meta = scripts_meta.get(ticker, {})
        script = meta.get("script", meta)
        name = script.get("name") or meta.get("name") or ticker
        title = f"{name} 주가 분석 | {datetime.now().strftime('%Y-%m-%d')}"
        tags = ["한국주식", "주가분석", name, "투자정보", "stock", "코스피"]

        video_id = publish(result.path, title, build_description(script, ticker), tags)
        if video_id:
            published[ticker] = video_id
            result.path.with_suffix(".published").write_text(video_id, encoding="utf-8")
    return published


# ── 클린업 ─────────────────────────────────────────────

def cleanup(retention_days: int = RETENTION_DAYS) -> dict[str, int]:
    """output/ cache/ 에서 경과 일자를 지난 파일을 삭제한다. 게시 완료본은 보존."""
    removed = {"output": 0, "cache": 0}
    cutoff = time.time() - retention_days * 86400

    for video in OUTPUT_DIR.glob("*.mp4"):
        if video.with_suffix(".published").exists():
            continue  # 게시 완료 영상은 아카이브
        if video.stat().st_mtime < cutoff:
            video.unlink(missing_ok=True)
            removed["output"] += 1

    for item in CACHE_DIR.iterdir():
        if item.is_dir() and item.stat().st_mtime < cutoff:
            shutil.rmtree(item, ignore_errors=True)
            removed["cache"] += 1

    log.info("디스크 클린업: output %d건, cache %d건 제거 (%d일 경과)",
             removed["output"], removed["cache"], retention_days)
    return removed
