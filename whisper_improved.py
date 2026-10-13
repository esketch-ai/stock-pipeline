"""Improved Whisper transcription using mlx_whisper directly (no CLI dependency)."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional

from logger import log

# ── mlx_whisper 직접 사용 ──────────────────────────────────────

def _transcribe_mlx(audio_path: str, model: str | None = None) -> dict:
    """mlx_whisper로 전사 (JSON 출력) — hallucination 방지 옵션 포함"""
    import config
    import mlx_whisper

    model = model or config.WHISPER_MODEL
    log.info("[mlx_whisper] 전사 중... model=%s", model)
    result = mlx_whisper.transcribe(
        audio_path,
        path_or_hf_repo=model,
        word_timestamps=True,
        condition_on_previous_text=False,
        hallucination_silence_threshold=1,
    )
    return result


def _diarize_whispermlx(audio_path: str, hf_token: str, model: str | None = None) -> list[dict]:
    """whispermlx로 화자 분리만 수행, JSON 결과에서 화자 정보 추출"""
    import config
    import shutil
    whispermlx = shutil.which("whispermlx")
    if not whispermlx:
        raise FileNotFoundError("whispermlx를 찾을 수 없습니다. uv tool install whispermlx")

    model = model or config.WHISPER_MODEL
    hf_token = os.getenv("HF_TOKEN", "")
    if not hf_token:
        raise ValueError("화자 분리에는 HF_TOKEN이 필요합니다. export HF_TOKEN=...")
    
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            "whispermlx",
            audio_path,
            "--model", model,
            "--diarize",
            "--hf_token", os.getenv("HF_TOKEN", ""),
            "--output_dir", tmp,
        ]
        log.info("[whispermlx] 화자 분리 중...")
        subprocess.run(cmd, check=True, capture_output=True)

        basename = os.path.splitext(os.path.basename(audio_path))[0]
        json_path = os.path.join(tmp, f"{basename}.json")
        with open(json_path) as f:
            data = json.load(f)

        diar_segments = []
        for seg in data.get("segments", []):
            speaker = seg.get("speaker", "UNKNOWN")
            diar_segments.append({
                "start": seg["start"],
                "end": seg["end"],
                "speaker": seg.get("speaker", "UNKNOWN"),
            })
        return diar_segments


def _assign_speakers(transcription: dict, diarization: list[dict]) -> list[dict]:
    """mlx_whisper 전사 세그먼트에 whispermlx 화자 배정"""
    result = []
    for seg in transcription.get("segments", []):
        seg_start = seg["start"]
        seg_end = seg["end"]
        # 가장 많이 겹치는 화자 구간 찾기
        best_speaker = "UNKNOWN"
        best_overlap = 0.0
        for d in diarization:
            overlap = max(0, min(seg_end, d["end"]) - max(seg_start, d["start"]))
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = d["speaker"]
        result.append({
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"].strip(),
            "speaker": best_speaker,
        })
    return result


def _transcribe_mlx_pipeline(audio_path: str, hf_token: str = None) -> dict:
    """mlx_whisper + whispermlx 파이프라인으로 전사 + 화자 분리"""
    # 1. mlx_whisper 전사
    transcription = _transcribe_mlx(audio_path)
    
    # 2. 화자 분리 (HF_TOKEN이 있으면)
    diarization = []
    if hf_token:
        try:
            diarization = _diarize_whispermlx(audio_path, hf_token)
        except Exception as exc:
            log.warning("화자 분리 실패: %s", exc)
    
    # 화자 배정
    segments = _assign_speakers(transcription, diarization)
    
    return {
        "text": transcription.get("text", ""),
        "segments": transcription.get("segments", []),
        "language": transcription.get("language", "ko"),
    }


def transcribe_whisper(audio_path: Path | str, script_text: str = None, company_name: str = None) -> list[dict]:
    """
    기존 인터페이스와 호환되는 래퍼 함수.
    Whisper 타임스탬프 + 회사명 보호를 반환합니다.
    """
    from logger import log
    
    try:
        result = _transcribe_mlx_pipeline(audio_path, hf_token=os.getenv("HF_TOKEN"))
        log.info(f"Whisper 전사 완료: {len(result.get('segments', []))} 세그먼트")
        
        # 기존 인터페이스 호환: [{word, start, end}, ...]
        segments = []
        for seg in result.get("segments", []):
            segments.append({
                "word": seg["text"].strip(),
                "start": seg["start"],
                "end": seg["end"],
                "speaker": seg.get("speaker", "UNKNOWN"),
            })
        return segments
        
    except Exception as exc:
        log.warning("개선된 Whisper 파이프라인 실패(원본 유지): %s", exc)
        # 폴백: 기존 mlx_whisper 직접 호출
        import config

        result = _transcribe_mlx(str(audio_path), model=config.WHISPER_MODEL)
        return [
            {"word": s["text"].strip(), "start": s["start"], "end": s["end"]}
            for s in result["segments"]
        ]


if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    if len(sys.argv) > 1:
        audio_path = Path(sys.argv[1])
        result = transcribe_whisper(Path(sys.argv[1]))
        for seg in result:
            print(f"{seg['start']:.2f} {seg['word']}")