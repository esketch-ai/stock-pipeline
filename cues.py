"""대본 → 시각 큐(cue) 생성.

대본에서 수치가 언급되는 시각을 찾아, 그 구간에 맞는
지표 스트립 항목과 차트 포인터를 만든다.
Remotion 이 이 cues 를 받아 상단 지표바/포인터를 그린다.

포인터 좌표는 하드코딩이 아니라 실제 OHLCV 에서 계산한다
(build_pointer_positions) — 그래야 차트의 봉과 정확히 겹친다.
"""

from __future__ import annotations

import re

from logger import log

# ── 수치 패턴 → 지표 라벨 매핑 ──────────────────────────
# (정규식, 지표 라벨, 톤)
_NUM_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"(\d[\d,]*)\s*원"), "현재가", "flat"),
    (re.compile(r"(\d+)\s*%"), "등락률", "up"),
    (re.compile(r"(\d+)\s*배"), "거래량 배율", "up"),
    (re.compile(r"(\d[\d,]*)\s*억"), "거래대금", "flat"),
    (re.compile(r"(\d[\d,]*)\s*조"), "시가총액", "flat"),
    (re.compile(r"(\d+)\s*만\s*주"), "거래량", "flat"),
]


def _fmt(value: str, unit_hint: str = "") -> str:
    v = value.replace(",", "")
    try:
        n = int(v)
    except ValueError:
        return value
    if n >= 10000:
        return f"{n:,}"
    return str(n)


def build_pointer_positions(series: dict | None, chart_kind: str = "price") -> list[dict]:
    """주목할 '봉'을 지정한다.

    좌표(x, y)는 여기서 만들지 않는다. matplotlib 픽셀 레이아웃을 가정하는
    매직 상수를 Python 과 TypeScript 에 두 벌 두면 반드시 어긋나기 때문이다.
    이 단계는 "어느 봉을 가리킬지" 만 정하고, Remotion 이 자기 스케일로
    좌표를 계산한다.

    반환: [{"index": int, "panel": str, "label": str, "sublabel": str}, ...]
    """
    if not series or not series.get("c") or not series.get("pts"):
        return []

    try:
        pts = series["pts"]
        close = series["c"]
        ret = series.get("ret") or []
        vol = series.get("v") or []

        i_last = pts.get("last", len(close) - 1)
        i_vol = pts.get("volMax", i_last)

        vol_avg = _mean([v for v in vol[-20:] if v is not None]) or 1.0
        vol_mult = (vol[i_vol] / vol_avg) if (i_vol < len(vol) and vol[i_vol]) else 0

        if chart_kind == "return":
            i_hi, i_lo = pts.get("retMax", i_last), pts.get("retMin", i_last)
            return [
                {"index": i_hi, "panel": "return", "label": "최고 수익률",
                 "sublabel": _pct(ret, i_hi)},
                {"index": i_lo, "panel": "return", "label": "최저 수익률",
                 "sublabel": _pct(ret, i_lo)},
                {"index": i_last, "panel": "return", "label": "현재 수익률",
                 "sublabel": _pct(ret, i_last)},
                {"index": i_vol, "panel": "volume", "label": "거래량 급증",
                 "sublabel": f"평소의 {vol_mult:.0f}배"},
            ]

        # price / trend / momentum — 위쪽 패널은 가격 축이다
        i_hi = pts.get("high52", i_last)
        i_lo = pts.get("low52", i_last)
        hi = series["h"][i_hi] if i_hi < len(series["h"]) else None
        drop = ""
        if hi and close[i_last]:
            drop = f"현재 {(close[i_last] / hi - 1) * 100:.0f}% 아래"

        return [
            {"index": i_vol, "panel": "volume", "label": "거래량 급증",
             "sublabel": f"평소의 {vol_mult:.0f}배"},
            {"index": i_hi, "panel": "price", "label": "52주 고점", "sublabel": drop},
            {"index": i_lo, "panel": "price", "label": "저점", "sublabel": "이 구간에서 출발"},
            {"index": i_last, "panel": "price", "label": "현재가",
             "sublabel": f"{close[i_last]:,.0f}원" if close[i_last] else ""},
        ]
    except Exception:
        return []


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _pct(values: list[float | None], i: int) -> str:
    if i < len(values) and values[i] is not None:
        return f"{values[i]:+.0f}%"
    return ""


def build_cues(text: str, timestamps: list[dict], facts: dict | None = None,
               series: dict | None = None, chart_kinds: list[str] | None = None) -> list[dict]:
    """대본 + 타임스탬프 → cue 리스트.

    cue 는 '언제(초) 어떤 수치가 말해지는가' 를 담는다.
    포인터 좌표는 차트 종류별로 하드코딩된 대표 지점을 사용한다
    (정확한 좌표는 시각 설계 후 튜닝).
    """
    if not timestamps:
        return []

    facts = facts or {}
    cues: list[dict] = []
    seen: set[tuple[str, str]] = set()


    # 타임스탬프를 문장 단위로 묶어 문장 시작 시각을 구한다
    sentence_starts: list[float] = []
    for w in timestamps:
        word = w.get("word", "")
        if re.search(r"[.!?]$", word.strip()):
            sentence_starts.append(w.get("end", 0.0))
    if not sentence_starts:
        sentence_starts = [timestamps[-1].get("end", 30.0)]

    total = timestamps[-1].get("end", 30.0)
    # 문장 텍스트 위치 → 시각 근사치
    def _time_at(ratio: float) -> float:
        return round(ratio * total, 2)

    for pat, label, tone in _NUM_PATTERNS:
        for m in pat.finditer(text):
            raw = m.group(1)
            # 같은 지표·같은 값은 한 번만
            key = (label, raw)
            if key in seen:
                continue
            # 같은 라벨은 최대 2회까지 (등락률 8번 반복 방지)
            if sum(1 for c in cues if c["metric"]["label"] == label) >= 2:
                continue
            seen.add(key)

            at = _time_at(min(1.0, m.start() / max(1, len(text))))

            # 단위는 라벨이 아니라 실제 매칭된 패턴에서 가져온다.
            if label == "등락률":
                suffix = "%"
            elif label == "거래량 배율":
                suffix = "배"
            else:
                suffix = ""

            cue = {
                "at": at,
                "metric": {
                    "label": label,
                    "value": _fmt(raw) + suffix,
                    "tone": tone,
                },
            }
            cues.append(cue)
            if len(cues) >= 8:
                break
        if len(cues) >= 8:
            break

    cues.sort(key=lambda c: c["at"])

    # 포인터 부착 — 차트 종류별로 어떤 봉을 가리킬지 결정
    kinds = chart_kinds or ["price", "trend", "momentum", "return"]
    per_chart = [build_pointer_positions(series, k) for k in kinds]
    per_chart = [p for p in per_chart if p]
    if not per_chart:
        # series 가 없는 구버전 데이터 — PNG 폴백 화면용 레거시 좌표.
        # Remotion 은 x/y 가 있으면 그대로 쓰고, 없으면 포인터를 생략한다.
        per_chart = [[
            {"x": 0.86, "y": 0.34, "label": "최근 급등 구간"},
            {"x": 0.30, "y": 0.70, "label": "거래량 급증"},
            {"x": 0.50, "y": 0.30, "label": "52주 고점 대비"},
            {"x": 0.88, "y": 0.80, "label": "현재가"},
        ]]

    # 차트 세그먼트 길이(=1장당 시간)에 맞춰 포인터를 시간축에 분산 배치
    n_charts = len(per_chart)
    seg = total / max(1, n_charts)
    flat: list[dict] = []
    for ci, specs in enumerate(per_chart):
        for si, p in enumerate(specs):
            start = round(seg * ci + seg * (si + 0.3) / len(specs), 2)
            flat.append({**p, "from": start, "to": min(total, start + seg / len(specs) + 1.0)})

    # 기존 cue 에 포인터를 순서대로 배정 (cue 개수보다 많으면 cue 를 늘림)
    if len(flat) > len(cues):
        base = cues[-1].copy() if cues else {"metric": {}}
        for i in range(len(flat) - len(cues)):
            cues.append({"at": round(min(total, flat[i]["from"]), 2), "metric": dict(base.get("metric", {}))})
    for i, p in enumerate(flat[: len(cues)]):
        cues[i]["pointer"] = p

    cues.sort(key=lambda c: c["at"])

    log.info("cue 생성: %d개", len(cues))
    return cues


def metrics_summary(facts: dict) -> list[dict]:
    """팩트에서 상단 지표 스트립용 요약 수치를 만든다."""
    out: list[dict] = []
    mapping = [
        ("close", "현재가", "flat"),
        ("market_cap", "시가총액", "flat"),
        ("trading_value", "거래대금", "flat"),
        ("high_52w", "52주 고점", "flat"),
        ("range_pos", "52주 위치", "flat"),
    ]
    for key, label, tone in mapping:
        if facts.get(key):
            out.append({"label": label, "value": facts[key], "tone": tone})
    return out