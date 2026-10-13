"""LLM 기반 한국어 교정 (의미층 오류 담당).

korean_lint 가 못 잡는 것들을 처리한다:
  - 어색한 표현, 병렬구조 불일치
  - 문장 호흡, 리듬
  - 같은 말 반복 (의역 위주)
  - 듣기 어려운 한 문장

반드시 **원문의 수치와 팩트는 절대 바꾸지 않는다.**
교정 대상은 오직 언어다. 교정 후 숫자 검증이 다시 돌기 때문에,
LLM 이 숫자를 건드리면 numeric_verify 가 잡아낸다.
"""

from __future__ import annotations

import re

from logger import log

PROOFREAD_SYSTEM = """당신은 한국어 대본 교정 전문가입니다.
방송 대본을 읽는 사람의 귀에 자연스럽게, 어색함 없이 다듬는 것이 임무입니다.

절대 규칙 (이것보다 중요합니다):
1. 숫자·단위·백분율을 절대 바꾸지 마세요. "65%"를 "64.5%"로 바꾸는 식의
   수치 변형은 절대 금지입니다.
2. 사실관계(누가, 언제, 얼마)를 바꾸지 마세요.
3. 내용을 추가하거나 삭제하지 마세요. 문장만 다듬습니다.
4. 투자 권유로 바꾸지 마세요."""

PROOFREAD_PROMPT = """아래 대본의 한국어를 교정하세요.

[교정 대상]
1. 어색한 어순, 어색한 조사
2. 한 문장에 너무 많은 내용 → 적절히 끊기
3. 같은 말의 어색한 반복 → 자연스러운 표현으로
4. 읽을 때 숨이 끊기는 긴 문장 → 2문장으로
5. 띄어쓰기·맞춤법
6. 듣기 어려운 전문 용어 → 쉬운 말

[교정하지 말 것]
- 숫자, 단위, 백분율
- 사실관계
- 문단의 순서와 내용
- 투자 권유 고지 문구

[출력]
교정된 대본 텍스트만 출력하세요. 설명이나 코멘트는 쓰지 마세요.
원문의 문단 구분(빈 줄)을 유지하세요.

──────── 원문 ────────
{text}
──────── 끝 ────────
"""


async def proofread(text: str, call_llm, name: str = "") -> tuple[str, bool]:
    """LLM 으로 대본을 교정한다.

    반환: (교정된 텍스트, 실제 교정이 수행되었는지)
    실패하면 원문을 그대로 돌려주고 False 를 함께 준다.
    (성공 여부를 텍스트 비교로만 알면 "LLM 이 손대지 않았다" 와
      "LLM 이 실패했다" 를 구분할 수 없다 — 호출부가 리포트에 쓰는 값이다)
    """
    if not text or len(text) < 100:
        return text, False

    prompt = PROOFREAD_PROMPT.format(text=text)
    try:
        raw = await call_llm(prompt)
    except Exception as exc:
        log.warning("%s 대본 교정 실패 — 원문 유지: %s", name or "", exc)
        return text, False

    corrected = _clean(raw)
    if not corrected or len(corrected) < len(text) * 0.85:
        log.warning("%s 대본 교정 결과가 부자연스럽습니다 — 원문 유지", name or "")
        return text, False

    changed = _diff_ratio(text, corrected)
    log.info("%s 대본 교정 완료 (변경 %.0f%%)", name or "", changed * 100)
    return corrected, True


def _clean(raw: str) -> str:
    t = (raw or "").strip()
    t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
    t = re.sub(r"\n?```$", "", t)
    t = re.sub(r"^#{1,6}\s*.*$", "", t, flags=re.MULTILINE)
    return t.strip()


def _diff_ratio(a: str, b: str) -> float:
    """변경 비율 대략치 (문장 단위 비교)."""
    sa = set(re.split(r"[.!?]\s+", a.strip()))
    sb = set(re.split(r"[.!?]\s+", b.strip()))
    if not sa:
        return 0.0
    return 1 - len(sa & sb) / len(sa)