"""전역 설정 로더 — .env 파일과 실행 환경변수를 병합한다."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent
# 실제 환경변수가 .env 보다 우선한다. (예: LLM_PROVIDER=ollama 로 한 번만 로컬 생성)
# launchd 는 .env 만 읽으므로 주간 배치 동작은 그대로다.
load_dotenv(PROJECT_DIR / ".env", override=False)

LOG_DIR = PROJECT_DIR / "logs"
OUTPUT_DIR = PROJECT_DIR / "output"
CACHE_DIR = PROJECT_DIR / "cache"
STATE_DIR = PROJECT_DIR / "state"
DATA_DIR = PROJECT_DIR / "data"
REMOTION_DIR = PROJECT_DIR / "remotion"

for _d in (LOG_DIR, OUTPUT_DIR, CACHE_DIR, STATE_DIR, DATA_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def env(key: str, default: str = "") -> str:
    """환경변수 조회. 공백 문자열은 '미설정'으로 취급해 default를 반환한다."""
    value = os.environ.get(key, "")
    return value.strip() if value.strip() else default


def env_int(key: str, default: int) -> int:
    try:
        return int(env(key, str(default)))
    except ValueError:
        return default


def env_bool(key: str, default: bool = False) -> bool:
    raw = env(key, "true" if default else "false").lower()
    return raw in {"1", "true", "yes", "y", "on"}


# ── 파이프라인 설정 ──────────────────────────────────────
DAILY_VIDEO_COUNT = env_int("DAILY_VIDEO_COUNT", 1)
VIDEO_RESOLUTION = env("VIDEO_RESOLUTION", "4k")
YOUTUBE_VISIBILITY = env("YOUTUBE_VISIBILITY", "private")
YOUTUBE_SCHEDULE_ENABLED = env_bool("YOUTUBE_SCHEDULE_ENABLED", True)

LLM_MAX_CONCURRENCY = env_int("LLM_MAX_CONCURRENCY", 3)
LLM_MAX_RETRIES = env_int("LLM_MAX_RETRIES", 2)

# ── 영상 길이 모드 ──────────────────────────────────────
# short : 60~90초 (기본)   long : 약 7분 풀버전
VIDEO_DURATION = env("VIDEO_DURATION", "long").lower()
LONG_TARGET_CHARS = env_int("LONG_TARGET_CHARS", 2400)
TTS_MAX_CONCURRENCY = env_int("TTS_MAX_CONCURRENCY", 3)
API_TIMEOUT = env_int("API_TIMEOUT", 120)

# ── 프로바이더 ───────────────────────────────────────────
LLM_PROVIDER = env("LLM_PROVIDER", "openai").lower()
TTS_PROVIDER = env("TTS_PROVIDER", "openai").lower()

OPENAI_MODEL = env("OPENAI_MODEL", "gpt-4o")
ANTHROPIC_MODEL = env("ANTHROPIC_MODEL", "claude-sonnet-4-5")
GEMINI_MODEL = env("GEMINI_MODEL", "gemini-2.5-flash")

# 로컬 Ollama (LLM_PROVIDER=ollama). 대본이 기기를 떠나지 않는다.
#   .env 에 OLLAMA_MODEL=gpt-oss:20b 로 두면 문체·구조 다양성이 개선된다.
#   gpt-oss 는 'harmony' 형식 사고 태그를 쓰므로 기본 reasoning 을 끈다.
OLLAMA_MODEL = env("OLLAMA_MODEL", "qwen3-coder:30b")
OLLAMA_HOST = env("OLLAMA_HOST", "http://127.0.0.1:11434")

TTS_MODEL = env("TTS_MODEL", "tts-1")
TTS_VOICE = env("TTS_VOICE", "alloy")

# 1순위: mlx-whisper (Apple Silicon Metal 가속)
WHISPER_MODEL = env("WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")
# 2순위 폴백: whisper-timestamped (torch). mlx 실패 시에만 쓰이므로
# 새벽 배치 전에 반드시 미리 내려받아 둔다 (설치: setup_status.py --prefetch-whisper)
WHISPER_FALLBACK_MODEL = env("WHISPER_FALLBACK_MODEL", "medium")

# ── 영상 말풍선 (마지막 카드) ─────────────────────────────
# 자주 바뀐다 — .env 에서만 바꾸면 되도록 코드에 박지 않는다
CONTACT_CHANNEL = env("CONTACT_CHANNEL", "채널 메시지로 문의")
CONTACT_URL = env("CONTACT_URL", "")
CONTACT_NOTE = env("CONTACT_NOTE", "종목 문의 · 자료 요청 가능")
# contact.txt 를 쓰지 않을 때 .env 로만 연락처를 채울 때 사용한다.
CONTACT_PROVIDER = env("CONTACT_PROVIDER", "")
CONTACT_EMAIL = env("CONTACT_EMAIL", "")
CONTACT_PHONE = env("CONTACT_PHONE", "")
CONTACT_BUSINESS = env("CONTACT_BUSINESS", "")
# 영상이 끝나기 전에도 QR 을 상단에 계속 노출할지 (기본은 마무리 카드에만 표시)
CONTACT_QR_PERSISTENT = env_bool("CONTACT_QR_PERSISTENT", False)

YOUTUBE_CLIENT_ID = env("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = env("YOUTUBE_CLIENT_SECRET")
YOUTUBE_REDIRECT_URI = env("YOUTUBE_REDIRECT_URI", "https://developers.google.com/oauthplayground")
YOUTUBE_CHANNEL_ID = env("YOUTUBE_CHANNEL_ID")


def _token_path() -> Path:
    raw = env("YOUTUBE_TOKEN_PATH", "youtube_token.json")
    p = Path(raw).expanduser()
    return p if p.is_absolute() else (PROJECT_DIR / p).resolve()


YOUTUBE_TOKEN_PATH = _token_path()


def openai_key() -> str:
    return env("OPENAI_API_KEY") or env("OPENAI_TTS_API_KEY")


def anthropic_key() -> str:
    return env("ANTHROPIC_API_KEY")


def gemini_key() -> str:
    return env("GEMINI_API_KEY") or env("GEMINI_TTS_API_KEY")


def elevenlabs_key() -> str:
    return env("ELEVENLABS_API_KEY")


# ── 해상도 프리셋 ───────────────────────────────────────
RESOLUTION_PRESETS = {
    "4k": (3840, 2160),
    "1080p": (1920, 1080),
}


def resolution() -> tuple[int, int]:
    return RESOLUTION_PRESETS.get(VIDEO_RESOLUTION.lower(), RESOLUTION_PRESETS["4k"])
LONG_SECTION_GAP = env_int("LONG_SECTION_GAP", 20)


def env_float(key: str, default: float) -> float:
    try:
        return float(env(key, str(default)))
    except ValueError:
        return default
