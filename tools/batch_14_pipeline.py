"""14개 전 종목 7분 풀버전 4K 영상 제작 및 유튜브 업로드 오케스트레이터.

5대 기술적 지표 집중형 (Style A):
- 캔들스틱 분석 (장대양봉/음봉, 꼬리, 캔들 심리)
- 수급 분석 (외국인, 기관, 개인 39거래일 매매동향)
- 거래량 분석 (거래량 폭발, 거래대금, 눌림목 거래량 마름)
- 이동평균선 분석 (5일, 20일, 60일 이평선 수렴 및 골든크로스)
- 추세선, 채널, W자형 이중바닥/수렴 패턴, 지지선, 1차/2차 저항선

음성 & 자막:
- edge-tts ko-KR-InJoonNeural (+1% rate)
- Whisper 단어 타임스탬프 & 100% 원문 자막 매칭
- 4K 동적 카메라 줌인/줌아웃 & 어노테이션 포커스
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

import config
import chart_data
import facts
import stage4_render
import stage5_publish
from logger import log

# 시장 평가성 & 자본 보존형 스크리닝 통과 14대 우량 종목 바스켓
DEFAULT_14_TICKERS = [
    ("028260", "삼성물산"),       # 시장평가성 100점 (제작 및 업로드 완료)
    ("009540", "HD한국조선해양"),   # 시장평가성 95점
    ("035420", "NAVER"),          # 시장평가성 95점
    ("000660", "SK하이닉스"),     # 시장평가성 95점
    ("005930", "삼성전자"),       # 시장평가성 95점
    ("034730", "SK"),             # 시장평가성 95점
    ("012330", "현대모비스"),     # 시장평가성 91점
    ("066570", "LG전자"),         # 시장평가성 91점
    ("017670", "SK텔레콤"),       # 시장평가성 91점
    ("028670", "팬오션"),         # 시장평가성 90점
    ("011200", "HMM"),            # 시장평가성 85점
    ("012750", "에스원"),         # 시장평가성 85점
    ("030200", "KT"),             # 시장평가성 85점
    ("032640", "LG유플러스"),     # 시장평가성 85점
    ("009470", "삼화전기"),       # 시장평가성 80점
]

PROGRESS_FILE = config.STATE_DIR / "batch_14_progress.json"


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"started_at": datetime.now().isoformat(), "stocks": {}}


def save_progress(progress: dict) -> None:
    PROGRESS_FILE.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


def sanitize_text_for_tts(text: str) -> str:
    """TTS 음성 합성 전용 텍스트 정제기.
    
    괄호, 영문 병기, 특수기호 등으로 인한 나레이션 불안 및 끊김 현상을 원천 방지합니다.
    """
    # 1. 한글 바로 뒤 영문 병기 괄호 완전 제거: e.g. 골든크로스(Golden Cross) -> 골든크로스
    text = re.sub(r'([가-힣]+)\s*\([A-Za-z\s/_-]+\)', r'\1', text)
    
    # 2. 비율 표현 한글화: e.g. 2.47:1 -> 2.47대 1
    text = re.sub(r'(\d+(?:\.\d+)?)\s*:\s*(\d+)', r'\1대 \2', text)
    
    # 3. 부호 및 퍼센트 한글화: +29.1% -> 플러스 29.1퍼센트, 110% -> 110퍼센트
    text = re.sub(r'\+(\d+(?:\.\d+)?)%', r'플러스 \1퍼센트', text)
    text = re.sub(r'-(\d+(?:\.\d+)?)%', r'마이너스 \1퍼센트', text)
    text = re.sub(r'(\d+(?:\.\d+)?)%', r'\1퍼센트', text)
    
    # 4. 주요 투자 용어 및 영문 약어 발음화 (한국어 조사 결합 대응)
    acronym_map = [
        (r'F-Score', '에프 스코어'),
        (r'M-Score', '엠 스코어'),
        (r'POC', '피오씨'),
        (r'W자형', '더블유자형'),
        (r'BPS', '비피에스'),
        (r'PBR', '피비알'),
        (r'PER', '피이알'),
        (r'ROE', '알오이'),
        (r'ROIC', '알오아이씨'),
        (r'WACC', '왝'),
        (r'RSI', '알에스아이'),
        (r'MACD', '엠에이씨디'),
        (r'SMR', '에스엠알'),
        (r'DCF', '디씨에프'),
        (r'NCAV', '엔씨에이브이'),
        (r'OHLCV', '오에이치엘씨브이'),
        (r'EPC', '이피씨'),
    ]
    for pat, rep in acronym_map:
        text = re.sub(rf'(?i){pat}(?=[은는이가을를의에로와과\s\.,\(\)\[\]]|$)', rep, text)
    
    # 5. 모든 괄호 안 텍스트를 자연스럽게 문장으로 흡수 (괄호 기호 완전 탈색)
    # e.g. (1,924만 주) -> 1,924만 주, (670원) -> 670원
    text = re.sub(r'[\(\[\{]([^\(\)\[\]\{\}]+)[\)\]\}]', r' \1 ', text)
    text = text.replace('(', ' ').replace(')', ' ').replace('[', ' ').replace(']', ' ')
    
    # 6. 한국어 조사 앞 불필요한 띄어쓰기 결합 (자연스러운 발음)
    text = re.sub(r'\s+([은는이가을를과와로의에])\b', r'\1', text)
    
    # 7. 문맥상 불필요한 특수문자 및 다중 공백 정리
    text = re.sub(r'[·ㆍ/]', ' ', text)
    text = re.sub(r'[\'\"`]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def collect_stock_metrics(ticker: str, name: str) -> dict[str, Any]:
    """실측 기술적 지표 및 수급 데이터 집계 (100% 네이버 증권 서비스 연동)."""
    series = chart_data.fetch_series_naver(ticker)
    if not series or not series.get("c"):
        raise ValueError(f"{ticker} 네이버 증권 OHLCV 데이터를 불러올 수 없습니다.")

    levels = chart_data.support_resistance(series) or {}
    supply = chart_data.fetch_supply(ticker) or {}

    n = len(series["c"])
    last_idx = n - 1
    last_close = int(series["c"][last_idx])
    first_close = int(series["c"][0])

    valid_highs = [x for x in series.get("h") or [] if x and x > 0]
    valid_lows = [x for x in series.get("l") or [] if x and x > 0]
    high52 = int(max(valid_highs)) if valid_highs else last_close
    low52 = int(min(valid_lows)) if valid_lows else last_close

    ma5 = int(series["ma5"][-1]) if series.get("ma5") and series["ma5"][-1] else last_close
    ma20 = int(series["ma20"][-1]) if series.get("ma20") and series["ma20"][-1] else last_close
    ma60 = int(series["ma60"][-1]) if series.get("ma60") and series["ma60"][-1] else last_close

    vols = [v for v in series.get("v") or [] if v is not None]
    recent_vols = vols[-20:] if len(vols) >= 20 else vols
    max_v = max(recent_vols) if recent_vols else 1000000
    vol_max_idx = (len(vols) - len(recent_vols)) + recent_vols.index(max_v) if recent_vols else last_idx

    c_open = int(series["o"][vol_max_idx]) if series.get("o") else last_close
    c_close = int(series["c"][vol_max_idx]) if series.get("c") else last_close
    c_high = int(series["h"][vol_max_idx]) if series.get("h") else last_close
    chg_rate = ((c_close / c_open - 1) * 100) if c_open else 0.0

    last_vol = int(vols[-1]) if vols else 100000
    vol_multiple = max(2, int(max_v / last_vol)) if last_vol else 5

    sup = levels.get("support") or levels.get("recent_low") or int(last_close * 0.92)
    res1 = levels.get("resistance") or levels.get("recent_high") or int(last_close * 1.1)
    res2 = int(res1 * 1.15)

    f_sum = round(sum(supply.get("foreign") or []), 1)
    r_sum = round(sum(supply.get("retail") or []), 1)
    i_sum = round(sum(supply.get("institution") or []), 1)

    # 네이버 증권 매물대 분석도 및 거래량 급증 뉴스 매칭 (유튜브 학습 반영)
    import naver_finance
    vp = naver_finance.calculate_volume_profile(series) or {}
    surge_date = series.get("d", [""])[vol_max_idx] if series.get("d") else ""
    matched_n = naver_finance.match_surge_news(ticker, surge_date)
    surge_news_title = matched_n.get("title") if matched_n else ""

    # 자본 보존형(Capital Preservation) 평가 결합
    import capital_preservation
    cp_eval = capital_preservation.evaluate_capital_preservation(
        ticker=ticker,
        name=name,
        series=series,
        levels=levels,
    )

    # 주식 전문가용 종합 시장 평가성(Market Consensus & Valuation) 결합
    import market_evaluation
    try:
        m_eval = market_evaluation.build_market_evaluation_report(ticker, name)
    except Exception as e:
        log.warning("시장 평가성 수집 실패(기본값 대체): %s", e)
        m_eval = {}

    frate_val = m_eval.get("foreign_ratio") or cp_eval.get("step0_anti_manipulation", {}).get("foreign_rate", 30.6)

    return {
        "ticker": ticker,
        "name": name,
        "series": series,
        "levels": levels,
        "supply": supply,
        "last_close": last_close,
        "high52": high52,
        "low52": low52,
        "ma5": ma5,
        "ma20": ma20,
        "ma60": ma60,
        "max_vol": max_v,
        "last_vol": last_vol,
        "vol_multiple": vol_multiple,
        "vol_max_idx": vol_max_idx,
        "c_open": c_open,
        "c_close": c_close,
        "c_high": c_high,
        "chg_rate": round(chg_rate, 2),
        "sup": sup,
        "res1": res1,
        "res2": res2,
        "foreign_sum": f_sum,
        "retail_sum": r_sum,
        "inst_sum": i_sum,
        "poc_price": vp.get("poc_price", sup),
        "poc_pct": vp.get("poc_pct", 15.0),
        "is_above_poc": vp.get("is_above_poc", True),
        "surge_news": surge_news_title,
        "f_score": cp_eval["step1_moat"]["f_score"],
        "rr_ratio": cp_eval["step4_trade"]["rr_ratio"],
        "margin_of_safety_pct": cp_eval["step3_safety"]["margin_of_safety_pct"],
        "safety_status": cp_eval["step3_safety"]["status"],
        "shares_to_buy": cp_eval["step4_trade"]["shares_to_buy"],
        "disparity_20": cp_eval["step2_market"]["disparity_20"],
        "cash_allocation_pct": cp_eval["step2_market"]["cash_allocation_pct"],
        "market_cap_raw": cp_eval.get("step0_anti_manipulation", {}).get("market_cap_raw", ""),
        "foreign_rate": frate_val,
        "anti_verdict": cp_eval.get("step0_anti_manipulation", {}).get("verdict", ""),
        "anti_passed": cp_eval.get("step0_anti_manipulation", {}).get("passed", True),
        "market_eval": m_eval,
        "target_price": m_eval.get("target_price"),
        "upside_pct": m_eval.get("upside_pct"),
        "foreign_ratio": frate_val,
        "pbr": m_eval.get("pbr"),
        "bps": m_eval.get("bps"),
        "rsi": m_eval.get("rsi"),
        "selection_headline": m_eval.get("headline"),
        "selection_sub": m_eval.get("market_summary"),
        "major_holder": m_eval.get("major_holder"),
        "major_ratio": m_eval.get("major_ratio"),
        "major_total_ratio": m_eval.get("major_total_ratio"),
        "major_change_reason": m_eval.get("major_change_reason"),
        "major_change_ratio": m_eval.get("major_change_ratio"),
        "insider_buyer_count": m_eval.get("insider_buyer_count"),
        "has_treasury_cancel": m_eval.get("has_treasury_cancel"),
    }


def generate_7min_script(m: dict[str, Any]) -> list[dict[str, str]]:
    """5대 지표 중심 8개 씬 대본 생성 (시장 평가성 기반, 탈클리셰 전문 스크립트)."""
    name = m["name"]
    ticker = m["ticker"]

    import market_evaluation
    return market_evaluation.generate_market_evaluated_script(ticker, name)


async def generate_voice_and_timestamps(ticker: str, full_text: str, sections: list[dict], force: bool = False) -> tuple[Path, list[dict], list[dict]]:
    """edge-tts ko-KR-InJoonNeural 음성 합성 및 Whisper 단어 타임스탬프 추출."""
    import edge_tts
    import whisper

    cache_dir = config.CACHE_DIR / ticker
    cache_dir.mkdir(parents=True, exist_ok=True)
    voice_path = cache_dir / "voice.mp3"

    recreate_voice = True
    if voice_path.exists() and not force:
        try:
            dur_check = float(subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(voice_path)]
            ).decode().strip())
            if dur_check >= 300.0:  # 최소 5분(300초) 이상이어야 7분용 음성으로 인정
                recreate_voice = False
        except Exception:
            pass

    if recreate_voice:
        log.info("%s 7분 아나운서 음성 합성 시작 (%d자, ko-KR-InJoonNeural)...", ticker, len(full_text))
        tts_text = sanitize_text_for_tts(full_text)
        log.info("✔ TTS 음성 발음 최적화 완료 (%d자)", len(tts_text))
        comm = edge_tts.Communicate(tts_text, "ko-KR-InJoonNeural", rate="+1%")
        await comm.save(str(voice_path))
        log.info("✔ %s 음성 합성 완료: %s", ticker, voice_path.name)
    else:
        log.info("✔ %s 검증된 7분 음성 파일 재사용: %s", ticker, voice_path.name)

    log.info("%s Whisper 타임스탬프 추출...", ticker)
    model = whisper.load_model("base")
    result = model.transcribe(str(voice_path), language="ko", word_timestamps=True)

    words = []
    for seg in result.get("segments", []):
        for w in seg.get("words", []):
            word, start, end = w.get("word"), w.get("start"), w.get("end")
            if word and start is not None and end is not None:
                words.append({
                    "word": word.strip(),
                    "start": round(float(start), 2),
                    "end": round(float(end), 2),
                })

    total_dur = result["segments"][-1]["end"] if result["segments"] else 390.0

    # 문장 단위 정밀 자막 구성 (원문 100% 매칭)
    all_sentences = []
    for sec in sections:
        sents = [s.strip() for s in re.split(r"(?<=[.?!])\s+", sec["text"]) if s.strip()]
        all_sentences.extend(sents)

    total_chars = sum(len(s) for s in all_sentences)
    subtitles = []
    cur_t = words[0]["start"] if words else 0.5
    eff_dur = total_dur - cur_t - 1.0

    for s in all_sentences:
        s_dur = (len(s) / total_chars) * eff_dur if total_chars else 5.0
        subtitles.append({
            "text": s,
            "start": round(cur_t, 2),
            "end": round(cur_t + s_dur, 2),
        })
        cur_t += s_dur

    return voice_path, words, subtitles


def build_props_and_manifest(m: dict[str, Any], sections: list[dict], voice_path: Path, words: list[dict], subtitles: list[dict]) -> dict[str, Any]:
    """props_{ticker}.json 및 audio_manifest.json 갱신."""
    ticker = m["ticker"]
    name = m["name"]

    manifest_path = config.DATA_DIR / "audio_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    item_meta = {
        "ticker": ticker,
        "name": name,
        "audio": str(voice_path.resolve()),
        "timestamps": words,
        "subtitles": subtitles,
        "sections": sections,
        "long_text": "\n\n".join(s["text"] for s in sections),
        "series": m.get("series"),
        "levels": m.get("levels"),
        "supply": m.get("supply"),
        "script": {
            "name": name,
            "ticker": ticker,
            "hook": sections[0]["text"][:120],
            "body": [s["text"][:120] for s in sections[1:7]],
            "closing": sections[7]["text"][:120],
            "chart_paths": [],
        },
        "facts": {
            "name": name,
            "ticker": ticker,
            "close": f"{m['last_close']:,}원",
            "high_52w": f"{m['high52']:,}원",
            "change_rate": f"{m['chg_rate']:+.2f}%",
            "volume_ratio": f"{m['vol_multiple']}배",
            "target_price": m.get("target_price"),
            "upside_pct": m.get("upside_pct"),
            "foreign_ratio": m.get("foreign_ratio"),
            "pbr": m.get("pbr"),
            "selection_headline": m.get("selection_headline"),
            "selection_sub": m.get("selection_sub"),
        },
    }

    manifest[ticker] = item_meta
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # stage4_render._item_props 호출로 props 생성
    props = stage4_render._item_props(ticker, item_meta)
    props_path = config.DATA_DIR / f"props_{ticker}.json"
    props_path.write_text(json.dumps({"items": [props]}, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info("✔ %s props 및 manifest 저장 완료 (자막 %d개, 어노테이션 %d개)", ticker, len(subtitles), len(props.get("annotations", [])))
    return props


def run_pipeline_for_ticker(ticker: str, name: str, render_video: bool = True, upload_video: bool = True, force: bool = False) -> bool:
    """단일 종목 파이프라인 (대본·음성·자막 → 4K 렌더 → 유튜브 업로드)."""
    log.info("=" * 60)
    log.info("▶ [%s %s] 7분 풀버전 4K 제작 시작 (force=%s)", ticker, name, force)
    log.info("=" * 60)

    progress = load_progress()
    stock_p = progress["stocks"].setdefault(ticker, {"name": name, "status": "pending"})

    # 1. 지표 수집
    m = collect_stock_metrics(ticker, name)

    # 2. 7구간 대본 작성
    sections = generate_7min_script(m)
    full_text = "\n\n".join(s["text"] for s in sections)

    # 3. 음성 합성 & 타임스탬프
    voice_path, words, subtitles = asyncio.run(generate_voice_and_timestamps(ticker, full_text, sections, force=force))

    # 4. Props & Manifest 구성
    build_props_and_manifest(m, sections, voice_path, words, subtitles)
    stock_p["prepared"] = True
    save_progress(progress)

    video_path = config.OUTPUT_DIR / f"{ticker}_{name}_{datetime.now():%Y%m%d}.mp4"

    # 5. 4K 렌더 (이미 생성되고 QC 통과한 파일이 있으면 재렌더 생략)
    if render_video:
        needs_render = True
        if not force and video_path.exists() and video_path.stat().st_size > 100 * 1024 * 1024:
            qc = stage5_publish.probe(video_path)
            if qc.ok:
                log.info("✔ [%s %s] 이미 렌더링된 4K 비디오 확인 (%s, %.1fMB)", ticker, name, video_path.name, qc.size_mb)
                needs_render = False

        if needs_render:
            manifest_item = {ticker: json.loads((config.DATA_DIR / "audio_manifest.json").read_text(encoding="utf-8"))[ticker]}
            log.info("[%s %s] 4K VideoToolbox 렌더링 시작...", ticker, name)
            videos = stage4_render.render(manifest_item)
            if not videos:
                log.error("✖ [%s %s] 렌더링 실패", ticker, name)
                stock_p["status"] = "render_failed"
                save_progress(progress)
                return False

            results = stage5_publish.run_qc(videos)
            if not results or not results[0].ok:
                log.error("✖ [%s %s] QC 실패: %s", ticker, name, results[0].reason if results else "결과 없음")
                stock_p["status"] = "qc_failed"
                save_progress(progress)
                return False
            video_path = results[0].path
            log.info("✔ [%s %s] 4K 렌더 및 QC 통과: %s", ticker, name, video_path.name)

        stock_p["rendered"] = True
        stock_p["video_path"] = str(video_path)
        save_progress(progress)

    # 6. 유튜브 업로드
    if upload_video and video_path.exists():
        published_marker = video_path.with_suffix(".published")
        if published_marker.exists():
            vid = published_marker.read_text(encoding="utf-8").strip()
            log.info("✔ [%s %s] 이미 YouTube 게시됨: https://youtu.be/%s", ticker, name, vid)
            stock_p["youtube_id"] = vid
            stock_p["youtube_url"] = f"https://youtu.be/{vid}"
            stock_p["status"] = "published"
            save_progress(progress)
            return True

        log.info("[%s %s] YouTube 업로드 시작 (%s)...", ticker, name, video_path.name)
        cmd = [
            str(ROOT_DIR / "venv" / "bin" / "python3"),
            str(ROOT_DIR / "tools" / "upload_youtube.py"),
            ticker,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            vid = published_marker.read_text(encoding="utf-8").strip() if published_marker.exists() else ""
            log.info("✔ [%s %s] YouTube 업로드 완료! (id=%s)\n%s", ticker, name, vid, proc.stdout)
            stock_p["youtube_id"] = vid
            stock_p["youtube_url"] = f"https://youtu.be/{vid}" if vid else ""
            stock_p["status"] = "published"
            save_progress(progress)
        else:
            log.error("✖ [%s %s] YouTube 업로드 실패:\n%s\n%s", ticker, name, proc.stdout, proc.stderr)
            stock_p["status"] = "upload_failed"
            save_progress(progress)
            return False

    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="14개 전 종목 7분 4K 영상 제작 및 유튜브 업로드")
    parser.add_argument("--tickers", help="쉼표로 구분한 특정 종목 코드 (기본: 14개 전체)")
    parser.add_argument("--step", choices=["all", "prepare", "render", "upload"], default="all")
    parser.add_argument("--force", action="store_true", help="음성 및 렌더링 강제 재생성")
    parser.add_argument("--no-upload", action="store_true", help="유튜브 업로드 생략 (영상 제작까지만)")
    args = parser.parse_args()

    target_list = DEFAULT_14_TICKERS
    if args.tickers:
        wanted = [t.strip() for t in args.tickers.split(",") if t.strip()]
        name_dict = {t: n for t, n in DEFAULT_14_TICKERS}
        name_dict.update({
            "028260": "삼성물산",
            "005930": "삼성전자",
            "000660": "SK하이닉스",
            "012330": "현대모비스",
            "009540": "HD한국조선해양",
            "066570": "LG전자",
            "035420": "NAVER",
        })
        targets = []
        for t in wanted:
            n = name_dict.get(t)
            if not n:
                try:
                    import naver_finance
                    n = naver_finance.fetch_stock_integration(t).get("name") or t
                except Exception:
                    n = t
            targets.append((t, n))
        target_list = targets

    log.info("총 %d개 종목 배치 시작 (step=%s, force=%s, no_upload=%s)", len(target_list), args.step, args.force, args.no_upload)
    render_video = args.step in ["all", "render"]
    upload_video = args.step in ["all", "upload"] and not args.no_upload

    success_count = 0
    for idx, (ticker, name) in enumerate(target_list, 1):
        log.info("\n>>> 전체 진행률: [%d/%d] %s (%s)", idx, len(target_list), name, ticker)
        try:
            ok = run_pipeline_for_ticker(ticker, name, render_video=render_video, upload_video=upload_video, force=args.force)
            if ok:
                success_count += 1
            else:
                log.error("종목 %s 처리 실패, 다음 종목 계속 진행", ticker)
        except Exception as e:
            log.exception("[%s %s] 예외 발생: %s", ticker, name, e)

    log.info("\n==========================================")
    log.info("배치 완료: %d/%d 성공", success_count, len(target_list))
    log.info("==========================================")
    return 0 if success_count == len(target_list) else 1


if __name__ == "__main__":
    raise SystemExit(main())
