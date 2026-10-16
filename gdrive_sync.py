"""Google Drive 업로드 및 종목 영상 패키지 자동 동기화 모듈 (gdrive_sync.py).

새벽 2시 배치로 생성된 4K 영상 및 관련 모든 에셋(음성, 대본, 6대 애널리스트 감사서, 차트, 메타데이터)을
구글 드라이브의 계층형 폴더 구조로 안전하게 패키징하여 업로드/동기화합니다.
"""

from __future__ import annotations

import io
import json
import mimetypes
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import config
from logger import log
import archive
import investment_highlights
import market_evaluation
import analyst_board_audit

GDRIVE_TOKEN_PATH = config.STATE_DIR / "gdrive_token.json"
GDRIVE_FOLDER_NAME = config.env("GDRIVE_FOLDER_NAME", "주식챠트를뿌셔보까_아카이브")
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]


def is_authenticated() -> bool:
    """구글 드라이브 인증 토큰이 존재하고 유효한지 확인."""
    token_path = GDRIVE_TOKEN_PATH
    if not token_path.exists():
        # youtube_token.json이 drive scope를 포함하고 있는지 확인
        if config.YOUTUBE_TOKEN_PATH.exists():
            try:
                data = json.loads(config.YOUTUBE_TOKEN_PATH.read_text(encoding="utf-8"))
                scopes = data.get("scopes", [])
                if any("drive" in s for s in scopes):
                    token_path = config.YOUTUBE_TOKEN_PATH
                else:
                    return False
            except Exception:
                return False
        else:
            return False

    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(token_path), scopes=SCOPES)
        return bool(creds and (creds.valid or creds.refresh_token))
    except Exception:
        return False


def get_drive_service():
    """Google Drive v3 API 클라이언트 빌드."""
    import google.auth.transport.requests
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_path = GDRIVE_TOKEN_PATH
    if not token_path.exists() and config.YOUTUBE_TOKEN_PATH.exists():
        try:
            data = json.loads(config.YOUTUBE_TOKEN_PATH.read_text(encoding="utf-8"))
            if any("drive" in s for s in data.get("scopes", [])):
                token_path = config.YOUTUBE_TOKEN_PATH
        except Exception:
            pass

    if not token_path.exists():
        raise RuntimeError(
            f"Google Drive 인증 토큰이 없습니다. state/gdrive_token.json 생성이 필요합니다. "
            "대시보드 또는 tools/gdrive_auth.py 를 실행하세요."
        )

    creds = Credentials.from_authorized_user_file(str(token_path), scopes=SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(google.auth.transport.requests.Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
        token_path.chmod(0o600)

    if not creds.valid:
        raise RuntimeError("Google Drive 인증 토큰이 유효하지 않습니다. 재인증이 필요합니다.")

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def ensure_folder(service, folder_name: str, parent_id: Optional[str] = None) -> str:
    """지정된 이름의 폴더를 찾고, 없으면 생성하여 folder_id 반환."""
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    else:
        query += " and 'root' in parents"

    results = service.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name, webViewLink)",
        pageSize=1
    ).execute()

    files = results.get("files", [])
    if files:
        return files[0]["id"]

    # 생성
    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        metadata["parents"] = [parent_id]

    created = service.files().create(
        body=metadata,
        fields="id, name, webViewLink"
    ).execute()

    log.info("📁 [Google Drive] 새 폴더 생성: %s (id: %s)", folder_name, created.get("id"))
    return created.get("id")


def upload_single_file(
    service,
    file_path: Path,
    folder_id: str,
    progress_callback: Optional[Callable[[str, float], None]] = None
) -> Dict[str, Any]:
    """단일 파일을 지정된 구글 드라이브 폴더에 업로드."""
    from googleapiclient.http import MediaFileUpload

    file_name = file_path.name
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if not mime_type:
        if file_path.suffix == ".mp4":
            mime_type = "video/mp4"
        elif file_path.suffix == ".mp3":
            mime_type = "audio/mpeg"
        elif file_path.suffix == ".json":
            mime_type = "application/json"
        elif file_path.suffix in (".md", ".txt"):
            mime_type = "text/plain"
        elif file_path.suffix == ".png":
            mime_type = "image/png"
        else:
            mime_type = "application/octet-stream"

    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    # 기존 동일 파일 검색
    query = f"name = '{file_name}' and '{folder_id}' in parents and trashed = false"
    existing = service.files().list(q=query, fields="files(id, name)", pageSize=1).execute().get("files", [])

    body = {"name": file_name, "parents": [folder_id]}
    is_large = file_size_mb > 15.0  # 15MB 초과 시 resumable chunk upload

    media = MediaFileUpload(
        str(file_path),
        mimetype=mime_type,
        resumable=is_large,
        chunksize=10 * 1024 * 1024 if is_large else -1
    )

    if existing:
        file_id = existing[0]["id"]
        log.info("🔄 [Google Drive] 기존 파일 덮어쓰기: %s (id: %s)", file_name, file_id)
        updated = service.files().update(
            fileId=file_id,
            media_body=media,
            fields="id, name, webViewLink, size"
        ).execute()
        return updated

    log.info("⬆ [Google Drive] 파일 업로드 시작: %s (%.1fMB)", file_name, file_size_mb)
    if is_large:
        request = service.files().create(body=body, media_body=media, fields="id, name, webViewLink, size")
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status and progress_callback:
                progress_callback(file_name, status.progress())
        return response
    else:
        uploaded = service.files().create(body=body, media_body=media, fields="id, name, webViewLink, size").execute()
        if progress_callback:
            progress_callback(file_name, 1.0)
        return uploaded


def collect_stock_bundle(date: str, ticker: str) -> Dict[str, Any]:
    """특정 일자 및 종목의 모든 관련 파일 번들 수집."""
    bundle: Dict[str, Any] = {
        "ticker": ticker,
        "date": date,
        "name": ticker,
        "files": []
    }

    # 1. 아카이브에서 항목 정보 로드
    item = archive.read_item(date, ticker) or {}
    stock_name = item.get("name") or (item.get("script") or {}).get("name") or ticker
    bundle["name"] = stock_name

    bundle_dir = config.CACHE_DIR / ticker / "gdrive_bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # 2. 4K 비디오 파일 찾기
    video_candidates = [
        config.OUTPUT_DIR / f"{stock_name}_{ticker}_{date}.mp4",
        config.OUTPUT_DIR / f"video_{ticker}_4k.mp4",
        config.OUTPUT_DIR / f"{ticker}.mp4",
        Path(item.get("video")) if item.get("video") else None,
    ]
    # glob으로 검색
    video_candidates.extend(list(config.OUTPUT_DIR.glob(f"*{ticker}*.mp4")))
    found_video = next((p for p in video_candidates if p and p.exists() and p.stat().st_size > 1024 * 1024), None)
    if found_video:
        bundle["files"].append(found_video)

    # 3. 오디오 음성 파일
    audio_candidates = [
        config.CACHE_DIR / ticker / "voice.mp3",
        Path(item.get("audio")) if item.get("audio") else None,
    ]
    found_audio = next((p for p in audio_candidates if p and p.exists()), None)
    if found_audio:
        bundle["files"].append(found_audio)

    # 4. 8대 씬 스토리텔링 대본 텍스트
    long_text = item.get("long_text") or archive.read_item_long_text(date, ticker)
    if not long_text:
        txt_path = config.DATA_DIR / f"script_long_{ticker}.txt"
        if txt_path.exists():
            long_text = txt_path.read_text(encoding="utf-8")

    if long_text:
        script_file = bundle_dir / f"대본_8대씬_{stock_name}_{ticker}.txt"
        script_file.write_text(long_text, encoding="utf-8")
        bundle["files"].append(script_file)

    # 5. 6대 애널리스트 감사 인증서 마크다운 생성
    try:
        m = market_evaluation.build_market_evaluation_report(ticker, stock_name)
        import scenario_writer_30yr
        sections = scenario_writer_30yr.write_accessible_storytelling_script(m)
        audit_res = analyst_board_audit.audit_and_advise_script(ticker, stock_name, m, sections)
        audit_file = bundle_dir / f"6대애널리스트_감사보고서_{stock_name}_{ticker}.md"
        audit_file.write_text(audit_res.summary(), encoding="utf-8")
        bundle["files"].append(audit_file)
    except Exception as exc:
        log.warning("%s 감사 보고서 번들 생성 실패: %s", ticker, exc)

    # 6. 유튜브 및 메타데이터 JSON
    try:
        highlights = investment_highlights.get_highlights(ticker, stock_name)
        title_str = investment_highlights.get_youtube_title(ticker, stock_name)
        tags_list = ["주식", "주식차트", "주식챠트를뿌셔보까", stock_name, ticker]
        meta = {
            "title": title_str,
            "description": f"[주식 챠트를 뿌셔 보까] {stock_name}({ticker}) 주식 차트 및 6대 애널리스트 팩트 분석\n\n핵심 투자 포인트:\n" + "\n".join(f"- {p.get('icon', '')} {p.get('title', '')}: {p.get('desc', '')}" for p in highlights),
            "tags": tags_list,
            "keyPoints": highlights,
            "generated_at": datetime.now().isoformat(),
        }
        meta_file = bundle_dir / f"메타데이터_{stock_name}_{ticker}.json"
        meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        bundle["files"].append(meta_file)
    except Exception as exc:
        log.warning("%s 메타데이터 번들 생성 실패: %s", ticker, exc)

    # 7. 차트 이미지들
    cache_dir = config.CACHE_DIR / ticker
    if cache_dir.exists():
        for img in cache_dir.glob("*.png"):
            if not img.name.startswith("test_"):
                bundle["files"].append(img)

    return bundle


def sync_stock_bundle(
    service,
    date: str,
    ticker: str,
    progress_callback: Optional[Callable[[str, float], None]] = None
) -> Dict[str, Any]:
    """단일 종목의 전체 에셋 번들을 구글 드라이브에 업로드."""
    bundle = collect_stock_bundle(date, ticker)
    stock_name = bundle["name"]
    files = bundle["files"]

    if not files:
        raise ValueError(f"{stock_name}({ticker}) 관련 에셋 파일을 찾을 수 없습니다.")

    # 1. 루트 폴더 확보
    root_folder_id = ensure_folder(service, GDRIVE_FOLDER_NAME)

    # 2. 날짜별 서브폴더 확보 (YYYY-MM-DD)
    date_folder_id = ensure_folder(service, date, parent_id=root_folder_id)

    # 3. 종목별 서브폴더 확보 (삼성전자_005930)
    stock_folder_name = f"{stock_name}_{ticker}"
    stock_folder_id = ensure_folder(service, stock_folder_name, parent_id=date_folder_id)

    uploaded_files = []
    total = len(files)
    for idx, fpath in enumerate(files):
        def _cb(fname, p):
            if progress_callback:
                overall = (idx + p) / total
                progress_callback(f"{fname} ({int(p*100)}%)", overall)

        res = upload_single_file(service, fpath, stock_folder_id, progress_callback=_cb)
        uploaded_files.append({
            "name": fpath.name,
            "id": res.get("id"),
            "link": res.get("webViewLink")
        })

    folder_url = f"https://drive.google.com/drive/folders/{stock_folder_id}"
    log.info("🎉 [Google Drive] %s(%s) 전체 에셋 %d개 업로드 완료: %s", stock_name, ticker, len(uploaded_files), folder_url)

    return {
        "ticker": ticker,
        "name": stock_name,
        "date": date,
        "folder_id": stock_folder_id,
        "folder_url": folder_url,
        "files_count": len(uploaded_files),
        "files": uploaded_files
    }


def batch_sync_to_gdrive(
    date: str,
    tickers: List[str],
    job_updater: Optional[Callable[[str, str], None]] = None
) -> Dict[str, Any]:
    """선택한 종목 리스트의 모든 영상 에셋을 구글 드라이브로 일괄 전송."""
    service = get_drive_service()
    results = []
    errors = []

    total_stocks = len(tickers)
    for idx, ticker in enumerate(tickers):
        stock_label = f"[{idx+1}/{total_stocks}] {ticker}"
        if job_updater:
            job_updater("업로드 진행 중", f"{stock_label} 에셋 수집 및 Google Drive 전송 중...")

        try:
            res = sync_stock_bundle(service, date, ticker)
            results.append(res)
            log.info("✔ %s Google Drive 전송 완료", stock_label)
        except Exception as exc:
            log.error("✖ %s Google Drive 전송 실패: %s", stock_label, exc)
            errors.append({"ticker": ticker, "error": str(exc)})

    if job_updater:
        job_updater("완료", f"총 {len(results)}/{total_stocks} 종목 Google Drive 전송 성공")

    return {
        "date": date,
        "success_count": len(results),
        "total_count": total_stocks,
        "results": results,
        "errors": errors,
        "gdrive_root_folder": GDRIVE_FOLDER_NAME
    }
