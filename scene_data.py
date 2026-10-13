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

    def _time_at(char_pos: float) -> float:
        """대본 문자 위치 → 발화 시각 (인접 구간 내 선형 보간)."""
        if char_pos <= 0:
            return marks[0][1]
        if char_pos >= marks[-1][0]:
            return marks[-1][1]
        for i in range(1, len(marks)):
            c_prev, t_prev = marks[i - 1]
            c_cur, t_cur = marks[i]
            if char_pos <= c_cur:
                span = c_cur - c_prev
                ratio = (char_pos - c_prev) / span if span else 0.0
                return t_prev + (t_cur - t_prev) * ratio
        return marks[-1][1]

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

    # 씬 설계표 — (id, eyebrow, 차트 종류)
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
            "chart": chart if chart != "title" else "price",
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


def _scene_content(*, chart, name, ticker, facts, series, supply, levels,
                   last_close, high52, ma_pos, momentum, rsi_now):
    """장면별 (헤드라인, 부제, 핵심 수치).

    역할 분리 — 헤드라인은 **해석** 한 줄, stats 는 **숫자**.
    둘이 같은 말을 반복하지 않게 한다.
    """
    chg = _num(facts.get("change_rate"))
    vol_ratio = _num(facts.get("volume_ratio"))

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
