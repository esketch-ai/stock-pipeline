"""단계 3 — TTS 비동기 수신 + mlx-whisper 단어 타임스탬프 추출.

Apple Silicon Metal 가속을 위해 mlx-whisper 를 1순위로 사용한다.
mlx-whisper 가 단어 단위 타임스탬프를 지원하지 않는 경우 whisper-timestamped 로 폴백한다.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

import config
from config import CACHE_DIR, DATA_DIR
from logger import log
from stage2_script import Script


def _spoken_text(text: str) -> str:
    """TTS 에 넘길 텍스트 - 숫자를 한글로 변환한다.

    LLM TTS(gpt-4o-mini-tts, gemini-*-tts)는 숫자 문자열을 자릿수로 읽어
    반드시 틀린다.  '172,800원' -> '172만 1,800원' (37만이 아님).
    한글로 바꾸면 정확히 읽는다.  '172,800원' -> '십칠만이천팔백원'.
    """
    import tts_numbers

    return tts_numbers.normalize_for_tts(text)


async def _tts_openai(text: str, out: Path) -> Path:
    import voice_director

    spoken = voice_director.direct_script_for_tts(text, provider="openai")
    async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
        resp = await client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {config.env('OPENAI_API_KEY')}"},
            json={
                "model": config.env("TTS_MODEL", "tts-1"),
                "voice": config.env("TTS_VOICE", "alloy"),
                "input": spoken,
                "response_format": "mp3",
            },
        )
        resp.raise_for_status()
    out.write_bytes(resp.content)
    return out


async def _tts_gcloud(text: str, out: Path) -> Path:
    """Google Cloud TTS (Neural2/Chirp3 한국어 + 방송 오디오 디렉팅).

    숫자 표기를 그대로 정확히 읽으며, voice_director 를 통해
    '뿌셔 보까!', 도파민 훅, 리스크 경고, 3대 수칙 등에
    역동적인 피치/속도/볼륨의 SSML 다이내믹스를 부여한다.
    """
    import asyncio as _aio

    import gcloud_tts
    import voice_director

    # 방송 30년 차 오디오 디렉팅: 다이내믹 SSML 연출 적용
    directed_text = voice_director.direct_script_for_tts(text, provider="gcloud")

    rate = config.env_float("GOOGLE_TTS_RATE", 1.03)
    pitch = config.env_float("GOOGLE_TTS_PITCH", 0.0)

    path = await _aio.to_thread(
        gcloud_tts.synth, directed_text, out, rate, pitch
    )
    if path is None:
        raise RuntimeError("Google Cloud TTS 합성 실패")
    return path


async def _tts_elevenlabs(text: str, out: Path) -> Path:
    voice_id = config.env("ELEVENLABS_VOICE_ID")
    async with httpx.AsyncClient(timeout=config.API_TIMEOUT) as client:
        resp = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": config.env("ELEVENLABS_API_KEY")},
            json={
                "text": _spoken_text(text),
                "model_id": config.env("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"),
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
        )
        resp.raise_for_status()
    out.write_bytes(resp.content)
    return out


async def _tts_gemini(text: str, out: Path) -> Path:
    """Gemini TTS 는 raw PCM(L16, 24kHz, mono) 을 반환한다. 반드시 ffmpeg 으로 인코딩한다."""
    import base64
    import subprocess

    model = env_tts_model()
    # Gemini TTS 는 긴 텍스트에서 변환 시간이 길어진다 (장편은 청크 분할로 완화)
    timeout = config.env_int("TTS_TIMEOUT", 300)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": config.gemini_key()},
            json={
                "contents": [{"parts": [{"text": _spoken_text(text)}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {"voiceName": config.env("GEMINI_TTS_VOICE", "Kore")}
                        }
                    },
                },
            },
        )
        resp.raise_for_status()

    part = resp.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
    data = base64.b64decode(part["data"])
    mime = part.get("mimeType", "")
    return _encode_audio(data, mime, out)


def env_tts_model() -> str:
    return config.env("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")


def _encode_audio(data: bytes, mime: str, out: Path) -> Path:
    """TTS 응답 바이트를 Remotion/Whisper 가 읽을 수 있는 mp3 로 정규화한다.

    Gemini 는 audio/L16;codec=pcm;rate=24000 (signed 16-bit LE, mono) 을 주는데
    이를 그대로 .mp3 으로 쓰면 디코딩이 실패한다.
    """
    import subprocess

    out.parent.mkdir(parents=True, exist_ok=True)
    mp3 = out.with_suffix(".mp3")

    if "pcm" in mime or "L16" in mime:
        # rate=24000 기본, 필요 시 mime 에서 파싱
        rate = 24000
        for token in mime.split(";"):
            if token.strip().startswith("rate="):
                try:
                    rate = int(token.split("=", 1)[1])
                except ValueError:
                    pass
        proc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-f", "s16le", "-ar", str(rate), "-ac", "1",
             "-i", "pipe:0", "-c:a", "libmp3lame", "-b:a", "128k", str(mp3)],
            input=data, capture_output=True,
        )
        if proc.returncode != 0 or not mp3.exists() or mp3.stat().st_size == 0:
            raise RuntimeError(f"PCM→mp3 변환 실패: {proc.stderr.decode()[:300]}")
        log.info("PCM(%s, %dHz) → mp3 변환 완료: %s", mime, rate, mp3.name)
        return mp3

    if "wav" in mime:
        wav = out.with_suffix(".wav")
        wav.write_bytes(data)
        return wav

    # 이미 mp3/ogg 등 그대로 쓸 수 있는 포맷
    mp3.write_bytes(data)
    return mp3


async def _tts_one(script: Script, semaphore: asyncio.Semaphore) -> Path:
    async with semaphore:
        out = CACHE_DIR / script.ticker / "voice.mp3"
        out.parent.mkdir(parents=True, exist_ok=True)
        provider = config.TTS_PROVIDER
        log.info("TTS 요청 %s (%s)", script.name, provider)

        if provider == "gcloud":
            import gcloud_tts

            if not gcloud_tts.is_configured():
                raise RuntimeError(
                    "GOOGLE_TTS_PROJECT 미설정 (.env 확인)"
                )
            path = await _tts_gcloud(script.full_text, out)
        elif provider == "elevenlabs":
            if not config.elevenlabs_key():
                raise RuntimeError("ELEVENLABS_API_KEY 미설정")
            path = await _tts_elevenlabs(script.full_text, out)
        elif provider == "gemini":
            if not config.gemini_key():
                raise RuntimeError("GEMINI_TTS_API_KEY 미설정")
            path = await _tts_gemini(script.full_text, out)
        else:
            if not config.env("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY 미설정")
            path = await _tts_openai(script.full_text, out)

        log.info("TTS 완료 %s → %s (%.1fKB)", script.name, path.name, path.stat().st_size / 1024)
        return path


async def _tts_all(scripts: list[Script]) -> dict[str, Path]:
    sem = asyncio.Semaphore(config.TTS_MAX_CONCURRENCY)
    tasks = [_tts_one(s, sem) for s in scripts]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    audio: dict[str, Path] = {}
    for script, res in zip(scripts, results):
        if isinstance(res, Exception):
            log.error("TTS 실패 %s: %s", script.name, res)
        else:
            audio[script.ticker] = res
    return audio


def _transcribe_mlx(audio_path: Path) -> list[dict]:
    """mlx-whisper (Apple Silicon Metal 가속) — 1순위 경로."""
    import mlx_whisper

    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=config.WHISPER_MODEL,
        word_timestamps=True,
        language="ko",
        verbose=None,
    )

    words: list[dict] = []
    for seg in result.get("segments", []):
        for w in seg.get("words", []) or []:
            word, start, end = w.get("word"), w.get("start"), w.get("end")
            if word is None or start is None or end is None:
                continue
            words.append({"word": word.strip(), "start": round(float(start), 3), "end": round(float(end), 3)})
    return words


def _transcribe_fallback(audio_path: Path) -> list[dict]:
    """whisper-timestamped 폴백 — MPS 또는 CPU 경로."""
    from whisper_timestamped.transcribe import get_audio_tensor, get_vad_segments

    model = _load_torch_whisper()
    audio = get_audio_tensor(str(audio_path))
    result = model.transcribe(
        audio,
        language="ko",
        word_timestamps=True,
        verbose=False,
        vad=True,
    )

    words: list[dict] = []
    for seg in result.get("segments", []):
        for w in seg.get("words", []) or []:
            token, start, end = w.get("word"), w.get("start"), w.get("end")
            if token is None or start is None or end is None:
                continue
            words.append({"word": token.strip(), "start": round(float(start), 3), "end": round(float(end), 3)})
    return words


def _load_torch_whisper():
    import whisper_timestamped
    import torch

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    name = config.WHISPER_FALLBACK_MODEL
    log.info("whisper-timestamped 폴백 — model=%s device=%s", name, device)
    try:
        return whisper_timestamped.load_model(name, device=device)
    except Exception as exc:
        # 폴백 모델이 아직 안 받아져 있으면(첫 실행) 그 사실을 로그로 남긴다
        log.error(
            "폴백 모델 '%s' 로드 실패 (%s) — setup_status.py 를 먼저 실행해 "
            "미리 받아두세요",
            name,
            exc,
        )
        raise


def prefetch_whisper_models(verbose: bool = True) -> bool:
    """배치 전에 두 Whisper 모델을 모두 준비해 야간 배치가 끊기지 않게 한다.

    폴백 경로는 mlx 가 죽을 때만 쓰이지만, 그때 1.5GB 를 내려받으면
    새벽 02:00 배치의 타임아웃을 넘긴다. 그래서 배포 시 한 번 미리 받아 둔다.
    """
    ok = True

    if verbose:
        log.info("Whisper 1순위(mxl) 사전 확인: %s", config.WHISPER_MODEL)
    try:
        import mlx_whisper  # noqa: F401
        from huggingface_hub import snapshot_download

        snapshot_download(config.WHISPER_MODEL)
        if verbose:
            log.info("  ✓ 1순위 모델 준비 완료")
    except Exception as exc:
        ok = False
        log.error("  ✖ 1순위 모델 준비 실패: %s", exc)

    if verbose:
        log.info("Whisper 2순위(폴백) 사전 확인: %s", config.WHISPER_FALLBACK_MODEL)
    try:
        import whisper

        whisper.load_model(config.WHISPER_FALLBACK_MODEL)
        if verbose:
            log.info("  ✓ 폴백 모델 준비 완료")
    except Exception as exc:
        ok = False
        log.error("  ✖ 폴백 모델 준비 실패: %s", exc)

    return ok


def extract_word_timestamps(audio_path: Path, script_text: str | None = None,
                           company_name: str | None = None) -> list[dict]:
    """자막 타임스탬프 생성.

    ══ 구조 ══
    텍스트는 **대본을 그대로** 쓴다. 음성을 재인식해 자막을 만들지 않는다.
        대본 -> TTS 음성 -> [Whisper: 타이밍만] -> 대본 텍스트로 자막 생성
    Whisper 는 '언제 말했는가' 만 제공하며, 무엇을 말했는지는 신뢰하지 않는다.
    (그래야 고유명사·숫자 인식 오류가 원천적으로 사라진다)

    ══ TTS 숫자 처리 ══
    TTS 는 숫자 문자열을 자릿수로 잘못 읽으므로 한글로 변환해 합성한다.
      '172,800원' -> '십칠만이천팔백원' -> 발화 '172,800원'
    (tts_numbers 모듈 / _spoken_text)

    시간값은 아무것도 임의로 바꾸지 않는다.
    """
    # ── 1. 타이밍 소스: Whisper 경계 ──
    spans: list[dict] = []
    try:
        spans = _transcribe_mlx(audio_path)
        if spans:
            log.info("Whisper 경계 추출: %d개 (텍스트는 사용하지 않음)", len(spans))
        else:
            log.warning("mlx-whisper 결과 비어있음 — 폴백")
    except Exception as exc:
        log.warning("mlx-whisper 실패 (%s) — whisper-timestamped 폴백", exc)

    if not spans:
        try:
            spans = _transcribe_fallback(audio_path)
            log.info("whisper-timestamped 경계: %d개", len(spans))
        except Exception as exc:
            log.error("타임스탬프 추출 완전 실패 (%s)", exc)
            return []

    # ── 2. 대본이 있으면 강제 정렬 (텍스트 = 대본) ──
    if script_text:
        try:
            import caption_align

            captions = caption_align.build_from_script(script_text, spans)
            v = caption_align.verify(script_text, captions)
            if not v["ok"]:
                log.warning("자막 검증 실패 — %s", v["reason"])
            else:
                log.info("자막 생성 완료 — 대본 %d어절 (검증 통과)", len(captions))
            return captions
        except Exception as exc:
            log.error("자막 정렬 실패: %s", exc)

    # ── 3. 대본이 없으면 Whisper 결과 사용 (안전망) ──
    log.warning("대본 미제공 — Whisper 인식 결과를 자막으로 사용")
    return spans


def synthesize(scripts: list[Script]) -> dict[str, dict]:
    """TTS + 타임스탬프. 결과는 ticker → {audio, timestamps, script} 맵."""
    if not scripts:
        log.warning("대본이 없어 TTS 단계 종료")
        return {}

    audio_map = asyncio.run(_tts_all(scripts))

    manifest: dict[str, dict] = {}
    for script in scripts:
        audio = audio_map.get(script.ticker)
        if not audio:
            continue
        words = extract_word_timestamps(
            audio, script_text=script.full_text, company_name=script.name
        )
        manifest[script.ticker] = {
            "name": script.name,
            "audio": str(audio),
            "timestamps": words,
            "script": script.to_dict(),
        }
        log.info("%s 타임스탬프 %d tokens / %.1fs", script.name, len(words), audio.stat().st_size)

    out = DATA_DIR / "audio_manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest