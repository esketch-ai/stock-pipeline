#!/usr/bin/env python3
"""환경 진단 스크립트 — setup_status

    ~/.local/share/stock-pipeline/venv/bin/python3 setup_status.py
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import config

OK, WARN, FAIL = "✔", "!", "✖"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "", warn: bool = False) -> None:
    results.append((OK if ok else (WARN if warn else FAIL), name, detail))


def _whisper_ready() -> tuple[bool, bool]:
    """(mlx 1순위, torch 폴백) 모델 캐시 준비 여부 — 다운로드 없이 확인만 한다."""
    home = Path.home()
    repo = config.WHISPER_MODEL.replace("/", "--")
    snapshots = home / ".cache/huggingface/hub" / f"models--{repo}" / "snapshots"
    mlx_ok = snapshots.is_dir() and any(snapshots.glob("*/weights.safetensors"))
    fb_ok = (
        home / ".cache/whisper" / f"{config.WHISPER_FALLBACK_MODEL}.pt"
    ).exists()
    return mlx_ok, fb_ok


def main() -> int:
    print("=" * 64)
    print("stock-pipeline 환경 진단")
    print("=" * 64)

    # 시스템
    check("플랫폼", sys.platform == "darwin", f"{platform.system()} {platform.mac_ver()[0]}")
    check("아키텍처", os.uname().machine == "arm64", os.uname().machine)
    mem = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024**3)
    check("메모리", True, f"{mem:.0f}GB")
    check("Python", sys.version_info >= (3, 11), f"{sys.version.split()[0]}")

    # 외부 바이너리
    for tool in ("node", "npx", "ffmpeg", "ffprobe", "caffeinate"):
        path = shutil.which(tool)
        check(tool, path is not None, path or "미설치")

    # ffmpeg VideoToolbox (하드웨어 인코더 필수)
    if shutil.which("ffmpeg"):
        proc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                              capture_output=True, text=True)
        vt = "h264_videotoolbox" in proc.stdout
        check("VideoToolbox 인코더", vt, "활성" if vt else "미지원 — HW 인코딩 불가")

    # API 키
    keys = [
        ("KRX_ID / KRX_PW", bool(os.getenv("KRX_ID")) and bool(os.getenv("KRX_PW")),
         "pykrx 로그인 (https://www.krx.co.kr 회원가입)"),
        ("LLM 키", bool(config.openai_key() or config.anthropic_key() or config.gemini_key()),
         f"provider={config.LLM_PROVIDER}"),
        ("TTS 키", bool(config.openai_key() or config.gemini_key() or config.elevenlabs_key()),
         f"provider={config.TTS_PROVIDER}"),
        ("YouTube 자격증명", bool(config.YOUTUBE_CLIENT_ID and config.YOUTUBE_CLIENT_SECRET), ""),
        ("YouTube 토큰", config.YOUTUBE_TOKEN_PATH.exists(), str(config.YOUTUBE_TOKEN_PATH)),
    ]
    for name, ok, detail in keys:
        check(name, ok, detail if ok else (detail or "미설정 — .env 확인"))

    # Remotion
    node_modules = config.REMOTION_DIR / "node_modules"
    check("Remotion 설치", node_modules.exists(), str(config.REMOTION_DIR))
    for link in ("cache", "output"):
        p = config.REMOTION_DIR / "public" / link
        check(f"public/{link} 링크", p.is_symlink(), str(p) if p.is_symlink() else "없음")

    # Whisper 모델 — 미리 받아두지 않으면 새벽 배치 중 폴백이 1.5GB 를
    # 내려받다가 타임아웃을 넘긴다.
    mlx_ok, fb_ok = _whisper_ready()
    check("Whisper 1순위(mxl)", mlx_ok,
          config.WHISPER_MODEL if mlx_ok else "미수신 — --prefetch-whisper")
    check("Whisper 2순위(폴백)", fb_ok,
          config.WHISPER_FALLBACK_MODEL if fb_ok else "미수신 — --prefetch-whisper")

    # launchd
    label = "com.stockpipeline.daily"
    proc = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    check("launchd 등록", label in proc.stdout, label)

    # 출력
    print()
    for icon, name, detail in results:
        line = f"  {icon} {name:<22}"
        if detail:
            line += f"  {detail}"
        print(line)

    failures = [r for r in results if r[0] == FAIL]
    warnings = [r for r in results if r[0] == WARN]
    print("=" * 64)
    print(f"통과 {len(results) - len(failures) - len(warnings)}  "
          f"경고 {len(warnings)}  실패 {len(failures)}")
    if failures:
        print("\n실패 항목 조치:")
        for _, name, _ in failures:
            print(f"  · {name}")
    print("=" * 64)
    return 1 if failures else 0


if __name__ == "__main__":
    if "--prefetch-whisper" in sys.argv:
        import stage3_audio

        print("Whisper 모델 사전 수신 중... (1순위 + 폴백)")
        sys.exit(0 if stage3_audio.prefetch_whisper_models() else 1)
    sys.exit(main())