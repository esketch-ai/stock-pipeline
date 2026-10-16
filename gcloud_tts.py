"""Google Cloud Text-to-Speech 어댑터 (Neural2 한국어).

왜 전용 어댑터가 필요한가:
    LLM TTS(gpt-4o-mini-tts, gemini-*-tts)는 숫자 문자열을 자릿수로 분해해
    읽어서 반드시 틀린다.
        '172,800원' -> '172만 1,800원'  (37만이 아님)
    Google Cloud TTS Neural2 는 숫자 표기를 그대로 정확히 읽는다.
        '172,800원' -> '172,800원'

인증:
    gcloud 사용자 자격증명(ADC 불필요)을 쓴다.
    ADC 가 개입하면 quota project 오류(403)가 나므로 반드시 우회한다.

환경변수:
    GOOGLE_TTS_PROJECT    필수 — Cloud TTS API 가 활성화된 프로젝트 ID
    GOOGLE_TTS_VOICE      선택 — 기본 ko-KR-Wavenet-A (남성)
GOOGLE_TTS_PITCH      선택 — 기본 -4.0 (반음 낮춤, 낮은 베이스)
GOOGLE_TTS_RATE       선택 — 기본 0.97 (약간 느리게 = 신뢰감)
    GOOGLE_TTS_LANGUAGE   선택 — 기본 ko-KR
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import config
from logger import log

ENDPOINT = "https://texttospeech.googleapis.com/v1/text:synthesize"
# 2026-10 실측으로 확인된 한국어 음성 목록 (Neural2, Chirp3-HD, Wavenet, Standard).
SUPPORTED_VOICES = {
    # ── [추천] 뉴럴2 (Neural2) : SSML 다이내믹스 & 감정 표현 최적화 ──
    "ko-KR-Neural2-C": ("ko-KR", "남성 · 뉴럴2 (유튜브 애널리스트 추천)"),
    "ko-KR-Neural2-A": ("ko-KR", "여성 · 뉴럴2 (당찬 수석 애널리스트)"),
    "ko-KR-Neural2-B": ("ko-KR", "여성 · 뉴럴2 (차분한 정통 분석관)"),

    # ── [차세대] Chirp3-HD : 최신 고음질 생성형 AI 보이스 ──
    "ko-KR-Chirp3-HD-Fenrir": ("ko-KR", "남성 · Chirp3 생성형 HD (세련된 전문가)"),
    "ko-KR-Chirp3-HD-Puck": ("ko-KR", "남성 · Chirp3 생성형 HD (밝고 경쾌한 도파민)"),
    "ko-KR-Chirp3-HD-Charon": ("ko-KR", "남성 · Chirp3 생성형 HD (중후한 베이스)"),
    "ko-KR-Chirp3-HD-Kore": ("ko-KR", "여성 · Chirp3 생성형 HD (지적이고 생생한 톤)"),
    "ko-KR-Chirp3-HD-Aoede": ("ko-KR", "여성 · Chirp3 생성형 HD (차분한 앵커 톤)"),

    # ── 웨이브넷 (Wavenet) ──
    "ko-KR-Wavenet-C": ("ko-KR", "남성 · 웨이브넷 C"),
    "ko-KR-Wavenet-D": ("ko-KR", "남성 · 웨이브넷 D"),
    "ko-KR-Wavenet-A": ("ko-KR", "여성 · 웨이브넷 A"),
    "ko-KR-Wavenet-B": ("ko-KR", "여성 · 웨이브넷 B"),

    # ── 스탠다드 (Standard) ──
    "ko-KR-Standard-C": ("ko-KR", "남성 · 스탠다드 C"),
    "ko-KR-Standard-D": ("ko-KR", "남성 · 스탠다드 D"),
    "ko-KR-Standard-A": ("ko-KR", "여성 · 스탠다드 A"),
    "ko-KR-Standard-B": ("ko-KR", "여성 · 스탠다드 B"),
}


def project_id() -> str:
    return config.env("GOOGLE_TTS_PROJECT")


def voice_name() -> str:
    return config.env("GOOGLE_TTS_VOICE", "ko-KR-Neural2-C")


def pitch_semitones() -> float:
    """음높이 보정 (반음 단위). 음수면 낮아진다."""
    try:
        return float(config.env("GOOGLE_TTS_PITCH", "0.0"))
    except ValueError:
        return 0.0


def speaking_rate() -> float:
    return float(config.env("GOOGLE_TTS_RATE", "1.03"))


def is_configured() -> bool:
    return bool(project_id()) and shutil.which("gcloud") is not None


def _access_token(project: str) -> str | None:
    """gcloud 사용자 토큰 획득.

    ADC(application_default_credentials.json)가 있으면 403 quota 오류가 나므로
    이를 우회하기 위해 임시로 ADC를 격리한 상태에서 gcloud 를 호출한다.
    """
    adc = Path.home() / ".config/gcloud/application_default_credentials.json"
    backup = None
    try:
        if adc.exists():
            backup = Path(tempfile.mkdtemp()) / "adc.json"
            shutil.move(str(adc), str(backup))
        proc = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True, text=True, timeout=60,
        )
        token = proc.stdout.strip()
        return token or None
    except Exception as exc:
        log.debug("gcloud 토큰 획득 실패: %s", exc)
        return None
    finally:
        if backup and backup.exists():
            try:
                shutil.move(str(backup), str(adc))
            except Exception:
                pass


def available_voices() -> list[dict]:
    return [
        {"name": n, "lang": l, "desc": d}
        for n, (l, d) in SUPPORTED_VOICES.items()
    ]


def synth(text: str, out: Path, rate: float = 1.0, pitch: float = 0.0) -> Path | None:
    """Google Cloud TTS 로 음성을 합성한다.

    숫자는 원문 표기를 그대로 전달한다 (한글 변환 불필요).
    """
    import httpx

    project = project_id()
    if not project:
        log.error("GOOGLE_TTS_PROJECT 미설정")
        return None

    token = _access_token(project)
    if not token:
        log.error("gcloud 인증 실패 — 'gcloud auth login' 실행 필요")
        return None

    name = voice_name()
    lang = SUPPORTED_VOICES.get(name, ("ko-KR", ""))[0]

    is_ssml = text.strip().startswith("<speak>") and text.strip().endswith("</speak>")
    input_payload = {"ssml": text} if is_ssml else {"text": text}

    payload = {
        "input": input_payload,
        "voice": {"languageCode": lang, "name": name},
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": rate,
            "pitch": pitch,
        },
    }

    try:
        r = httpx.post(
            ENDPOINT,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "x-goog-user-project": project,
            },
            json=payload,
            timeout=120,
        )
    except Exception as exc:
        log.error("Cloud TTS 요청 실패: %s", exc)
        return None

    if r.status_code != 200:
        detail = ""
        try:
            detail = json.dumps(r.json())[:300]
        except Exception:
            detail = r.text[:300]
        log.error("Cloud TTS 오류 (HTTP %d): %s", r.status_code, detail)
        return None

    try:
        data = r.json()
        audio = base64.b64decode(data["audioContent"])
    except Exception as exc:
        log.error("Cloud TTS 응답 파싱 실패: %s", exc)
        return None

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(audio)
    log.debug("Cloud TTS 생성: %s (%d bytes, voice=%s)", out.name, len(audio), name)
    return out


def probe(text: str = "동양고속 37,200원입니다.") -> dict:
    """연결 확인 (설정 진단용)."""
    project = project_id()
    if not project:
        return {"ok": False, "reason": "GOOGLE_TTS_PROJECT 미설정"}
    token = _access_token(project)
    if not token:
        return {"ok": False, "reason": "gcloud 인증 실패"}

    import httpx

    is_ssml = text.strip().startswith("<speak>") and text.strip().endswith("</speak>")
    input_payload = {"ssml": text} if is_ssml else {"text": text}

    try:
        r = httpx.post(
            ENDPOINT,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "x-goog-user-project": project,
            },
            json={
                "input": input_payload,
                "voice": {"languageCode": "ko-KR", "name": voice_name()},
                "audioConfig": {
                    "audioEncoding": "MP3",
                    "speakingRate": speaking_rate(),
                    "pitch": pitch_semitones(),
                },
            },
            timeout=60,
        )
    except Exception as exc:
        return {"ok": False, "reason": f"요청 실패: {exc}"}

    if r.status_code == 200:
        size = len(base64.b64decode(r.json().get("audioContent", "")))
        return {
            "ok": True, "project": project, "voice": voice_name(),
            "bytes": size, "reason": "연결 정상",
        }
    try:
        msg = r.json().get("error", {}).get("message", "")[:200]
    except Exception:
        msg = r.text[:200]
    return {"ok": False, "project": project, "reason": f"HTTP {r.status_code}: {msg}"}