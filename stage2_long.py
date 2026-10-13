"""7분 풀버전 스테이지 — 장편 대본 생성 → TTS → 단어 타임스탬프 → 렌더 props.

stage2(60~90초) / stage3 / stage4 와 병렬로 쓰는 별도 진입점.
main_orchestrator 의 VIDEO_DURATION 모드에 따라 이 경로를 쓴다.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

import config
import editorial
import investment_lenses
import cues as cues_mod
import facts as facts_mod
import script_long
import stage2_script
import stage3_audio
from config import CACHE_DIR, DATA_DIR
from logger import log
from screening import Candidate


# TTS 청크 크기 (글자). Gemini TTS 는 장편에서 변환이 느려 타임아웃이 난다.
TTS_CHUNK_CHARS = 700


def _split_for_tts(text: str, limit: int = TTS_CHUNK_CHARS) -> list[str]:
    """문장 경계를 지켜 청크로 나눈다 (잘린 문장으로 읽히지 않도록)."""
    import re as _re

    sentences = _re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[str] = []
    buf = ""
    for s in sentences:
        if len(buf) + len(s) + 1 > limit and buf:
            chunks.append(buf.strip())
            buf = ""
        buf += s + " "
    if buf.strip():
        chunks.append(buf.strip())
    return [c for c in chunks if c]


async def _tts_long(text: str, ticker: str) -> Path | None:
    """장편 전체 텍스트를 TTS 로 합성한다.

    Gemini TTS 는 한 번에 수천자를 받으면 변환이 수십 초~수 분 걸려
    ReadTimeout 이 난다. 문장 경계로 나눠 순차 합성한 뒤 이어붙인다.
    """
    out = CACHE_DIR / ticker / "voice.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)
    provider = config.TTS_PROVIDER

    chunks = _split_for_tts(text)
    if len(chunks) <= 1:
        return await _tts_one(provider, text, out)

    log.info("장편 TTS %d개 청크 분할 (%d자)", len(chunks), len(text))
    parts: list[Path] = []
    for i, chunk in enumerate(chunks, 1):
        part = out.with_name(f"voice_part{i:02d}.mp3")
        await _tts_one(provider, chunk, part)
        parts.append(part)
        log.info("  TTS 청크 %d/%d 완료 (%d자)", i, len(chunks), len(chunk))

    _concat_audio(parts, out)
    for p in parts:
        p.unlink(missing_ok=True)
    log.info("장편 TTS 합성 완료: %s (청크 %d개)", out.name, len(parts))
    return out


async def _tts_one(provider: str, text: str, out: Path) -> Path:
    if provider == "gcloud":
        return await stage3_audio._tts_gcloud(text, out)
    if provider == "gemini":
        return await stage3_audio._tts_gemini(text, out)
    if provider == "elevenlabs":
        return await stage3_audio._tts_elevenlabs(text, out)
    return await stage3_audio._tts_openai(text, out)


def _concat_audio(parts: list[Path], out: Path) -> None:
    """mp3 청크를 무손실로 이어붙인다 (concat demuxer — 재인코딩 없음)."""
    import subprocess

    list_file = out.with_suffix(".txt")
    list_file.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8"
    )
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", str(list_file), "-c", "copy", str(out)],
        capture_output=True,
    )
    list_file.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise RuntimeError(f"오디오 병합 실패: {proc.stderr.decode()[:300]}")


async def _generate_and_tts(cand: Candidate, accepted: list[dict] | None = None,
                            reserved: list[dict] | None = None) -> dict | None:
    """장편 대본 생성 → TTS → 단어 타임스탬프."""
    try:
        f = facts_mod.collect(cand.ticker, cand.name, cand.market)
    except Exception as exc:
        log.warning("%s 팩트 수집 실패: %s", cand.ticker, exc)
        f = {"ticker": cand.ticker, "name": cand.name}

    accepted = accepted if accepted is not None else []
    reserved = reserved if reserved is not None else []
    lens = investment_lenses.allocate(f, reserved)
    brief = editorial.stock_brief(f, cand.reason)
    outline = await investment_lenses.make_outline(
        facts_mod.format_facts(f), cand.reason, brief, lens,
        [p.get('outline', {'lens_id': p['lens_id'], 'question': p['question']}) for p in reserved if p is not lens],
        stage2_script._call_llm,
    )
    lens['outline'] = outline
    brief += '\n' + investment_lenses.instruction(lens) + '\n[대본 전개 계획]\n' + json.dumps(outline, ensure_ascii=False)
    weights = {s[0]: s[2] for s in script_long.SECTIONS}

    async def _write() -> dict:
        previous_openings = '\n'.join(f"{p['name']}: {p['text'][:300]}" for p in accepted)
        res = await script_long.generate_long_script(
            facts_mod.format_facts(f), cand.reason, cand.name, cand.ticker,
            stage2_script._call_llm,
            target_chars=config.LONG_TARGET_CHARS,
            section_gap=float(config.LONG_SECTION_GAP),
            editorial_brief=brief + ('\n[이번 배치에서 이미 사용한 도입 — 재사용 금지]\n' + previous_openings if previous_openings else ''),
            editorial_plan=outline,
        )
        return await script_long.repair_repetitions(
            stage2_script._call_llm, result=res,
            facts_block=facts_mod.format_facts(f), reason=cand.reason,
            stock_name=cand.name, ticker=cand.ticker, editorial_brief=brief,
            weights=weights,
        )

    result = await _write()
    # 같은 멘트가 세 번 이상 나오면 품질 기준을 통과한 것으로 보지 않는다.
    # 두 번 반복은 허용하되 재생성 단계에서 한 번 다듬을 기회를 준다.
    hard = [h for h in result.get("repetitions", []) if h["count"] >= 3]
    if hard:
        worst = max(hard, key=lambda h: h["count"])
        raise ValueError(
            f"{cand.ticker}: 반복 멘트 해소 실패 — '{worst['text'][:40]}' "
            f"({worst['count']}회, {worst['id']})"
        )
    soft = [h for h in result.get("repetitions", []) if h["count"] < 3]
    if soft:
        log.warning("%s 반복 멘트 %d건 남아 있으나 3회 미만 — 진행", cand.ticker, len(soft))

    # 종목 간 중복은 재생성 결과까지 보고 판단한다 (Gate 를 통과한 원문 기준).
    similar = [p for p in accepted
               if editorial.overlap(result['text'], p['text'], [cand.name, p['name']]) >= 0.30]
    if similar:
        raise ValueError(f'{cand.ticker}: 종목 간 대본 중복률 30% 이상')

    text = result["text"]
    if len(text) < 800:
        log.error("%s 장편 대본이 너무 짧음 (%d자) — 폴백", cand.ticker, len(text))
        return None

    log.info("장편 대본 생성 완료: %s (%d자, 예상 %.1f분)",
             cand.name, len(text), result["estimated_duration"] / 60)

    # 다중 지표 차트 생성 (방송용 — 단일 이미지 반복 방지)
    chart_paths: list[str] = []
    hist_for_cue = None
    try:
        import charts_extended
        from pykrx import stock
        import screening as _scr

        tday = _scr.last_trading_day(stock)
        end = datetime.strptime(tday, "%Y%m%d")
        hist = stock.get_market_ohlcv_by_date(
            (end - timedelta(days=365)).strftime("%Y%m%d"), tday, cand.ticker
        )
        hist_for_cue = hist
        chart_paths = charts_extended.build_indicator_charts(hist, cand.ticker, cand.name)
    except Exception as exc:
        log.warning("%s 확장 차트 생성 실패: %s", cand.ticker, exc)

    # Remotion SVG 차트가 그릴 원본 데이터.
    # DataFrame 은 JSON 직렬화가 불가능하므로 여기서 dict 로 바꿔야 한다.
    import chart_data

    series = chart_data.to_series(hist_for_cue)

    # ── 검증 게이트: 통과해야 TTS/렌더로 넘어간다 ──
    import script_gate

    gate = script_gate.validate(
        text,
        facts=f,
        reason=cand.reason,
        hist=hist_for_cue,
        call_llm=stage2_script._call_llm,
        name=cand.name,
    )
    print(script_gate.render_report(gate, cand.name))
    text = gate.text
    (DATA_DIR / f"script_long_{cand.ticker}.txt").write_text(text, encoding="utf-8")

    if not gate.passed:
        log.error(
            "%s 대본 검증 실패 — TTS/렌더 생산 중단. 대시보드에서 수정 후 재빌드하세요.",
            cand.ticker,
        )
        return {
            "name": cand.name,
            "blocked": True,
            "gate": gate.to_dict(),
            "long_text": text,
            "facts": f,
            "chart_paths": chart_paths,
            "hist": hist_for_cue,
            "series": series,
            "investors": result.get("investors", []),
            "sections": [
                {"id": s["id"], "title": s["title"], "chars": s.get("chars", 0)}
                for s in result["sections"]
            ],
        }

    # TTS: 장편 전체 텍스트를 그대로 합성한다.
    # (Script.full_text 는 hook+body+closing 만 합치므로 장편에서는 본문이 누락된다)
    # await 이전에 최종 검증본을 등록하여 동시 생성에서도 비교 대상이 누락되지 않게 한다.
    if any(editorial.overlap(text, p['text'], [cand.name, p['name']]) >= 0.30 for p in accepted):
        raise ValueError(f'{cand.ticker}: 최종 교정 후 다른 종목과 대본 중복 — TTS 중단')
    accepted.append({'ticker': cand.ticker, 'name': cand.name, 'text': text})
    try:
        audio = await _tts_long(text, cand.ticker)
    except Exception as exc:
        log.error("%s 장편 TTS 실패: %s", cand.ticker, exc)
        return None
    if not audio or not Path(audio).exists():
        log.error("%s 장편 TTS 결과 없음", cand.ticker)
        return None

    script = stage2_script.Script(
        ticker=cand.ticker,
        name=cand.name,
        hook=result["sections"][0]["text"] if result["sections"] else "",
        body=[],
        closing="이 영상은 투자 권유가 아니며, 투자 판단과 책임은 본인에게 있습니다.",
    )

    words = stage3_audio.extract_word_timestamps(
        audio, script_text=text, company_name=cand.name
    )
    log.info("%s 장편 타임스탬프 %d 토큰", cand.name, len(words))

    return {
        "name": cand.name,
        "audio": str(audio),
        "timestamps": words,
        "script": script.to_dict(),
        "long_text": text,
        "sections": [{"id": s["id"], "title": s["title"], "chars": s.get("chars", 0)} for s in result["sections"]],
        "investors": result.get("investors", []),
        "estimated_duration": result["estimated_duration"],
        "editorial_brief": brief,
        "editorial_plan": lens,
        "facts": f,
        "gate": gate.to_dict(),
        "metrics": cues_mod.metrics_summary(f) if f else [],
        "chart_paths": chart_paths,
        "hist": hist_for_cue,
        "series": series,
    }


def generate_long(candidates: list[Candidate]) -> dict[str, dict]:
    """장편 파이프라인 일괄 실행."""
    if not candidates:
        return {}

    async def _run_all():
        accepted: list[dict] = []
        reserved: list[dict] = []
        semaphore = asyncio.Semaphore(max(1, config.LLM_MAX_CONCURRENCY))
        async def generate(cand):
            async with semaphore:
                return await _generate_and_tts(cand, accepted, reserved)
        return await asyncio.gather(
            *[generate(c) for c in candidates], return_exceptions=True
        )

    results = asyncio.run(_run_all())
    manifest: dict[str, dict] = {}
    for cand, res in zip(candidates, results):
        if isinstance(res, Exception):
            log.error("장편 생성 실패 %s: %s", cand.ticker, res)
        elif res:
            manifest[cand.ticker] = res

    out = DATA_DIR / "long_manifest.json"
    # hist 는 pandas DataFrame 이라 JSON 이 될 수 없다.
    # 메모리 안에서는 script_gate / cue 계산용으로 남겨 두고,
    # 디스크에 낼 때만 뺀다 (하위 단계는 직렬화된 series 만 쓴다).
    serializable = {
        ticker: {k: v for k, v in item.items() if k != "hist"}
        for ticker, item in manifest.items()
    }
    try:
        out.write_text(
            json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except TypeError as exc:
        log.error("long_manifest 직렬화 실패 (%s) — 해당 종목을 건너뜁니다", exc)
        raise
    return manifest
