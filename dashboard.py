"""관리 대시보드 — stock-pipeline 운영용 FastAPI 서버.

    venv/bin/python3 dashboard.py
    → http://127.0.0.1:8787  (127.0.0.1 바인딩 전용)

설계 원칙
    1. 수 분~수십 분 걸리는 작업(배치·렌더·TTS)은 동기 요청으로 두지 않는다.
       백그라운드 작업(Job)으로 등록하고 상태만 폴링한다.
    2. 게시(YouTube 업로드)는 사용자가 명시적으로 눌러야만 일어난다.
       재렌더·재빌드가 절대 게시까지 이어지지 않는다.
    3. 화면은 어떤 API 가 실패해도 빈 화면이 되지 않는다 —
       부분 실패는 해당 영역에만 표시한다.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import threading
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import archive
import config
from config import PROJECT_DIR
from logger import log

app = FastAPI(title="stock-pipeline Admin", version="2.0")

THUMB_DIR = config.CACHE_DIR / "_thumbs"
THUMB_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(PROJECT_DIR / "static")), name="static")
app.mount("/followup", StaticFiles(directory=str(PROJECT_DIR / "public-dashboard"), html=True), name="followup")

_TICKER_RE = re.compile(r"^[A-Za-z0-9_.-]{1,20}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _check_date(date: str) -> str:
    if not _DATE_RE.match(date or ""):
        raise HTTPException(400, "날짜 형식이 올바르지 않습니다 (YYYY-MM-DD).")
    return date


def _check_ticker(ticker: str) -> str:
    if not _TICKER_RE.match(ticker or ""):
        raise HTTPException(400, "종목코드 형식이 올바르지 않습니다.")
    return ticker


# ─────────────────────────────────────────────────────────
# 백그라운드 작업 (Job)
# ─────────────────────────────────────────────────────────


@dataclass
class Job:
    id: str
    kind: str
    label: str
    status: str = "running"  # running | done | failed
    started_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    finished_at: str | None = None
    step: str = "시작"
    message: str = ""
    result: dict | None = None

    def as_dict(self) -> dict:
        d = asdict(self)
        d["elapsed_sec"] = round(
            (datetime.now() - datetime.fromisoformat(self.started_at)).total_seconds(), 1
        )
        return d


_JOBS: dict[str, Job] = {}
_JOBS_LOCK = threading.Lock()


def _set_step(job: Job, step: str) -> None:
    job.step = step
    log.info("[job %s] %s — %s", job.id[:8], job.label, step)


def _run_job(job: Job, fn) -> None:
    """스레드에서 작업을 돌리고 상태를 기록한다."""

    def _target():
        try:
            fn(lambda s: _set_step(job, s))
            job.status = "done"
            job.step = "완료"
            job.message = "완료"
        except Exception as exc:
            job.status = "failed"
            job.step = "실패"
            job.message = f"{type(exc).__name__}: {exc}"
            job.result = {"traceback": traceback.format_exc()[-2000:]}
            log.exception("[job %s] 실패: %s", job.id[:8], exc)
        finally:
            job.finished_at = datetime.now().isoformat(timespec="seconds")

    threading.Thread(target=_target, daemon=True, name=f"job-{job.id[:8]}").start()


def _start_job(kind: str, label: str, fn) -> Job:
    job = Job(id=uuid.uuid4().hex, kind=kind, label=label)
    with _JOBS_LOCK:
        _JOBS[job.id] = job
        # 최근 40건만 유지
        if len(_JOBS) > 40:
            for old in sorted(_JOBS.values(), key=lambda j: j.started_at)[: len(_JOBS) - 40]:
                _JOBS.pop(old.id, None)
    _run_job(job, fn)
    return job


# ─────────────────────────────────────────────────────────
# 시스템 상태
# ─────────────────────────────────────────────────────────


def _launchd_installed() -> bool:
    try:
        out = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=10)
        return "com.stockpipeline.daily" in out.stdout
    except Exception:
        return False


def _launchd_pid() -> int | None:
    try:
        out = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=10)
        for line in out.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "com.stockpipeline.daily":
                try:
                    return int(parts[0])
                except ValueError:
                    return None
    except Exception:
        pass
    return None


def _next_run_hint() -> str:
    now = datetime.now()
    nxt = now.replace(hour=2, minute=0, second=0, microsecond=0)
    if now >= nxt:
        nxt += timedelta(days=1)
    return nxt.strftime("%Y-%m-%d %H:%M")


def _running_pipeline() -> bool:
    try:
        out = subprocess.run(["pgrep", "-f", "main_orchestrator.py"],
                             capture_output=True, text=True, timeout=5)
        return bool(out.stdout.strip())
    except Exception:
        return False


def _whisper_ready() -> dict:
    home = Path.home()
    repo = config.WHISPER_MODEL.replace("/", "--")
    snaps = home / ".cache/huggingface/hub" / f"models--{repo}" / "snapshots"
    mlx = snaps.is_dir() and any(snaps.glob("*/weights.safetensors"))
    fb = (home / ".cache/whisper" / f"{config.WHISPER_FALLBACK_MODEL}.pt").exists()
    return {"model": config.WHISPER_MODEL, "ready": mlx,
            "fallback": config.WHISPER_FALLBACK_MODEL, "fallback_ready": fb}


def _env_keys() -> dict:
    return {
        "KRX": bool(config.env("KRX_ID") and config.env("KRX_PW")),
        "LLM": bool(
            config.openai_key() or config.anthropic_key() or config.gemini_key()
        ),
        "TTS": bool(
            config.openai_key()
            or config.gemini_key()
            or config.elevenlabs_key()
            or (config.TTS_PROVIDER == "gcloud" and bool(config.env("GOOGLE_TTS_PROJECT")))
        ),
        "YOUTUBE_CLIENT": bool(config.YOUTUBE_CLIENT_ID and config.YOUTUBE_CLIENT_SECRET),
        "YOUTUBE_TOKEN": config.YOUTUBE_TOKEN_PATH.exists(),
    }


def _youtube_reachable() -> bool:
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(str(config.YOUTUBE_TOKEN_PATH))
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        yt.channels().list(part="status", mine=True).execute()
        return True
    except Exception:
        return False


def _youtube_channel() -> str | None:
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(str(config.YOUTUBE_TOKEN_PATH))
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        ch = yt.channels().list(part="snippet", mine=True).execute()
        return ch["items"][0]["snippet"]["title"]
    except Exception:
        return None


# ─────────────────────────────────────────────────────────
# 화면
# ─────────────────────────────────────────────────────────


@app.get("/")
def index() -> HTMLResponse:
    f = PROJECT_DIR / "static" / "index.html"
    if not f.exists():
        return HTMLResponse("<h1>UI 없음 — static/index.html 확인</h1>", status_code=404)
    return FileResponse(f)


# ─────────────────────────────────────────────────────────
# 조회 API
# ─────────────────────────────────────────────────────────


@app.get("/api/stats")
def api_stats() -> dict:
    s = archive.stats()
    s["launchd_installed"] = _launchd_installed()
    s["pipeline_running"] = _running_pipeline()
    s["next_run"] = _next_run_hint()
    s["whisper"] = _whisper_ready()
    s["env_keys"] = _env_keys()
    s["free_disk_gb"] = round(shutil.disk_usage(PROJECT_DIR).free / 1024**3, 1)
    s["active_jobs"] = sum(1 for j in _JOBS.values() if j.status == "running")
    return s


@app.get("/api/health")
def api_health() -> dict:
    keys = _env_keys()
    return {
        "ok": all(keys.values()) and _launchd_installed(),
        "krx": keys["KRX"],
        "llm": keys["LLM"],
        "tts": keys["TTS"],
        "youtube": _youtube_reachable(),
        "whisper": _whisper_ready(),
        "launchd": _launchd_installed(),
        "pipeline_running": _running_pipeline(),
    }


@app.get("/api/diagnostics")
def api_diagnostics() -> dict:
    """원격 환경 진단 — 설정 누락의 원인을 바로 알 수 있게."""
    keys = _env_keys()
    whisper = _whisper_ready()
    missing = [k for k, v in keys.items() if not v]
    node_ok = shutil.which("node") is not None
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    return {
        "env_keys": keys,
        "missing": missing,
        "whisper": whisper,
        "launchd": _launchd_installed(),
        "launchd_pid": _launchd_pid(),
        "pipeline_running": _running_pipeline(),
        "next_run": _next_run_hint(),
        "node": node_ok,
        "ffmpeg": ffmpeg_ok,
        "remotion": (config.REMOTION_DIR / "node_modules").exists(),
        "youtube_channel": _youtube_channel(),
        "disk": {
            "free_gb": round(shutil.disk_usage(PROJECT_DIR).free / 1024**3, 1),
            "used_gb": round(shutil.disk_usage(PROJECT_DIR).used / 1024**3, 1),
        },
        "paths": {
            "project": str(PROJECT_DIR),
            "output": str(config.OUTPUT_DIR),
            "cache": str(config.CACHE_DIR),
            "data": str(config.DATA_DIR),
        },
        "last_run": (archive.list_runs() or [{}])[0].get("date"),
    }


@app.get("/api/runs")
def api_runs() -> list[dict]:
    return archive.list_runs()


@app.get("/api/runs/{date}")
def api_run(date: str) -> dict:
    """날짜별 상세.

    items 를 dict 로 채워 넣는다 — 저장된 원본은 티커 문자열 배열이라
    목록 API(/api/runs)와 형태가 달랐고, 화면이 여기서 404 를 만나 죽었다.
    """
    _check_date(date)
    run = archive.read_run(date)
    if not run:
        raise HTTPException(404, "해당 날짜의 실행 기록이 없습니다.")
    run = dict(run)
    run["items"] = [s for s in (archive.list_runs_for_items(date) or []) if s]
    run["item_count"] = len(run["items"])
    return run


@app.get("/api/items/{date}/{ticker}")
def api_item(date: str, ticker: str) -> dict:
    _check_date(date)
    _check_ticker(ticker)
    item = archive.read_item(date, ticker)
    if not item:
        raise HTTPException(404, "해당 항목을 찾을 수 없습니다.")
    item = dict(item)
    item.setdefault("date", date)
    item.setdefault("ticker", ticker)
    item["long_text"] = archive.read_item_long_text(date, ticker)
    if item.get("video") and Path(item["video"]).exists():
        item["video_url"] = f"/media/video/{ticker}"
    if item.get("audio") and Path(item["audio"]).exists():
        item["audio_url"] = f"/media/audio/{ticker}"
    item["thumb_url"] = f"/media/thumb/{ticker}"
    return item


@app.get("/api/jobs")
def api_jobs() -> list[dict]:
    return [j.as_dict() for j in sorted(_JOBS.values(), key=lambda j: j.started_at, reverse=True)]


# ─────────────────────────────────────────────────────────
# 종목 분석 데이터베이스 (Analytics)
# ─────────────────────────────────────────────────────────


@app.get("/api/analytics")
def api_analytics(limit: int = 50, q: str = "") -> dict:
    """종목 분석 데이터베이스 조회 (심층 분석 지표 및 컨센서스)."""
    import stock_analytics_db
    conn = stock_analytics_db.get_db_connection()
    cur = conn.cursor()
    query = """
        SELECT p.ticker, p.name, p.market, p.industry_name, p.current_price,
               p.market_cap_eok, p.summary_comment1, p.summary_comment2, p.summary_comment3,
               p.updated_at,
               v.pbr, v.bps, v.per, v.eps, v.consensus_target, v.consensus_upside_pct,
               v.consensus_opinion, v.report_count,
               m.overall_score, m.selection_headline, m.valuation_attractiveness
        FROM company_profile p
        LEFT JOIN valuation_consensus v ON p.ticker = v.ticker
        LEFT JOIN market_evaluation_report m ON p.ticker = m.ticker
    """
    params = []
    if q:
        query += " WHERE p.name LIKE ? OR p.ticker LIKE ? OR p.industry_name LIKE ?"
        kw = f"%{q}%"
        params.extend([kw, kw, kw])
    query += " ORDER BY p.updated_at DESC, p.market_cap_eok DESC LIMIT ?"
    params.append(limit)
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    return {"total": len(rows), "items": rows}


@app.get("/api/analytics/{ticker}")
def api_analytics_detail(ticker: str) -> dict:
    """단일 종목의 심층 분석 상세 (재무, 주주, 기술지표, 평가 리포트)."""
    _check_ticker(ticker)
    import stock_analytics_db
    conn = stock_analytics_db.get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM company_profile WHERE ticker = ?", (ticker,))
    profile = cur.fetchone()
    if not profile:
        raise HTTPException(404, "종목 분석 데이터가 없습니다.")

    cur.execute("SELECT * FROM valuation_consensus WHERE ticker = ?", (ticker,))
    val = cur.fetchone()

    cur.execute("SELECT * FROM shareholders_info WHERE ticker = ?", (ticker,))
    sh = cur.fetchone()

    cur.execute("SELECT * FROM financial_metrics WHERE ticker = ? ORDER BY id DESC", (ticker,))
    fins = [dict(r) for r in cur.fetchall()]

    cur.execute("SELECT * FROM technical_analytics WHERE ticker = ? ORDER BY date DESC LIMIT 1", (ticker,))
    tech = cur.fetchone()

    cur.execute("SELECT * FROM market_evaluation_report WHERE ticker = ?", (ticker,))
    eval_rep = cur.fetchone()

    return {
        "profile": dict(profile) if profile else {},
        "valuation": dict(val) if val else {},
        "shareholders": dict(sh) if sh else {},
        "financials": fins,
        "technical": dict(tech) if tech else {},
        "market_evaluation": dict(eval_rep) if eval_rep else {},
    }


# ─────────────────────────────────────────────────────────
# 대본
# ─────────────────────────────────────────────────────────


@app.get("/api/items/{date}/{ticker}/script")
def api_script(date: str, ticker: str) -> dict:
    _check_date(date)
    _check_ticker(ticker)
    item = archive.read_item(date, ticker)
    if not item:
        raise HTTPException(404, "항목을 찾을 수 없습니다.")
    text = archive.read_item_long_text(date, ticker)
    return {
        "ticker": ticker,
        "date": date,
        "name": item.get("name") or ticker,
        "text": text,
        "chars": len(text),
        "sections": item.get("sections") or [],
        "investors": item.get("investors") or [],
        "facts": item.get("facts") or {},
        "gate": item.get("gate"),
    }


@app.patch("/api/items/{date}/{ticker}/script")
def api_save_script(date: str, ticker: str, payload: dict) -> dict:
    _check_date(date)
    _check_ticker(ticker)
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "대본이 비어 있습니다.")
    item = archive.read_item(date, ticker)
    if not item:
        raise HTTPException(404, "항목을 찾을 수 없습니다.")
    archive.set_item_field(date, ticker, "long_text", text)
    log.info("대본 저장 %s/%s (%d자)", date, ticker, len(text))
    return {"ok": True, "chars": len(text)}


@app.post("/api/actions/validate-script")
async def api_validate_script(payload: dict) -> dict:
    """대본 검증 게이트 실행 (LLM 교정 없이 — 편집 중 빠른 확인용)."""
    import script_gate

    date = _check_date(payload.get("date", ""))
    ticker = _check_ticker(payload.get("ticker", ""))
    text = payload.get("text") or archive.read_item_long_text(date, ticker)
    if not text:
        raise HTTPException(400, "검증할 대본이 없습니다.")

    item = archive.read_item(date, ticker) or {}
    gate = await asyncio.to_thread(
        script_gate.validate,
        text,
        facts=item.get("facts") or {},
        reason=(item.get("candidate") or {}).get("reason", ""),
        hist=None,
        call_llm=None,
        name=ticker,
        use_llm=False,
        max_rounds=1,
    )
    d = gate.to_dict()
    return {"passed": d["passed"], "gate": d, "report": script_gate.render_report(gate, ticker)}


# ─────────────────────────────────────────────────────────
# 작업 실행
# ─────────────────────────────────────────────────────────


@app.post("/api/actions/sync")
def api_sync_unarchived() -> dict:
    """output/ 디렉토리의 미등록 영상들을 아카이브와 즉시 동기화."""
    count = archive.sync_unarchived_videos()
    archive._rebuild_index()
    return {"ok": True, "synced_count": count}


@app.post("/api/actions/run")
def api_run_pipeline(payload: dict) -> dict:
    """배치 실행 — 지정 종목 또는 스크리닝 결과로 5단계를 돌린다."""
    if _running_pipeline():
        raise HTTPException(409, "이미 파이프라인이 실행 중입니다.")

    tickers = [t.strip() for t in (payload.get("tickers") or "").split(",") if t.strip()]
    for t in tickers:
        _check_ticker(t)
    if len(tickers) > 10:
        raise HTTPException(400, "한 번에 최대 10종목까지 지정할 수 있습니다.")

    no_publish = bool(payload.get("no_publish", True))
    dry_run = bool(payload.get("dry_run", False))
    cmd = [str(PROJECT_DIR / "venv/bin/python3"), str(PROJECT_DIR / "main_orchestrator.py")]
    if tickers:
        cmd += ["--tickers", ",".join(tickers)]
    if no_publish:
        cmd += ["--no-publish"]
    if dry_run:
        cmd += ["--dry-run"]

    logf = config.LOG_DIR / "dashboard_run.log"

    def _fn(step):
        step("파이프라인 실행 중")
        env = {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
               "HOME": str(Path.home())}
        with open(logf, "w", encoding="utf-8") as out:
            subprocess.run(cmd, cwd=str(PROJECT_DIR), stdout=out, stderr=subprocess.STDOUT,
                           env=env, check=False, timeout=7200)
        step("완료")

    job = _start_job("pipeline", "파이프라인 실행", _fn)
    return {"job": job.as_dict(), "cmd": " ".join(cmd[1:]), "log": f"/api/actions/log?path={logf.name}"}


@app.post("/api/actions/rebuild/{date}/{ticker}")
def api_rebuild(date: str, ticker: str) -> dict:
    """대본 수정 후 재빌드 — TTS → 자막 → 렌더 → QC. 게시하지 않는다."""
    _check_date(date)
    _check_ticker(ticker)
    item = archive.read_item(date, ticker)
    if not item:
        raise HTTPException(404, "항목을 찾을 수 없습니다.")

    def _fn(step):
        _rebuild_item(date, ticker, step)

    job = _start_job("rebuild", f"재빌드 {ticker}", _fn)
    return {"job": job.as_dict()}


def _rebuild_item(date: str, ticker: str, step) -> dict:
    """한 항목을 TTS → 렌더 → QC 까지 다시 만든다. (게시 없음)"""
    import stage2_long
    import stage3_audio
    import stage4_render
    import stage5_publish

    item = archive.read_item(date, ticker)
    text = archive.read_item_long_text(date, ticker)
    if not text:
        raise RuntimeError("대본이 없습니다.")
    name = item.get("name") or ticker

    step("TTS 합성 중")
    audio = asyncio.run(stage2_long._tts_long(text=text, ticker=ticker))
    if not audio or not Path(audio).exists():
        raise RuntimeError("TTS 실패")

    step("Whisper 자막 추출 중")
    words = stage3_audio.extract_word_timestamps(Path(audio), script_text=text, company_name=name)

    step("차트 데이터 갱신 중")
    series = _refresh_series(ticker)

    step("Remotion 렌더 중")
    manifest_item = {
        "name": name,
        "audio": str(audio),
        "timestamps": words,
        "script": item.get("script") or {},
        "long_text": text,
        "facts": item.get("facts") or {},
        "metrics": item.get("metrics") or [],
        "chart_paths": item.get("chart_paths") or [],
        "candidate": item.get("candidate") or {},
        "series": series,
        "editorial_plan": item.get("editorial_plan"),
    }
    rendered = stage4_render.render({ticker: manifest_item})
    if not rendered:
        raise RuntimeError("렌더 실패")

    step("QC 검사 중")
    qc = stage5_publish.probe(rendered[0])
    if not qc.ok:
        raise RuntimeError(f"QC 실패: {qc.reason}")

    archive.set_item_field(date, ticker, "audio", str(audio))
    archive.set_item_field(date, ticker, "timestamps", words)
    archive.set_item_field(date, ticker, "video", str(rendered[0]))
    archive.set_item_field(date, ticker, "qc", vars(qc) if hasattr(qc, "__dict__") else {})
    step("완료 (게시하지 않음)")
    return {"video": str(rendered[0]), "seconds": qc.duration}


def _refresh_series(ticker: str):
    """KRX 에서 최신 OHLCV 를 받아 SVG 차트용 series 를 다시 만든다."""
    try:
        import chart_data
        import screening as _scr
        from datetime import timedelta as _td
        from pykrx import stock

        tday = _scr.last_trading_day(stock)
        end = datetime.strptime(tday, "%Y%m%d")
        hist = stock.get_market_ohlcv_by_date(
            (end - _td(days=365)).strftime("%Y%m%d"), tday, ticker
        )
        return chart_data.to_series(hist)
    except Exception as exc:
        log.warning("series 갱신 실패(%s) — PNG 폴백으로 진행: %s", ticker, exc)
        return None


@app.get("/api/followup")
def api_get_followup():
    """STOCK ANALYSIS / FOLLOW UP 사후 시세 데이터 반환"""
    data_file = PROJECT_DIR / "public-dashboard" / "data.json"
    if not data_file.exists():
        import pages_export
        pages_export.export_dashboard()
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        raise HTTPException(500, f"Follow-up 데이터 로드 실패: {exc}")


@app.post("/api/followup/refresh")
def api_refresh_followup():
    """사후 시세 추적(Follow-Up) 최신 종가 비동기 갱신 작업 실행"""
    def _fn(step):
        step("YouTube 게시 영상 확인 및 시세 갱신 중")
        script = PROJECT_DIR / "update_public_dashboard.sh"
        if script.exists():
            res = subprocess.run([str(script), "--force"], capture_output=True, text=True, cwd=str(PROJECT_DIR))
            if res.returncode != 0:
                raise RuntimeError(f"스크립트 실행 오류: {res.stderr[:200]}")
        else:
            import pages_export
            pages_export.main()
        step("사후 시세 추적 갱신 완료")

    job = _start_job("followup_refresh", "사후 시세 추적 갱신", _fn)
    return {"job": job.as_dict()}


@app.post("/api/actions/qc/{date}/{ticker}")
def api_qc(date: str, ticker: str) -> dict:
    _check_date(date)
    _check_ticker(ticker)
    import stage5_publish

    item = archive.read_item(date, ticker)
    if not item:
        raise HTTPException(404, "항목을 찾을 수 없습니다.")
    video = item.get("video")
    if not video or not Path(video).exists():
        raise HTTPException(400, "렌더된 영상이 없습니다.")
    qc = stage5_publish.probe(Path(video))
    if qc.ok:
        archive.set_item_field(date, ticker, "qc", vars(qc) if hasattr(qc, "__dict__") else {})
    return {"ok": qc.ok, "reason": qc.reason,
            "resolution": getattr(qc, "resolution", None),
            "duration": getattr(qc, "duration", None)}


@app.post("/api/actions/publish/{date}/{ticker}")
def api_publish(date: str, ticker: str, payload: dict) -> dict:
    """YouTube 게시 — 사용자가 명시적으로 호출할 때만 수행한다."""
    _check_date(date)
    _check_ticker(ticker)
    import stage5_publish

    item = archive.read_item(date, ticker)
    if not item:
        raise HTTPException(404, "항목을 찾을 수 없습니다.")
    video = item.get("video")
    if not video or not Path(video).exists():
        raise HTTPException(400, "렌더된 영상이 없습니다.")
    if item.get("published_video_id"):
        raise HTTPException(400, "이미 게시된 영상입니다.")

    name = item.get("name") or ticker
    script = item.get("script") or {}
    title = payload.get("title") or f"{name}({ticker}) 주가 분석"
    desc = stage5_publish.build_description(
        {**script, "name": name, "long_text": item.get("long_text", "")}, ticker
    )
    vid = stage5_publish.publish(
        Path(video), title=title, description=desc,
        tags=["주식", "종목분석", ticker], immediate=True,
    )
    if not vid:
        raise HTTPException(500, "게시 실패 — YouTube API 응답을 확인하세요.")
    archive.set_item_field(date, ticker, "published_video_id", vid)
    screening_mark_published(ticker)
    return {"video_id": vid, "url": f"https://youtu.be/{vid}"}


def screening_mark_published(ticker: str) -> None:
    try:
        import screening

        screening.mark_published([ticker])
    except Exception:
        pass


@app.post("/api/actions/visibility/{date}/{ticker}")
def api_visibility(date: str, ticker: str, visibility: str = "private") -> dict:
    _check_date(date)
    _check_ticker(ticker)
    if visibility not in ("private", "unlisted", "public"):
        raise HTTPException(400, "visibility는 private/unlisted/public 중 하나여야 합니다.")
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    item = archive.read_item(date, ticker)
    if not item:
        raise HTTPException(404, "항목을 찾을 수 없습니다.")
    vid = item.get("published_video_id")
    if not vid or str(vid).startswith("manual-"):
        raise HTTPException(400, "게시된 영상 ID가 없습니다.")
    creds = Credentials.from_authorized_user_file(str(config.YOUTUBE_TOKEN_PATH))
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    yt.videos().update(part="status", body={"id": vid, "status": {"privacyStatus": visibility}}).execute()
    return {"ok": True, "video_id": vid, "visibility": visibility}


# ─────────────────────────────────────────────────────────
# Google Drive 동기화 및 백업
# ─────────────────────────────────────────────────────────

@app.get("/api/gdrive/status")
def api_gdrive_status() -> dict:
    """Google Drive 인증 상태 및 폴더 정보 조회."""
    import gdrive_sync
    authed = gdrive_sync.is_authenticated()
    return {
        "authenticated": authed,
        "folder_name": gdrive_sync.GDRIVE_FOLDER_NAME,
        "token_path": str(gdrive_sync.GDRIVE_TOKEN_PATH),
    }


@app.post("/api/gdrive/upload")
def api_gdrive_upload(payload: dict) -> dict:
    """선택한 종목 리스트의 모든 영상 에셋을 Google Drive로 일괄 백업."""
    import gdrive_sync
    date = _check_date(payload.get("date", ""))
    tickers = payload.get("tickers") or []
    if not isinstance(tickers, list) or not tickers:
        raise HTTPException(400, "전송할 종목 코드 목록(tickers)이 비어 있습니다.")
    for t in tickers:
        _check_ticker(t)

    if not gdrive_sync.is_authenticated():
        raise HTTPException(401, "Google Drive 인증이 필요합니다. terminal에서 'python3 tools/gdrive_auth.py'를 1회 실행해 승인하세요.")

    def _fn(step):
        def _update(st, msg):
            step(f"{st} — {msg}")

        res = gdrive_sync.batch_sync_to_gdrive(date, tickers, job_updater=_update)
        return res

    job = _start_job("gdrive_upload", f"Google Drive 백업 ({len(tickers)}개)", _fn)
    return {"job": job.as_dict(), "date": date, "tickers": tickers}


@app.post("/api/gdrive/upload/{date}/{ticker}")
def api_gdrive_upload_single(date: str, ticker: str) -> dict:
    """단일 종목의 영상 에셋을 Google Drive로 즉시 백업."""
    import gdrive_sync
    _check_date(date)
    _check_ticker(ticker)

    if not gdrive_sync.is_authenticated():
        raise HTTPException(401, "Google Drive 인증이 필요합니다. terminal에서 'python3 tools/gdrive_auth.py'를 1회 실행해 승인하세요.")

    def _fn(step):
        step("Google Drive 전송 중")
        service = gdrive_sync.get_drive_service()
        res = gdrive_sync.sync_stock_bundle(service, date, ticker)
        step("완료")
        return res

    job = _start_job("gdrive_upload", f"Google Drive 백업 {ticker}", _fn)
    return {"job": job.as_dict()}


# ─────────────────────────────────────────────────────────
# 삭제
# ─────────────────────────────────────────────────────────


@app.delete("/api/items/{date}/{ticker}")
def api_delete_item(date: str, ticker: str, media: bool = False) -> dict:
    _check_date(date)
    _check_ticker(ticker)
    p = archive.run_dir(date) / f"{ticker}.json"
    if not p.exists():
        raise HTTPException(404, "항목을 찾을 수 없습니다.")
    if media:
        item = archive.read_item(date, ticker) or {}
        for key in ("video", "audio"):
            f = item.get(key)
            if f and Path(f).exists():
                try:
                    Path(f).unlink()
                except OSError:
                    pass
        for sub in ("chart_", "price_chart", "trend_line"):
            for png in (config.CACHE_DIR / ticker).glob(f"{sub}*.png"):
                png.unlink(missing_ok=True)
    p.unlink()
    archive._rebuild_index()
    return {"ok": True}


@app.delete("/api/runs/{date}")
def api_delete_run(date: str, media: bool = False) -> dict:
    _check_date(date)
    if not archive.run_dir(date).exists():
        raise HTTPException(404, "해당 날짜의 기록이 없습니다.")
    if media:
        run = archive.read_run(date) or {}
        for it in run.get("items", []):
            for key in ("video", "audio"):
                f = it.get(key)
                if f and Path(f).exists():
                    Path(f).unlink(missing_ok=True)
    ok = archive.delete_run(date, delete_media=False)
    if not ok:
        raise HTTPException(500, "삭제하지 못했습니다.")
    return {"ok": True}


@app.get("/api/actions/log")
def api_action_log(path: str) -> Response:
    """배치 실행 로그 — 파일명만 받고 LOG_DIR 아래에서만 찾는다."""
    name = Path(path).name
    f = config.LOG_DIR / name
    if not f.exists() or f.parent.resolve() != config.LOG_DIR.resolve():
        raise HTTPException(404, "로그가 없습니다.")
    return Response(f.read_text(encoding="utf-8", errors="replace"), media_type="text/plain")


# ─────────────────────────────────────────────────────────
# 미디어
# ─────────────────────────────────────────────────────────


@app.get("/media/video/{ticker}")
def media_video(ticker: str):
    _check_ticker(ticker)
    f = _ticker_file(ticker, ".mp4")
    if not f:
        raise HTTPException(404, "영상이 없습니다.")
    return FileResponse(f, media_type="video/mp4")


@app.get("/media/audio/{ticker}")
def media_audio(ticker: str):
    _check_ticker(ticker)
    for ext in (".mp3", ".wav", ".m4a"):
        f = _ticker_file(ticker, ext)
        if f:
            return FileResponse(f, media_type="audio/mpeg")
    raise HTTPException(404, "음원이 없습니다.")


@app.get("/media/thumb/{ticker}")
def media_thumb(ticker: str):
    """썸네일 — 없으면 영상의 차트가 완성된 지점에서 1회 추출해 캐시한다.

    8초는 차트 리빌 중이라 거의 검게 나온다. 영상 길이의 12% 지점
    (10~45초 범위)이 그려진 차트가 가장 또렷하다.
    """
    _check_ticker(ticker)
    thumb = THUMB_DIR / f"{ticker}.jpg"
    if thumb.exists():
        return FileResponse(thumb, media_type="image/jpeg")

    src = _ticker_file(ticker, ".mp4")
    if not src:
        # 투명 1x1 PNG — 깨진 이미지 아이콘 대신 깔끔하게
        return Response(_PLACEHOLDER_PNG, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})

    at = 12.0
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(src)],
            capture_output=True, text=True, timeout=20,
        )
        at = min(45.0, max(10.0, float(probe.stdout.strip()) * 0.12))
    except Exception:
        pass

    tmp = thumb.with_suffix(".tmp.jpg")
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.1f}", "-i", str(src),
             "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "4", str(tmp)],
            capture_output=True, timeout=90, check=False,
        )
        if tmp.exists() and tmp.stat().st_size > 0:
            tmp.replace(thumb)
            return FileResponse(thumb, media_type="image/jpeg")
    except Exception:
        pass
    finally:
        tmp.unlink(missing_ok=True)
    return Response(_PLACEHOLDER_PNG, media_type="image/png")


@app.get("/media/chart/{ticker}/{name}")
def media_chart(ticker: str, name: str):
    """캐시된 차트 PNG — 파일명은 해당 종목 캐시 디렉터리 안에서만 찾는다."""
    _check_ticker(ticker)
    if Path(name).name != name or not name.endswith(".png"):
        raise HTTPException(400, "잘못된 차트 파일명입니다.")
    root = (config.CACHE_DIR / ticker).resolve()
    f = (root / name).resolve()
    if root not in f.parents or not f.exists():
        raise HTTPException(404, "차트가 없습니다.")
    return FileResponse(f, media_type="image/png")


def _ticker_file(ticker: str, ext: str) -> Path | None:
    """output/ 와 cache/<ticker>/ 에서 티커 파일을 찾는다.

    영상은 output/ 에 평탄하게 놓이고(접미사 _001 등 변형 포함),
    음원은 cache/<ticker>/voice.mp3 에 있다.
    """
    if ext == ".mp4":
        from video_files import latest_video
        return latest_video(config.OUTPUT_DIR, ticker)
    direct = config.OUTPUT_DIR / f"{ticker}{ext}"
    if direct.exists():
        return direct
    for f in sorted(config.OUTPUT_DIR.glob(f"{ticker}_*{ext}")):
        return f
    cache = config.CACHE_DIR / ticker
    if cache.exists():
        direct = cache / f"voice{ext}"
        if direct.exists():
            return direct
        for f in sorted(cache.glob(f"*{ext}")):
            return f
    return None


# 1x1 투명 PNG
_PLACEHOLDER_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


if __name__ == "__main__":
    import uvicorn

    print("대시보드 서버 시작: http://127.0.0.1:8787")
    uvicorn.run(app, host="127.0.0.1", port=8787, log_level="warning")
