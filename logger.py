"""구조화된 단계 로깅 + 단계별 소요 시간/메모리 기록."""

from __future__ import annotations

import logging
import resource
import sys
import time
from contextlib import contextmanager

from config import LOG_DIR


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")

    file_handler = logging.FileHandler(LOG_DIR / "pipeline.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    logger.addHandler(stream)
    return logger


log = get_logger("pipeline")


def peak_rss_mb() -> float:
    """macOS ru_maxrss는 바이트 단위."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)


@contextmanager
def stage(name: str):
    """단계 실행 래퍼 — 시작/종료/경과시간/최대 RSS 로그."""
    log.info("=" * 62)
    log.info("▶ START %s", name)
    started = time.time()
    try:
        yield
    except Exception:
        log.exception("✖ FAIL  %s (%.1fs)", name, time.time() - started)
        raise
    log.info("✔ DONE  %s (%.1fs, peak RSS %.0fMB)", name, time.time() - started, peak_rss_mb())