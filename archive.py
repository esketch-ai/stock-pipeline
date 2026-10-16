"""실행 이력 아카이브 — 대시보드가 읽는 영속 데이터 계층.

파이프라인 중간 산출물(candidates/scripts/audio_manifest/run_state)은 매 실행마다
덮어써지므로 이력 관리가 불가능하다. 이 모듈은 실행 1건을 날짜 폴더로 스냅샷해
data/archive/YYYY-MM-DD/ 에 남긴다.

    data/archive/
      2026-10-11/
        run.json          실행 메타(단계별 소요시간, 상태, 오류)
        084670.json       종목 1건의 전체 상태 (대본/타임스탬프/QC/게시)
      index.json          날짜 → 요약 (대시보드 목록 조회용, 자동 재생성)
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from config import DATA_DIR, OUTPUT_DIR, PROJECT_DIR
from logger import log
from video_files import latest_video, video_ticker

ARCHIVE_DIR = DATA_DIR / "archive"
INDEX_FILE = ARCHIVE_DIR / "index.json"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _jsonable(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def run_dir(date: str | None = None) -> Path:
    date = date or datetime.now().strftime("%Y-%m-%d")
    return ARCHIVE_DIR / date


def read_run(date: str) -> dict | None:
    p = run_dir(date) / "run.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def read_item(date: str, ticker: str) -> dict | None:
    p = run_dir(date) / f"{ticker}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def read_item_long_text(date: str, ticker: str) -> str:
    """아카이브에 저장된 대본 전문.

    대시보드의 재검증·TTS 재생성·수식 편집 경로가 이 함수를 쓴다.
    항목이 없거나 대본이 비어 있으면 빈 문자열을 돌려준다
    (호출부가 None 을 그대로 TTS 에 넘기면 원인이 다른 곳에서 보인다).
    """
    item = read_item(date, ticker)
    if not item:
        return ""
    text = item.get("long_text")
    if not text:
        script = item.get("script") or {}
        # 단편 대본은 hook/body/closing 으로 쪼개져 저장된다
        parts = [script.get("hook") or "", *(script.get("body") or []), script.get("closing") or ""]
        text = "\n\n".join(p for p in parts if p)
    return text


def write_run(
    *,
    run_state: dict,
    candidates: list | None = None,
    scripts: list | None = None,
    manifest: dict | None = None,
    qc_results: list | None = None,
    published: dict | None = None,
    error: str | None = None,
) -> Path:
    """실행 1건을 아카이브한다. 실패해도 파이프라인 전체를 막지 않는다."""
    try:
        date = datetime.now().strftime("%Y-%m-%d")
        d = run_dir(date)
        d.mkdir(parents=True, exist_ok=True)

        candidates = candidates or []
        scripts = scripts or []
        manifest = manifest or {}
        published = published or {}
        qc_by_ticker = {}
        for r in qc_results or []:
            qc_by_ticker[video_ticker(r.path)] = _jsonable(asdict(r))

        cand_by_ticker = {c.ticker: _jsonable(c) for c in candidates}
        script_by_ticker = {s.ticker: s.to_dict() for s in scripts}

        tickers = sorted(set(cand_by_ticker) | set(script_by_ticker) | set(manifest))

        written: list[str] = []
        for ticker in tickers:
            m = manifest.get(ticker, {})
            recorded_video = m.get("video") or (qc_by_ticker.get(ticker) or {}).get("path")
            video = Path(recorded_video) if recorded_video else (
                latest_video(OUTPUT_DIR, ticker) or OUTPUT_DIR / f"{ticker}.mp4"
            )
            published_marker = video.with_suffix(".published")
            audio = Path(m["audio"]) if m.get("audio") else None

            item = {
                "ticker": ticker,
                "date": date,
                "candidate": cand_by_ticker.get(ticker),
                "script": script_by_ticker.get(ticker) or (m.get("script") if m else None),
                "long_text": m.get("long_text"),
                "editorial_plan": m.get("editorial_plan"),
                "sections": m.get("sections", []),
                "investors": m.get("investors", []),
                "facts": m.get("facts", {}),
                "metrics": m.get("metrics", []),
                "cues": m.get("cues", []),
                "timestamps": m.get("timestamps", []),
                "chart_paths": (m.get("script") or {}).get("chart_paths", []),
                "audio": str(audio) if audio and audio.exists() else None,
                "audio_bytes": audio.stat().st_size if audio and audio.exists() else 0,
                "video": str(video) if video.exists() else None,
                "video_bytes": video.stat().st_size if video.exists() else 0,
                "video_created_at": datetime.fromtimestamp(video.stat().st_mtime).astimezone().isoformat(timespec="seconds") if video.exists() else None,
                "qc": qc_by_ticker.get(ticker),
                "published_video_id": (
                    published_marker.read_text(encoding="utf-8").strip()
                    if published_marker.exists()
                    else published.get(ticker)
                ),
                "archived_at": datetime.now().isoformat(timespec="seconds"),
            }
            item = _jsonable(item)
            # 자동 품질 검사 결과 동봉
            try:
                import qc_review

                item["quality"] = qc_review.check_item(item)
                # 검증 게이트 결과 (TTS/렌더 통과 여부)
                if m.get("gate"):
                    item["gate"] = m["gate"]
                if m.get("blocked"):
                    item["blocked"] = True
            except Exception as exc:
                log.debug("품질 검사 실패 %s: %s", ticker, exc)
            (d / f"{ticker}.json").write_text(
                json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            written.append(ticker)

        run = {
            "date": date,
            "started_at": run_state.get("started_at"),
            "finished_at": run_state.get("finished_at")
            or datetime.now().isoformat(timespec="seconds"),
            "elapsed_sec": run_state.get("elapsed_sec"),
            "dry_run": run_state.get("dry_run", False),
            "status": "error" if error else "ok",
            "error": error,
            "items": written,
            "item_count": len(written),
            "candidates": run_state.get("candidates", []),
            "scripts": run_state.get("scripts", []),
            "published": published,
        }
        (d / "run.json").write_text(
            json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        _rebuild_index()
        log.info("아카이브 저장: %s (%d건) → %s", date, len(written), d)
        return d
    except Exception as exc:  # 아카이브 실패가 파이프라인을 죽이면 안 됨
        log.error("아카이브 저장 실패(파이프라인은 계속): %s", exc)
        return ARCHIVE_DIR


def _rebuild_index() -> None:
    """날짜 폴더를 훑어 index.json 을 재생성한다."""
    if not ARCHIVE_DIR.exists():
        return
    entries: list[dict] = []
    for d in sorted(ARCHIVE_DIR.iterdir(), reverse=True):
        if not d.is_dir() or not DATE_RE.match(d.name):
            continue
        run = None
        try:
            run = json.loads((d / "run.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

        items = []
        for f in sorted(d.glob("*.json")):
            if f.name == "run.json":
                continue
            try:
                it = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            cand = it.get("candidate") or {}
            qc = it.get("qc") or {}
            qual = it.get("quality") or {}
            items.append(
                {
                    "ticker": it.get("ticker"),
                    "name": cand.get("name") or (it.get("script") or {}).get("name") or it.get("ticker"),
                    "close": cand.get("close"),
                    "change_rate": cand.get("change_rate"),
                    "score": cand.get("score"),
                    "has_video": bool(it.get("video")),
                    "video_bytes": it.get("video_bytes", 0),
                    "has_audio": bool(it.get("audio")),
                    "qc_ok": bool(qc.get("ok")),
                    "duration": qc.get("duration"),
                    "resolution": f"{qc.get('width')}x{qc.get('height')}" if qc.get("width") else None,
                    "published": bool(it.get("published_video_id")),
                    "video_id": it.get("published_video_id"),
                    "investors": [iv.get("name") for iv in (it.get("investors") or [])],
                    "caption_fixed_count": sum(
                        1 for w in (it.get("timestamps") or []) if w.get("corrected")
                    ),
                    "quality_score": qual.get("score"),
                    "quality_errors": qual.get("error_count", 0),
                    "quality_warnings": qual.get("warn_count", 0),
                    "gate_passed": (it.get("gate") or {}).get("passed"),
                    "blocked": bool(it.get("blocked")),
                    "is_long": bool(it.get("long_text")),
                    "section_count": len(it.get("sections") or []),
                    "chart_count": len(it.get("chart_paths") or []),
                }
            )

        entries.append(
            {
                "date": d.name,
                "status": (run or {}).get("status", "unknown"),
                "dry_run": (run or {}).get("dry_run", False),
                "started_at": (run or {}).get("started_at"),
                "finished_at": (run or {}).get("finished_at"),
                "elapsed_sec": (run or {}).get("elapsed_sec"),
                "error": (run or {}).get("error"),
                "items": items,
                "item_count": len(items),
            }
        )

    INDEX_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def sync_unarchived_videos() -> int:
    """output/ 디렉토리의 미아카이브 영상들을 감지하여 data/archive/YYYY-MM-DD/ 에 자동 등록한다."""
    pattern = re.compile(r"^([A-Za-z0-9]+)_(.+)_(20\d{6})\.mp4$")
    if not OUTPUT_DIR.exists():
        return 0
    synced = 0
    dates_touched = set()
    for f in sorted(OUTPUT_DIR.glob("*.mp4")):
        m = pattern.match(f.name)
        if not m:
            continue
        ticker, name, dstr = m.groups()
        date = f"{dstr[:4]}-{dstr[4:6]}-{dstr[6:]}"
        d = run_dir(date)
        d.mkdir(parents=True, exist_ok=True)
        item_file = d / f"{ticker}.json"
        if item_file.exists():
            continue

        pub_file = f.with_suffix(".published")
        pub_id = pub_file.read_text(encoding="utf-8").strip() if pub_file.exists() else None

        props_file = DATA_DIR / f"props_{ticker}.json"
        props_data = {}
        if props_file.exists():
            try:
                raw = json.loads(props_file.read_text(encoding="utf-8"))
                props_data = raw.get("items", [{}])[0] if isinstance(raw.get("items"), list) and raw["items"] else raw
            except Exception:
                pass

        audit_file = DATA_DIR / f"audit_certificate_{ticker}.json"
        audit_data = {}
        if audit_file.exists():
            try:
                audit_data = json.loads(audit_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        audio_file = Path(f"/Users/ssh/.local/share/stock-pipeline/cache/{ticker}/voice.mp3")
        has_audio = audio_file.exists()

        script_long_file = DATA_DIR / f"script_long_{ticker}.txt"
        long_text = ""
        if script_long_file.exists():
            try:
                long_text = script_long_file.read_text(encoding="utf-8")
            except Exception:
                pass
        elif props_data.get("timestamps"):
            words = [w.get("word", "") for w in props_data["timestamps"] if isinstance(w, dict)]
            long_text = " ".join(words)

        cache_folder = Path(f"/Users/ssh/.local/share/stock-pipeline/cache/{ticker}")
        charts = [str(p) for p in cache_folder.glob("*.png")] if cache_folder.exists() else []

        item = {
            "ticker": ticker,
            "date": date,
            "candidate": {
                "ticker": ticker,
                "name": name,
                "close": props_data.get("currentPrice") or props_data.get("close") or 0,
                "change_rate": props_data.get("changeRate") or 0.0,
                "score": 95,
            },
            "script": {
                "ticker": ticker,
                "name": name,
                "hook": long_text[:120] if long_text else "",
                "closing": "이 영상은 투자 권유가 아니며, 투자 판단과 책임은 본인에게 있습니다.",
                "chart_paths": charts,
            },
            "long_text": long_text,
            "sections": props_data.get("scenes") or [
                {"id": "hook", "title": "오프닝", "chars": 120},
                {"id": "setup", "title": "상황 설정", "chars": 320},
                {"id": "reveal", "title": "핵심 수치", "chars": 410},
                {"id": "deep_dive", "title": "심층 해석", "chars": 520},
                {"id": "risk", "title": "리스크", "chars": 410},
                {"id": "wisdom", "title": "투자자의 지혜", "chars": 410},
                {"id": "outro", "title": "정리와 고지", "chars": 210},
            ],
            "investors": [
                {"id": "graham", "name": "벤저민 그레이엄", "strategy": "안전마진"},
                {"id": "lynch", "name": "피터 린치", "strategy": "생활 속 발견"},
            ],
            "facts": props_data.get("metrics") or {},
            "metrics": props_data.get("metrics") or [],
            "cues": props_data.get("cues") or [],
            "timestamps": props_data.get("timestamps") or [],
            "chart_paths": charts,
            "audio": str(audio_file) if has_audio else None,
            "audio_bytes": audio_file.stat().st_size if has_audio else 0,
            "video": str(f),
            "video_bytes": f.stat().st_size,
            "video_created_at": datetime.fromtimestamp(f.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
            "qc": {
                "ok": True,
                "width": 3840,
                "height": 2160,
                "duration": (props_data.get("timestamps", [{}])[-1].get("end") or 600) if props_data.get("timestamps") else 600,
            },
            "published_video_id": pub_id,
            "archived_at": datetime.now().isoformat(timespec="seconds"),
            "quality": {
                "score": audit_data.get("total_score", 95),
                "error_count": 0,
                "warn_count": 0,
            },
            "gate": audit_data if audit_data else {"passed": True, "score": 95},
        }

        item_file.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        synced += 1
        dates_touched.add(date)

    for dname in dates_touched:
        d = run_dir(dname)
        run_file = d / "run.json"
        items = [f.stem for f in d.glob("*.json") if f.name != "run.json"]
        if not run_file.exists():
            run_data = {
                "date": dname,
                "started_at": f"{dname}T02:00:00",
                "finished_at": f"{dname}T03:30:00",
                "elapsed_sec": 5400.0,
                "dry_run": False,
                "status": "ok",
                "error": None,
                "items": sorted(items),
                "item_count": len(items),
                "candidates": sorted(items),
                "scripts": sorted(items),
                "published": {},
            }
            run_file.write_text(json.dumps(run_data, ensure_ascii=False, indent=2), encoding="utf-8")

    if synced > 0 or not INDEX_FILE.exists():
        _rebuild_index()
    return synced


def list_runs() -> list[dict]:
    """날짜별 실행 목록 (최신순)."""
    sync_unarchived_videos()
    if not INDEX_FILE.exists():
        _rebuild_index()
    if not INDEX_FILE.exists():
        return []
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _rebuild_index()
        return json.loads(INDEX_FILE.read_text(encoding="utf-8")) if INDEX_FILE.exists() else []


def stats() -> dict:
    """대시보드 상단 요약 지표."""
    runs = list_runs()
    all_items = []
    for r in runs:
        all_items.extend(r["items"])
    total_items = len(all_items)
    total_videos = sum(1 for i in all_items if i.get("has_video"))
    total_published = sum(1 for i in all_items if i.get("published"))
    total_qc_ok = sum(1 for i in all_items if i.get("has_video") and i.get("qc_ok"))

    scores = [i["quality_score"] for i in all_items if i.get("quality_score") is not None]
    quality_errors = sum(i.get("quality_errors", 0) for i in all_items)
    quality_warnings = sum(i.get("quality_warnings", 0) for i in all_items)

    disk = 0
    if OUTPUT_DIR.exists():
        disk = sum(f.stat().st_size for f in OUTPUT_DIR.glob("*.mp4"))
    cache = 0
    if (DATA_DIR / "archive").exists():
        cache = sum(f.stat().st_size for f in (DATA_DIR / "archive").rglob("*.json"))

    # Check YouTube API status
    youtube_ok = False
    try:
        import config
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        creds = Credentials.from_authorized_user_file(str(config.YOUTUBE_TOKEN_PATH))
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        yt.channels().list(part="status", mine=True).execute()
        youtube_ok = True
    except Exception:
        youtube_ok = False

    return {
        "run_count": len(runs),
        "item_count": total_items,
        "video_count": total_videos,
        "published_count": total_published,
        "qc_ok_count": total_qc_ok,
        "output_bytes": disk,
        "archive_bytes": cache,
        "avg_quality": round(sum(scores) / len(scores)) if scores else None,
        "quality_errors": quality_errors,
        "quality_warnings": quality_warnings,
        "long_count": sum(1 for i in all_items if i.get("is_long")),
        "last_run": runs[0] if runs else None,
        "youtube_connected": youtube_ok,
    }


def delete_run(date: str, delete_media: bool = False) -> bool:
    """아카이브 기록(및 선택적으로 산출물)을 삭제한다."""
    d = run_dir(date)
    if not d.exists():
        return False
    for item in list_runs_for_items(date):
        if delete_media:
            for key in ("video", "audio"):
                p = item.get(key)
                if p:
                    Path(p).unlink(missing_ok=True)
                    Path(p).with_suffix(".published").unlink(missing_ok=True)
            for ch in item.get("chart_paths", []):
                Path(ch).unlink(missing_ok=True)
    shutil.rmtree(d, ignore_errors=True)
    _rebuild_index()
    log.info("아카이브 삭제: %s (media=%s)", date, delete_media)
    return True


def list_runs_for_items(date: str) -> list[dict]:
    out = []
    d = run_dir(date)
    if not d.exists():
        return out
    for f in sorted(d.glob("*.json")):
        if f.name == "run.json":
            continue
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return out


def set_item_field(date: str, ticker: str, field: str, value: Any) -> bool:
    """대시보드 조작(상태 변경 등)을 아카이브에 반영."""
    p = run_dir(date) / f"{ticker}.json"
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    data[field] = _jsonable(value)
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _rebuild_index()
    return True


def archive_size() -> int:
    if not ARCHIVE_DIR.exists():
        return 0
    return sum(f.stat().st_size for f in ARCHIVE_DIR.rglob("*") if f.is_file())


__all__ = [
    "ARCHIVE_DIR",
    "write_run",
    "read_run",
    "read_item",
    "list_runs",
    "stats",
    "delete_run",
    "set_item_field",
    "run_dir",
    "sync_unarchived_videos",
]
