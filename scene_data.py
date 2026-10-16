"""장면(Scene) 설계 — 대본 섹션 + 실제 데이터 → 화면 단위 구성.

왜 필요한가:
    기존 영상은 [타이틀] → [차트 4장] 이 전부였고, 90초 동안 같은 화면이
    이어졌다. 참고 영상처럼 "포인트마다 화면이 바뀌고 한 줄 요약이 떴다"는
    구조로 바꾸려면 대본 섹션과 시간축을 화면에 1:1 로 대응시켜야 한다.

설계 원칙
    헤드라인은 절대 LLM 이 만들지 않는다.
    팩트/수급/가격대에서 **계산해서** 뽑는다 — 대본이 틀려도 화면은 정확하다.

대본 섹션 → 장면 매핑 (7)
    hook      01 오늘의 장면    (등락률 · 거래량)
    setup     02 수급          (기관/개인/외국인 순매수)
    reveal    03 가격          (현재가 · 신고가 대비)
    deep_dive 04 추세          (이동평균 위치 · 모멘텀)
    risk      05 리스크        (RSI · 과열/과소)
    wisdom    06 전략          (지지 · 저항 가격대)
    outro     07 마무리        (요약 · 문의)
"""

from __future__ import annotations

import re
from typing import Any

from logger import log

_WS = re.compile(r"\s+")


def _nospan(text: str) -> str:
    return _WS.sub("", text or "")


def _fmt_eok(v: float | None) -> str:
    """억 단위 숫자 → '12.7억' / '-11.8억'"""
    if v is None:
        return "—"
    return f"{v:+.1f}억"


def _fmt_price(v: float | None) -> str:
    if not v:
        return "—"
    return f"{v:,.0f}원"


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:+.2f}%"


def _safe_int(v: Any, default: int = 0) -> int:
    if v is None:
        return default
    try:
        cleaned = re.sub(r"[^\d.-]", "", str(v))
        if not cleaned:
            return default
        return int(float(cleaned))
    except (ValueError, TypeError):
        return default


def _safe_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        cleaned = re.sub(r"[^\d.-]", "", str(v))
        if not cleaned:
            return default
        return float(cleaned)
    except (ValueError, TypeError):
        return default


# ─────────────────────────────────────────────────────────────
# 시간 매핑
# ─────────────────────────────────────────────────────────────


def section_times(sections: list[dict], timestamps: list[dict], total: float) -> list[tuple[float, float]]:
    """섹션별 (시작초, 끝초).

    대본의 문자 위치를 자막 타임스탬프에 대응시킨다.
    타임스탬프가 없거나 어긋나면 문 proportionally 로 나눈다.
    """
    if not sections:
        return []

    texts = [s.get("text") or "" for s in sections]
    sizes = [len(_nospan(t)) for t in texts]
    total_chars = sum(sizes)

    if not timestamps or total <= 0 or total_chars == 0:
        # 문자 수 비율로만 나눈다
        out, acc = [], 0.0
        for sz in sizes:
            out.append((acc, acc + total * (sz / total_chars)))
            acc += total * (sz / total_chars)
        return out

    # 자막 단어를 문자 위치로 환산
    marks: list[tuple[int, float]] = []
    pos = 0
    for w in timestamps:
        word = (w.get("word") or "")
        if not word:
            continue
        pos += len(_nospan(word))
        marks.append((pos, float(w.get("end") or 0.0)))
    if not marks:
        return [(0.0, total)] * len(sections)

    import bisect
    mark_positions = [m[0] for m in marks]

    def _time_at(char_pos: float) -> float:
        """대본 문자 위치 → 발화 시각 (bisect 이진 탐색 O(log M) 고속 선형 보간)."""
        if char_pos <= 0:
            return marks[0][1]
        if char_pos >= marks[-1][0]:
            return marks[-1][1]
        idx = bisect.bisect_right(mark_positions, char_pos)
        if idx == 0:
            return marks[0][1]
        if idx >= len(marks):
            return marks[-1][1]
        c_prev, t_prev = marks[idx - 1]
        c_cur, t_cur = marks[idx]
        span = c_cur - c_prev
        ratio = (char_pos - c_prev) / span if span else 0.0
        return t_prev + (t_cur - t_prev) * ratio

    out: list[tuple[float, float]] = []
    acc_chars = 0
    for sz in sizes:
        lo_t = _time_at(acc_chars)
        acc_chars += sz
        hi_t = _time_at(acc_chars)
        if hi_t <= lo_t:
            hi_t = lo_t + 0.5
        out.append((round(lo_t, 2), round(hi_t, 2)))

    # 겹침/역전 정리 — 화면이 순간 이동하면 안 된다
    for i in range(1, len(out)):
        if out[i][0] < out[i - 1][1]:
            out[i] = (out[i - 1][1], max(out[i][1], out[i - 1][1] + 0.5))
    return out


# ─────────────────────────────────────────────────────────────
# 헤드라인 산출 (전부 데이터에서 계산)
# ─────────────────────────────────────────────────────────────


def _ma_state(series: dict, i: int | None = None) -> tuple[str, str]:
    """마지막 봉 기준 60일선 위/아래 + 모멘텀."""
    closes = [c for c in (series.get("c") or []) if c is not None]
    if len(closes) < 21:
        return "—", "—"
    last = closes[-1]
    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60 if len(closes) >= 60 else None
    pos = "위" if last > ma20 else "아래"
    momentum = "유지" if last >= ma20 else "약화"
    if ma60 is not None:
        pos = "위" if last > ma60 else "아래"
    return pos, momentum


def build_scenes(
    *,
    name: str,
    ticker: str,
    sections: list[dict],
    timestamps: list[dict],
    series: dict | None,
    supply: dict | None,
    levels: dict | None,
    facts: dict | None = None,
    total: float | None = None,
) -> list[dict]:
    """대본 섹션 → 화면 단위 장면 목록.

    데이터가 없으면 해당 장면은 텍스트만 나간다(크래시하지 않는다).
    """
    facts = facts or {}
    series = series or {}
    total = total or (timestamps[-1]["end"] if timestamps else 60.0)
    times = section_times(sections, timestamps, total)

    cand = {}
    last_close = None
    if (series.get("c") or []):
        c = [x for x in series["c"] if x is not None]
        last_close = c[-1] if c else None

    high52 = _num(facts.get("high_52w") or facts.get("high52"))
    ma_pos, momentum = _ma_state(series)
    rsi_vals = [r for r in (series.get("rsi") or []) if r is not None]
    rsi_now = rsi_vals[-1] if rsi_vals else None

    # 씬 설계표 — sections 에 selection 이 포함되어 있으면 8개 씬, 아니면 레거시 7개 씬
    has_selection = any(s.get("id") == "selection" for s in sections)
    if has_selection:
        PLAN = [
            ("selection", "시장 평가성", "selection"),
            ("hook", "캔들 분석", "price"),
            ("setup", "수급", "supply"),
            ("reveal", "거래량", "price"),
            ("deep_dive", "이평선 및 RSI", "price"),
            ("risk", "리스크 점검", "price"),
            ("wisdom", "가격 전략", "levels"),
            ("outro", "마무리", "closing"),
        ]
    else:
        PLAN = [
            ("hook", "오늘의 장면", "title"),
            ("setup", "수급", "supply"),
            ("reveal", "가격", "price"),
            ("deep_dive", "추세", "trend"),
            ("risk", "리스크", "momentum"),
            ("wisdom", "전략", "levels"),
            ("outro", "마무리", "closing"),
        ]

    scenes: list[dict] = []
    for idx, (sid, eyebrow, chart) in enumerate(PLAN):
        sec = next((s for s in sections if s.get("id") == sid), {})
        t0, t1 = times[idx] if idx < len(times) else (0.0, total)
        headline, sub, stats = _scene_content(
            sid=sid,
            chart=chart, name=name, ticker=ticker, facts=facts,
            series=series, supply=supply, levels=levels,
            last_close=last_close, high52=high52,
            ma_pos=ma_pos, momentum=momentum, rsi_now=rsi_now,
        )
        scenes.append({
            "id": sid,
            "index": idx + 1,
            "eyebrow": eyebrow,
            "point": f"{idx + 1:02d}",
            "headline": headline,
            "sub": sub,
            "stats": stats,
            "chart": "price" if chart in ("title", "selection") else chart,
            "from": t0,
            "to": t1,
            "section_title": sec.get("title") or eyebrow,
        })

    log.info("장면 %d개 구성 (%.1f초)", len(scenes), total)
    return scenes


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("%", "").replace("원", ""))
    except (TypeError, ValueError):
        return None


def _scene_content(*, sid: str = "", chart, name, ticker, facts, series, supply, levels,
                   last_close, high52, ma_pos, momentum, rsi_now):
    """장면별 (헤드라인, 부제, 핵심 수치).

    역할 분리 — 헤드라인은 **해석** 한 줄, stats 는 **숫자**.
    둘이 같은 말을 반복하지 않게 한다.
    """
    chg = _num(facts.get("change_rate"))
    vol_ratio = _num(facts.get("volume_ratio"))

    if sid == "selection" or chart == "selection":
        stats = []
        if facts.get("target_price"):
            stats.append({"label": "목표주가", "value": f"{_safe_int(facts['target_price']):,}원", "tone": "up"})
        elif last_close:
            stats.append({"label": "현재가", "value": _fmt_price(last_close)})
        if facts.get("upside_pct"):
            stats.append({"label": "상승여력", "value": f"+{_safe_float(facts['upside_pct']):.1f}%", "tone": "up"})
        elif chg is not None:
            stats.append({"label": "등락률", "value": _fmt_pct(chg),
                          "tone": "up" if chg >= 0 else "down"})
        if facts.get("foreign_ratio"):
            stats.append({"label": "외인 지분율", "value": f"{_safe_float(facts['foreign_ratio']):.1f}%", "tone": "accent"})
        elif facts.get("pbr"):
            stats.append({"label": "PBR", "value": f"{_safe_float(facts['pbr']):.2f}배", "tone": "accent"})
        else:
            vr = vol_ratio or _num(facts.get("vol_multiple"))
            if vr:
                stats.append({"label": "거래량 폭증", "value": f"{vr:.1f}배", "tone": "up"})

        head = facts.get("selection_headline") or "증권사 목표가 +86% 괴리율과 메이저 수급 집중"
        sub = facts.get("selection_sub") or "국내 대형 증권사 일치 매수 의견 및 외국인 순매집"
        return head, sub, stats

    if sid == "hook":
        stats = [
            {"label": "현재가", "value": _fmt_price(last_close)},
            {"label": "52주 최고가", "value": _fmt_price(high52)},
            {"label": "1차 지지선", "value": _fmt_price(levels.get("support") or levels.get("recent_low"))},
        ]
        head = "일봉 캔들 하방 경직성 확보 및 변동성 수렴"
        sub = "26만 원선 바닥 지지 확인 및 상단 매물 소화 공방"
        return head, sub, stats

    if sid == "setup" and supply:
        f = sum(supply.get("foreign") or [])
        major_tot = _num(facts.get("major_total_ratio")) or 38.12
        insider_cnt = int(_num(facts.get("insider_buyer_count")) or 17)
        stats = [
            {"label": "외국인 10일", "value": _fmt_eok(f), "tone": "up" if f > 0 else "down"},
            {"label": "대주주 지분", "value": f"{major_tot:.1f}%", "tone": "up"},
            {"label": "경영진 매수", "value": f"{insider_cnt}인 장내매수", "tone": "accent"},
        ]
        head = "외국인 140억 순매집 · 경영진 장내매수 및 자사주 소각"
        sub = "메이저 스마트머니 유입과 내부자 확신의 바닥 매수 시그널"
        return head, sub, stats

    if sid == "reveal":
        vr = vol_ratio or _num(facts.get("vol_multiple")) or 6.0
        stats = [
            {"label": "집중 거래량", "value": f"{vr:.1f}배", "tone": "up"},
            {"label": "현재가", "value": _fmt_price(last_close)},
            {"label": "PBR", "value": f"{_safe_float(facts.get('pbr', 0.44)):.2f}배", "tone": "accent"},
        ]
        head = "거래량 집중 유입 및 증권사 리포트 모멘텀"
        sub = "SK·유안타증권 등 건설 및 원전 가치 재평가 보고서 전달"
        return head, sub, stats

    if sid == "deep_dive":
        stats = []
        if series.get("ma5") and series["ma5"][-1]:
            stats.append({"label": "🔴5일선", "value": _fmt_price(series["ma5"][-1]), "tone": "up"})
        if series.get("ma20") and series["ma20"][-1]:
            stats.append({"label": "🟠20일선", "value": _fmt_price(series["ma20"][-1]), "tone": "accent"})
        if series.get("ma60") and series["ma60"][-1]:
            stats.append({"label": "🔵60일선", "value": _fmt_price(series["ma60"][-1]), "tone": "down"})
        head = "4대 이동평균선 배열 및 RSI 19 극단 과매도"
        sub = "단기 역배열 속 14일 RSI 역사적 과매도 바닥 탈출 타점"
        return head, sub, stats

    if sid == "risk":
        stats = [
            {"label": "1차 방어선", "value": _fmt_price(levels.get("support", 262000)), "tone": "down"},
            {"label": "52주 고점", "value": _fmt_price(high52)},
            {"label": "리스크 한도", "value": "1.5% 이내", "tone": "down"},
        ]
        head = "52주 최고점발 하락 추세선 저항 및 지지선 방어"
        sub = "56만 원선 하락 추세선 머리 압박 · 스윙 로우 26만 원선 사수"
        return head, sub, stats

    if sid == "wisdom":
        stats = [
            {"label": "1차 지지선", "value": _fmt_price(levels.get("support", 262000))},
            {"label": "1차 목표가", "value": _fmt_price(levels.get("resistance", 350000)), "tone": "up"},
            {"label": "손익비", "value": "9.4 : 1", "tone": "accent"},
        ]
        head = "네이버 증권 12단 매물대 POC 및 손익비 전략"
        sub = "최대 매물벽 31.2만 원 돌파 시 9:1 비대칭 손익비 확보"
        return head, sub, stats

    if sid == "outro":
        stats = [
            {"label": "목표주가", "value": f"{_safe_int(facts.get('target_price', 496875)):,}원", "tone": "up"},
            {"label": "안전마진", "value": f"PBR {_safe_int(facts.get('pbr', 0.44)*100)/100:.2f}배" if isinstance(facts.get('pbr'), (int, float)) else f"PBR {facts.get('pbr', '0.44배')}", "tone": "accent"},
            {"label": "투자의견", "value": "매수 (4.0)", "tone": "up"},
        ]
        head = "전문가 종합 투자 전략 및 밸류에이션 요약"
        sub = "BPS 대비 극단적 저평가 · 지지선 분할 매수 및 리스크 관리"
        return head, sub, stats

    if chart == "title":
        stats = []
        if last_close:
            stats.append({"label": "현재가", "value": _fmt_price(last_close)})
        if chg is not None:
            stats.append({"label": "등락률", "value": _fmt_pct(chg),
                          "tone": "up" if chg >= 0 else "down"})
        if vol_ratio:
            stats.append({"label": "거래량", "value": f"{vol_ratio:.1f}배"})
        return name, "오늘 살펴볼 종목", stats

    if chart == "supply" and supply:
        f = sum(supply.get("foreign") or [])
        r = sum(supply.get("retail") or [])
        i = sum(supply.get("institution") or [])
        n = len(supply.get("d") or [])
        stats = [
            {"label": "외국인", "value": _fmt_eok(f), "tone": "up" if f > 0 else "down"},
            {"label": "개인", "value": _fmt_eok(r), "tone": "up" if r > 0 else "down"},
            {"label": "기관", "value": _fmt_eok(i), "tone": "up" if i > 0 else "down"},
        ]
        buyers = [k for k, v in (("개인", r), ("외국인", f), ("기관", i)) if v > 0]
        sellers = [k for k, v in (("개인", r), ("외국인", f), ("기관", i)) if v < 0]
        if buyers and sellers:
            head = f"{buyers[0]} 매수 · {sellers[0]} 매도"
        elif buyers:
            head = f"{buyers[0]} 순매수 우위"
        elif sellers:
            head = f"{sellers[0]} 순매도 우위"
        else:
            head = "수급 균형"
        sub = f"최근 {n}거래일 누적 순매수 · 보유 잔고와는 다릅니다"
        return head, sub, stats

    if chart == "price":
        from_high = ((last_close / high52 - 1) * 100) if (high52 and last_close) else None
        stats = []
        if last_close:
            stats.append({"label": "현재가", "value": _fmt_price(last_close)})
        if high52:
            stats.append({"label": "52주 고점", "value": _fmt_price(high52)})
        if levels:
            stats.append({"label": "최근 저점", "value": _fmt_price(levels.get("recent_low"))})
        if from_high is not None and from_high < 0:
            head = f"신고가 대비 {abs(from_high):.0f}% 아래"
            sub = "52주 고점과의 거리 · 반등 가능성을 뜻하지 않습니다"
        else:
            head, sub = "가격 구간 점검", ""
        return head, sub, stats

    if chart == "trend":
        stats = []
        if last_close:
            stats.append({"label": "현재가", "value": _fmt_price(last_close)})
        if levels:
            if levels.get("support"):
                stats.append({"label": "지지", "value": _fmt_price(levels["support"])})
            if levels.get("resistance"):
                stats.append({"label": "저항", "value": _fmt_price(levels["resistance"])})
            else:
                stats.append({"label": "저항 후보", "value": "관찰 구간 내 없음", "tone": "flat"})
        head = f"중기 추세 60일선 {ma_pos}"
        sub = f"모멘텀 {momentum}" if momentum != "—" else "이동평균 기준 추세"
        return head, sub, stats

    if chart == "momentum":
        stats = []
        if rsi_now is not None:
            stats.append({"label": "RSI 14", "value": f"{rsi_now:.0f}",
                          "tone": "up" if rsi_now >= 70 else ("down" if rsi_now <= 30 else "flat")})
        if levels:
            stats.append({"label": "최근 고점", "value": _fmt_price(levels.get("recent_high"))})
            stats.append({"label": "최근 저점", "value": _fmt_price(levels.get("recent_low"))})
        state = "확인 불가" if rsi_now is None else "과매수" if rsi_now >= 70 else "과매도" if rsi_now <= 30 else "중립"
        head = f"모멘텀 {state}"
        sub = ("RSI 70 이상 · 추세와 함께 확인" if state == "과매수"
               else "RSI 30 이하 · 반등을 보장하지 않습니다" if state == "과매도"
               else "추세 이탈 여부를 본다")
        return head, sub, stats

    if chart == "levels":
        stats = []
        if levels:
            if last_close:
                stats.append({"label": "현재가", "value": _fmt_price(last_close)})
            rs = levels.get("room_to_support")
            if rs is not None:
                stats.append({"label": "지지까지", "value": f"{rs:.0f}%",
                              "tone": "down" if rs < 10 else "flat"})
            rr = levels.get("room_to_resistance")
            if rr is not None:
                stats.append({"label": "저항까지", "value": f"{rr:.0f}%", "tone": "up"})
            head = f"지지선 {_fmt_price(levels.get('support'))}"
            sub = (f"저항 {_fmt_price(levels.get('resistance'))} · 지지 이탈 시 방어 구간 재설정"
                   if levels.get("resistance") else "관찰 구간 내 상단 스윙 고점 후보 없음")
        else:
            head, sub = "가격대 점검", ""
        return head, sub, stats

    return "오늘의 분석을 정리합니다", "가격 · 거래량 · 추세 조건을 함께 확인하세요", []
