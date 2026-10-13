"""대본 품질 검수기.

LLM 산출물은 아무리 프롬프트를 잘 써도 가끔 규칙을 어긴다.
설명적/반복적인 대본을 걸러내기 위해 기계적으로 검사하고,
위반 시 LLM 에게 피드백을 돌려 재생성을 요청한다.

검사 항목:
  1. 반복어 — 같은 단어가 과도하게 반복되는가
  2. 나열형 — "X원입니다" 식 보고 멘트가 연속되는가
  3. 클리셰 오프닝 — "여러분, ~~ 보셨나요?" 류인가
  4. 환각 — 확인되지 않은 정보를 단정하는 표현인가
  5. 구조 — body 문장 수, 길이, 고지 문구 포함 여부
"""

from __future__ import annotations

import re
from collections import Counter

# ── 환각 패턴 (팩트 블록에 근거가 없을 때 위험한 표현) ──
HALLUCINATION_PATTERNS = [
    (r"공시가?\s*(있|없)", "공시 단정"),
    (r"테마성|테마주|테마에\s*엮", "테마 단정"),
    (r"기관이?\s*(사들|매수|순매수|투입)", "수급 단정"),
    (r"외국인(이|이들)?\s*(사들|순매수|유입|투입)", "수급 단정"),
    (r"(실적|영업이익|매출).{0,6}(개선|감소|호실적|부진|악화)", "재무 단정"),
    (r"계약|수주|공급계약", "수주 단정"),
]

# ── 금지 클리셰 ──
CLICHE_PATTERNS = [
    (r"여러분.{0,10}보셨나요", "클리셰 오프닝"),
    (r"오늘은.{0,20}다루겠습니다", "클리셰 오프닝"),
    (r"여러분.{0,6}반갑습니다", "클리셰 오프닝"),
    (r"여러분.{0,10}안녕", "클리셰 오프닝"),
]

# ── 나열형 판정 ──
REPORT_RE = re.compile(r"[\d,]+\s*(원|억|조|만|%|배)")

# ── 수식어 (군더더기) ──
FILLER = ["아주", "역시", "다시 한번", "무려", "정말로", "역으로", "바로 이"]

DISCLAIMER = "투자 권유가 아니며"

# 위배를 허용하는 최대치
MAX_REPEAT = 3          # 동일 어간 등장 허용 횟수
MAX_REPORT_RUN = 2      # 연속 나열형 멘트 허용
MIN_BODY = 4
MAX_BODY = 6


def _stem(word: str) -> str:
    """한국어 어간 근사 — 조사/어미를 제거해 같은 단어인지 판단."""
    w = word.strip()
    for suffix in ("입니다", "입니다.", "했죠", "거든요", "입니다만", "습니다",
                   "이라는", "라고", "이라는", "에서", "으로", "에게", "까지", "부터",
                   "다는", "은", "는", "이", "가", "을", "를", "의", "에", "도", "만", "와", "과"):
        if w.endswith(suffix) and len(w) > len(suffix) + 1:
            return w[: -len(suffix)]
    return w


def check(script) -> dict:
    """대본을 검사해 {'score': 0~100, 'violations': [...], 'feedback': str} 반환."""
    violations: list[str] = []
    hook = (script.hook or "").strip()
    body = [b.strip() for b in (script.body or []) if b and b.strip()]
    closing = (script.closing or "").strip()

    if not hook:
        violations.append("hook 이 비어있음")
    if len(body) < MIN_BODY:
        violations.append(f"body 문장 부족 ({len(body)}개, 최소 {MIN_BODY})")
    if len(body) > MAX_BODY:
        violations.append(f"body 문장 과다 ({len(body)}개, 최대 {MAX_BODY})")
    if not closing:
        violations.append("closing 이 비어있음")

    # 1) 반복어
    all_text = " ".join([hook, *body, closing])
    tokens = re.findall(r"[가-힣]{2,}", all_text)
    stems = Counter(_stem(t) for t in tokens)
    top_repeat = [(w, c) for w, c in stems.most_common(12) if c > MAX_REPEAT and w not in DISCLAIMER]
    for w, c in top_repeat[:4]:
        violations.append(f"반복어 '{w}' {c}회")

    # 2) 나열형 연속 구간
    run = 0
    max_run = 0
    for s in [hook, *body, closing]:
        if REPORT_RE.search(s):
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    if max_run > MAX_REPORT_RUN:
        violations.append(f"나열형 멘트 {max_run}문장 연속")

    # 3) 클리셰
    for pat, label in CLICHE_PATTERNS:
        if re.search(pat, hook):
            violations.append(f"{label} (hook)")

    # 4) 환각
    for pat, label in HALLUCINATION_PATTERNS:
        for s in [hook, *body, closing]:
            if re.search(pat, s):
                violations.append(f"{label} 단정")
                break

    # 5) 수식어
    filler_hits = [f for f in FILLER if f in all_text]
    if len(filler_hits) >= 2:
        violations.append("군더더기 수식어 과다")

    # 6) 고지 문구
    if DISCLAIMER not in closing:
        violations.append("closing 에 투자권유 고지 없음")

    # 7) 길이
    if len(all_text) < 180:
        violations.append("대본이 너무 짧음 (180자 미만)")
    if len(all_text) > 900:
        violations.append("대본이 너무 김 (900자 초과)")

    score = max(0, 100 - len(violations) * 18)
    return {
        "score": score,
        "violations": violations,
        "feedback": "; ".join(violations) if violations else "",
    }


def build_retry_prompt(original_prompt: str, script, result: dict) -> str:
    """위반 사유를 넣어 재생성을 요청하는 보강 프롬프트."""
    if not result["violations"]:
        return original_prompt

    return f"""{original_prompt}

═══════════════════════════════════════════
⚠️ 이전 시도에서 아래 규칙을 어겼습니다. 반드시 고쳐서 다시 작성하세요.
═══════════════════════════════════════════
위반 항목:
{chr(10).join(f'  ✗ {v}' for v in result['violations'])}

이전 시도:
- hook: {script.hook}
- body: {script.body}
- closing: {script.closing}

위반 사유를 먼저 머릿속에서 고친 뒤, 완전히 다른 각도로 다시 써세요.
특히 hook 은 수치를 그대로 나열하지 말고 '왜 이 숫자가 충격적인가' 에서 출발하세요.
"""