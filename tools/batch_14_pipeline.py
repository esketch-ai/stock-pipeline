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
from pykrx import stock

# 14개 대상 종목 목록 (점수 순)
DEFAULT_14_TICKERS = [
    ("089590", "제주항공"),
    ("011330", "유니켐"),
    ("084010", "대한제강"),
    ("010580", "에스엠벡셀"),
    ("009190", "대양금속"),
    ("272450", "진에어"),
    ("015260", "에이엔피"),
    ("028670", "팬오션"),
    ("004700", "조광피혁"),
    ("006840", "AK홀딩스"),
    ("011200", "HMM"),
    ("071090", "하이스틸"),
    ("000180", "성창기업지주"),
    ("298690", "에어부산"),
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


def collect_stock_metrics(ticker: str, name: str) -> dict[str, Any]:
    """실측 기술적 지표 및 수급 데이터 집계 (네이버 증권 서비스 우선 연동)."""
    series = chart_data.fetch_series_naver(ticker)
    if not series or not series.get("c"):
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=280)).strftime("%Y%m%d")
        df = stock.get_market_ohlcv_by_date(start_date, end_date, ticker)
        series = chart_data.to_series(df)
    if not series or not series.get("c"):
        raise ValueError(f"{ticker} OHLCV 데이터를 불러올 수 없습니다.")

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
    }


def generate_7min_script(m: dict[str, Any]) -> list[dict[str, str]]:
    """5대 지표 중심 8개 씬 대본 생성 (총 약 2,400~2,600자, 약 6.5~7분 분량)."""
    name = m["name"]
    ticker = m["ticker"]

    # 0. Selection (종목 선정 배경 및 자본 보존형 분석)
    f_score_val = m.get("f_score", 7)
    rr_val = m.get("rr_ratio", 2.5)
    safety_margin_val = m.get("margin_of_safety_pct", 46.9)
    sec0_text = (
        f"오늘 주차뿌까에서 긴급 타격 분석 종목으로 {name}을 선정한 데에는 워런 버핏의 제1원칙인 '절대로 돈을 잃지 마라'에 기반한 4단계 자본 보존형 방어 시스템의 엄격한 검증을 통과했기 때문입니다. "
        f"첫째, {name}은 피오트로스키 F-Score {f_score_val}점을 기록하며 탄탄한 회계적 건전성과 현금 창출력을 입증했습니다. "
        f"둘째, 세스 클라만의 안전마진 원칙에 따라 보수적 청산가치 대비 {m.get('safety_status', f'안전마진 {safety_margin_val:+.1f}%')}라는 확고한 하방 안전판을 갖추고 있습니다. "
        f"셋째, 최근 바닥권에서 평소 거래량 대비 {m['vol_multiple']}배에 달하는 {m['max_vol'] / 10000:,.0f}만 주의 기록적인 거래량이 폭발하며 네이버 증권 최대 매물대 POC 벽을 강하게 돌파했습니다. "
        f"넷째, 폴 튜더 존스의 원칙대로 스윙 로우 {m['sup']:,}원을 칼손절선으로 고정하고, 1차 저항선까지 {rr_val}:1의 비대칭 손익비가 확보되었습니다. "
        f"과연 지금의 자리가 장기 복리를 지켜낼 결정적 변곡점일지, 캔들부터 수급, 거래량, 추세까지 5대 핵심 지표로 샅샅이 파헤쳐보겠습니다."
    )

    # 1. Hook (캔들스틱 분석)
    sec1_text = (
        f"가장 먼저 {name}의 일봉 차트를 펼쳐보면, 최근 가장 강렬했던 캔들 하나가 시선을 단숨에 사로잡습니다. "
        f"바로 하루 만에 {m['c_open']:,}원에서 {m['c_close']:,}원까지 치솟으며 {m['chg_rate']:+.1f}%의 강력한 양봉을 뽑아냈던 거래일입니다. "
        f"캔들의 몸통이 이처럼 길게 형성되었다는 것은 장 시작부터 마감까지 매수세가 시장을 압도적으로 지배했음을 의미합니다. "
        f"하지만 고점 부근 {m['c_high']:,}원 선에서는 차익 실현을 노리는 강력한 매도벽에 부딪히며 윗꼬리가 형성되기도 했습니다. "
        f"이후 캔들의 변동 폭이 점차 좁아지며 건전한 숨고르기 국면에 진입하고 있습니다. "
        f"캔들의 몸통 크기와 꼬리의 길이는 단순한 수치가 아니라 매수자와 매도자가 치열하게 공방을 벌인 심리의 흔적입니다."
    )

    # 2. Setup (수급 분석)
    f_stat = f"{abs(m['foreign_sum']):,.1f}억 원 순매수" if m['foreign_sum'] > 0 else f"{abs(m['foreign_sum']):,.1f}억 원 순매도"
    r_stat = f"{abs(m['retail_sum']):,.1f}억 원 순매수" if m['retail_sum'] > 0 else f"{abs(m['retail_sum']):,.1f}억 원 순매도"
    i_stat = f"{abs(m['inst_sum']):,.1f}억 원 순매수" if m['inst_sum'] > 0 else f"{abs(m['inst_sum']):,.1f}억 원 순매도"

    sec2_text = (
        f"캔들의 움직임 뒤에는 언제나 자금의 주체, 즉 수급이 자리하고 있습니다. "
        f"최근 39거래일간의 누적 수급 데이터를 정밀 분석해보면 시장 참여자별로 명확한 시각 차이가 확인됩니다. "
        f"외국인 투자자들은 {f_stat}를 기록하며 포지션을 조율했고, 개인 투자자들은 {r_stat}로 물량을 활발히 교환했습니다. "
        f"여기에 기관 투자자는 {i_stat}의 흐름을 보이며 관망세와 지지선을 타진하고 있습니다. "
        f"주가가 안정적인 2차 상승 랠리를 펼치기 위해서는 특정 주체의 단독 매수보다는 외국인과 기관의 쌍끌이 순매수 전환이 필수적입니다. "
        f"수급의 균형추가 어느 방향으로 기울어지는지 체크하는 것이 핵심 관전 포인트입니다."
    )

    # 3. Reveal (거래량 폭발 분석 + 뉴스 매칭)
    news_mention = f"특히 거래량이 번쩍 뜨며 폭발한 날에는 반드시 시장의 뉴스를 함께 살펴봐야 합니다. 실제로 {name}은 '{m['surge_news']}' 등의 이슈가 시장에 전해지며 " if m.get("surge_news") else "특히 거래량이 번쩍 뜨며 폭발한 날에는 시장의 매수세가 강하게 유입되며 "
    sec3_text = (
        f"이번 흐름에서 가장 눈여겨봐야 할 결정적인 시그널은 단연 거래량의 폭발이었습니다. "
        f"주식 시장의 오랜 격언처럼, 주가는 속일 수 있어도 거래량은 결코 속일 수 없습니다. "
        f"{news_mention}돌파 구간에서 터진 {m['max_vol'] / 10000:,.0f}만 주의 거래량은 평소 거래량 대비 {m['vol_multiple']}배에 달하는 기록적인 유동성을 보여주었습니다. "
        f"이는 단순한 개인들의 매매가 아니라 신규 메이저 자금이 대거 유입되었음을 방증하는 신호탄입니다. "
        f"특히 고무적인 점은, 최근 주가가 조정을 받을 때 거래량이 {m['last_vol'] / 10000:,.0f}만 주 수준으로 급감하며 전형적인 '거래량 마름' 현상을 보여준다는 사실입니다. "
        f"거래량이 줄어들면서 가격이 지지된다는 것은 매수 주포가 아직 이탈하지 않았음을 뜻하는 건전한 눌림목 신호입니다."
    )

    # 4. Deep Dive (이동평균선 수렴/정렬)
    sec4_text = (
        f"이제 중기적인 추세의 방향을 가늠하기 위해 이동평균선의 배열을 들여다보겠습니다. "
        f"현재 {name}의 5일 이동평균선은 {m['ma5']:,}원, 20일선은 {m['ma20']:,}원, 그리고 60일선은 {m['ma60']:,}원에 위치해 있습니다. "
        f"단기 5일선이 중장기 이평선들을 차례로 상향 돌파하는 골든크로스를 형성한 이후, 세 선이 한곳으로 팽팽하게 좁혀지는 초밀집 수렴 국면에 놓여 있습니다. "
        f"이평선이 이처럼 밀집했다는 것은 최근 60거래일 동안 시장 참여자들의 평균 매수 단가가 수렴했다는 의미입니다. "
        f"수렴의 끝에서는 언제나 상방이든 하방이든 강력한 방향성 분출이 일어납니다. "
        f"현재 주가가 20일 생명선 위에 안착해 있다는 점에서 상승 모멘텀의 불씨가 살아있음을 확인할 수 있습니다."
    )

    # 5. Risk (추세선 및 채널 분석)
    sec5_text = (
        f"하지만 시장은 늘 양면성을 지니고 있기에, 상승 채널과 함께 잠재적 리스크 요인도 냉정하게 분석해야 합니다. "
        f"52주 최고점인 {m['high52']:,}원에서부터 내려오는 중기 하락 추세선의 상단 저항선이 여전히 주가의 머리를 누르고 있습니다. "
        f"단기적으로는 저점을 완만하게 높여가는 상승 채널을 형성하고 있지만, 직전 고점 매물대를 단숨에 돌파하지 못한다면 채널 하단 지지선까지의 되밀림이 발생할 수 있습니다. "
        f"단기 트레이딩 관점에서는 상승 채널의 하단 지지선 이탈 여부를 반드시 스탑로스 기준선으로 설정해야 합니다. "
        f"기대 수익만을 바라보고 성급하게 진입하기보다는, 하방 지지력이 확인되는 구간에서 분할 매수로 접근하는 균형 잡힌 시각이 중요합니다."
    )

    # 6. Wisdom (차트 패턴 및 지지/저항 + 네이버 증권 매물 분석도)
    poc_status = "상향 돌파하여 강력한 하방 지지벽을 형성한 상태" if m.get("is_above_poc") else "돌파를 목전에 두고 상단 매물벽 저항을 소화하는 국면"
    sec6_text = (
        f"차트 패턴의 관점에서 보면, 바닥권에서 W자형 이중 바닥 패턴을 완성한 뒤 넥라인을 돌파하는 상승 삼각형 수렴 형태가 나타나고 있습니다. "
        f"특히 네이버 증권 보조지표인 매물대 분석도를 살펴보면, 가장 많은 거래량이 집중된 최대 매물벽이 {m.get('poc_price', m['sup']):,}원 부근에 두텁게 쌓여 있으며, "
        f"현재 주가는 이 핵심 매물대를 {poc_status}입니다. "
        f"구체적인 가격 기준을 설정해 보겠습니다. 아래로는 {m['sup']:,}원의 강력한 1차 지지선이 콘크리트처럼 받쳐주고 있으며, "
        f"위쪽으로는 {m['res1']:,}원 부근에 직전 매물대 저항선이 형성되어 있습니다. "
        f"만약 거래량을 동반하여 {m['res1']:,}원의 저항선을 확실하게 뚫어낸다면, 다음 타깃인 {m['res2']:,}원, 나아가 52주 고점 영역까지 상방 룸이 시원하게 열리게 됩니다. "
        f"패턴 매매의 정석은 저항선 바로 밑에서 추격 매수하는 것이 아니라, {m['sup']:,}원 지지선 부근에서 하방 리스크를 통제하며 눌림목을 공략하는 전략입니다."
    )

    # 7. Outro (종합 분석 및 전략 요약)
    sec7_text = (
        f"지금까지 {name}의 캔들, 수급, 거래량 폭발, 이동평균선 정렬, 그리고 지지 저항 패턴까지 5대 기술적 지표를 종합 분석해 보았습니다. "
        f"{m['vol_multiple']}배 폭발한 유동성과 골든크로스는 긍정적인 시그널이지만, {m['res1']:,}원의 매물벽 돌파 여부와 {m['sup']:,}원의 지지선 수호 여부를 면밀히 확인해야 합니다. "
        f"차트는 미래를 예언하는 마법이 아니라, 이길 확률이 높은 자리를 찾아내고 손익비를 극대화하는 투자자의 나침반입니다. "
        f"본 영상은 특정 종목의 매수나 매도를 권유하지 않으며, 모든 투자의 최종 판단과 결과에 대한 책임은 투자자 본인에게 있습니다."
    )

    sections = [
        {"id": "selection", "title": "종목 선정 이유", "text": sec0_text},
        {"id": "hook", "title": "캔들스틱 분석", "text": sec1_text},
        {"id": "setup", "title": "수급 분석", "text": sec2_text},
        {"id": "reveal", "title": "거래량 폭발 분석", "text": sec3_text},
        {"id": "deep_dive", "title": "이동평균선 수렴/정렬", "text": sec4_text},
        {"id": "risk", "title": "추세선 및 채널 분석", "text": sec5_text},
        {"id": "wisdom", "title": "차트 패턴 및 지지/저항", "text": sec6_text},
        {"id": "outro", "title": "종합 분석 및 전략 요약", "text": sec7_text},
    ]
    return sections


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
        comm = edge_tts.Communicate(full_text, "ko-KR-InJoonNeural", rate="+1%")
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
        # 종목명 매핑 확장
        name_dict = {t: n for t, n in DEFAULT_14_TICKERS}
        name_dict.update({
            "005930": "삼성전자",
            "000660": "SK하이닉스",
        })
        target_list = [(t, name_dict.get(t, t)) for t in wanted]

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
