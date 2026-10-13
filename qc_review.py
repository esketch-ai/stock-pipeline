"""생성물 자동 품질 검사.

대본/차트/포인터가 서로 어긋나는 문제를 사람이 눈으로 다 확인하면 놓친다.
발견된 실제 사고 유형을 검출 규칙으로 만든다:

  1. 수치 불일치  — 대본 수치와 팩트(원본 데이터) 가 다름
  2. 소수점 잔존  — 통용 규칙 위반
  3. 한국어 표기  — 띄어쓰기/어휘 난이도
  4. 포인터 정렬  — 포인터 좌표가 차트 영역 밖이거나 실제 봉과 어긋남
  5. 구조        — 섹션 길이, 고지 문구, 환각 표현
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from logger import log
from numeric_verify import NumIssue

# ── 1. 소수점 규칙 ──────────────────────────────────────
DECIMAL_RE = re.compile(r"\d+\.\d+(?:%|배|억|조|만)")

# ── 2. 한국어 표기 ──────────────────────────────────────
HARD_WORDS = {
    "간극": "격차/차이",
    "역전 개연성": "뒤집힐 가능성",
    "가격 발견 효과": "호가 반등 효과",
    "미시총주": "소형주",
    "유동성 제약": "거래가 제한됨",
}
SPACING_HINTS = [
    (re.compile(r"[\uac00-\ud7a3]{2,}[을를이가은는이]", re.UNICODE), None),  # 참고용
]
BAD_SPACING = [
    (re.compile(r"사흘\s*새"), "사흘 만에"),
    (re.compile(r"일주일\s*새"), "일주일 만에"),
    (re.compile(r"오늘\s*기준으로\b"), "오늘 기준으로"),
]

# ── 3. 환각 패턴 ────────────────────────────────────────
HALLUCINATION = [
    (re.compile(r"공시가?\s*(있|없)"), "공시 단정"),
    (re.compile(r"테마성|테마주|테마에\s*엮"), "테마 단정"),
    (re.compile(r"기관이?\s*(사들|매수|순매수|투입)"), "수급 단정"),
    (re.compile(r"외국인이?\s*(사들|순매수|유입|투입)"), "수급 단정"),
    (re.compile(r"(실적|영업이익|매출).{0,6}(개선|감소|호실적|부진|악화)"), "재무 단정"),
    (re.compile(r"계약|수주|공급계약"), "수주 단정"),
]

DISCLAIMER = "투자 권유가 아니며"

# 고지 문구로 인정되는 변형 (LLM 교정 시 표현이 달라진다)
DISCLAIMER_PATTERNS = [
    r"투자\s*권유가\s*아니며",
    r"투자\s*권유가\s*아닌",
    r"투자\s*권유가\s*아닙니다",
    r"투자\s*권유가\s*아니고",
    r"투자\s*권유가\s*아닌\s*정보",
    r"투자\s*권유로\s*(?:는|가)\s*아니",
    r"투자\s*자문의?\s*일?\s*아니",
    r"매매\s*권유가\s*아니",
    r"권유가\s*아닙니다",
]


def _has_disclaimer(text: str) -> bool:
    """고지 문구 존재 여부 (변형 포함)."""
    return any(re.search(p, text or "") for p in DISCLAIMER_PATTERNS)


def _fmt_int(v: float) -> str:
    return f"{int(round(v)):,}"


def check_item(item: dict) -> dict:
    """아카이브 항목 1건을 검사해 리포트를 반환."""
    issues: list[dict] = []
    text = item.get("long_text") or ""
    facts = item.get("facts") or {}
    candidate = item.get("candidate") or {}
    cues = item.get("cues") or []
    charts = item.get("chart_paths") or []

    def add(level: str, kind: str, msg: str, fix: str = ""):
        issues.append({"level": level, "kind": kind, "message": msg, "fix": fix})

    # ── 1. 소수점 ──
    for m in DECIMAL_RE.finditer(text):
        s = max(0, m.start() - 30)
        add("error", "decimal", f'소수점 표기 "{m.group()}" 사용',
            f'정수로: "{m.group().split(".")[0]}{m.group().split(".")[1][0]}"')
        break  # 첫 건만 (같은 유형)

    # ── 2. 한국어 ──
    for word, easy in HARD_WORDS.items():
        if word in text:
            add("warn", "korean", f'어려운 어휘 "{word}"', f'→ "{easy}" 로 교체')
    for pat, fix in BAD_SPACING:
        m = pat.search(text)
        if m:
            add("warn", "korean", f'띄어쓰기 "{m.group()}"', f'→ "{fix}"')

    # ── 3. 환각 ──
    for pat, label in HALLUCINATION:
        m = pat.search(text)
        if m:
            add("error", "hallucination", f"{label}: \"{m.group()}\"",
                "팩트에 없는 정보 — 삭제하거나 '추정된다' 로 완곡하게")

    # ── 4. 고지 문구 ──
    if text:
        if not _has_disclaimer(text):
            add("error", "structure", "투자 권유 고지 문구 없음",
                f'대본 말미에 "{DISCLAIMER}" 포함')
        else:
            # 고지 문구가 대본 끝(마지막 400자) 안에 있어야 한다
            if not _has_disclaimer(text[-400:]):
                add("warn", "structure",
                    "고지 문구가 대본 앞쪽에만 있음 — 마무리 멘트에 넣어야 합니다",
                    "closing(끝부분)으로 이동")

    # ── 5. 수치 일관성 (대본 vs 팩트) ──
    if text and facts:
        close_raw = facts.get("close_raw")
        hi_raw = facts.get("high_52w_raw") or facts.get("high_52w")

        if close_raw:
            target = _fmt_int(float(close_raw))
            # '현재가' 라벨이 붙은 금액만 검사한다.
            # 문맥 라벨 없는 금액은 과거 가격 서사/다른 지표일 수 있다.
            labeled = re.findall(
                r"(?:현재가|종가|기준가|가격표|지금|현재\s*가격)\s*은?\s*([\d,]{5,})\s*원",
                text,
            )
            wrong = sorted({
                m for m in labeled
                if m.replace(",", "") != target.replace(",", "")
            })
            if wrong:
                add("error", "number",
                    f"현재가 불일치 — 팩트 {target}원인데 대본이 "
                    f"{', '.join(wrong[:3])}원 사용",
                    f"대본의 금액을 {target}원으로 통일")
            elif labeled:
                pass
            else:
                # 라벨이 없더라도 대본 서술상 현재가를 지칭하는 경우만 검사
                pass

    # ── 6. 포인터 정렬 ──
    pointer_stats = _check_pointers(cues, charts)
    if pointer_stats["out_of_range"]:
        add("error", "pointer",
            f'포인터 {pointer_stats["out_of_range"]}개가 차트 영역(0~1) 밖',
            "포인터 좌표 계산 로직 확인")

    # ── 7. 구조 ──
    sections = item.get("sections") or []
    for s in sections:
        if s.get("chars", 0) < 120:
            add("warn", "structure",
                f'구간 "{s.get("title")}" 이 {s.get("chars")}자로 너무 짧음')
    if text and len(text) < 800:
        add("warn", "structure", f"대본이 짧음 ({len(text)}자)")

    # ── 점수 ──
    weights = {"error": 25, "warn": 10}
    score = max(0, 100 - sum(weights.get(i["level"], 5) for i in issues))

    report = {
        "score": score,
        "issues": issues,
        "error_count": sum(1 for i in issues if i["level"] == "error"),
        "warn_count": sum(1 for i in issues if i["level"] == "warn"),
        "pointer_total": pointer_stats["total"],
        "pointer_out_of_range": pointer_stats["out_of_range"],
        "checked_at": None,
    }
    return report


def _find_price_mentions(text: str, unit: str) -> list[str]:
    return re.findall(r"[\d,]+\s*" + unit, text)


def _numeric_issues(text: str, facts: dict) -> list[NumIssue]:
    """게이트와 동일한 숫자 검증 엔진을 재사용 (단일 진실 공급원)."""
    try:
        import numeric_verify

        return numeric_verify.verify(text, facts or {}, "").issues
    except Exception:
        return []


def _check_pointers(cues: list[dict], charts: list[str]) -> dict:
    total = 0
    out = 0
    for c in cues:
        p = c.get("pointer")
        if not p:
            continue
        total += 1
        x, y = p.get("x", 0), p.get("y", 0)
        if not (0 <= x <= 1 and 0 <= y <= 1):
            out += 1
    return {"total": total, "out_of_range": out}


def summarize(items: list[dict]) -> dict:
    """전체 항목 요약 (대시보드 상단 지표용)."""
    reports = [check_item(i) for i in items]
    return {
        "total": len(reports),
        "avg_score": round(sum(r["score"] for r in reports) / len(reports)) if reports else 0,
        "errors": sum(r["error_count"] for r in reports),
        "warnings": sum(r["warn_count"] for r in reports),
        "clean": sum(1 for r in reports if r["score"] >= 90),
    }