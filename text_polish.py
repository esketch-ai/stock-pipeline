"""수치 표기 표준화 + 한국어 띄어쓰기 교정.

규칙:
  1. % 는 소수점 없이 정수로 (65.22% → 65%, 78.5% → 79%, 4.58배 → 5배, 29.91% → 30%)
     —已经很接近이면 그대로, 아니면 반올림. 발표에서는 "65%" 처럼 크게 말하는 게 자연스럽다.
  2. 억원/조원 등 금액도 소수점 없이 (524.52억 → 524억)
  3. 어색한 어휘 대체 + 띄어쓰기 교정
"""

from __future__ import annotations

import re


def round_percent(v: float) -> int:
    """소수점 없이 정수 퍼센트로. 65.22 → 65, 78.5 → 79(반올림), 29.91 → 30"""
    return int(round(v))


def fmt_int_amount(v: float, unit: str = "억") -> str:
    """524.52 → '524억' (소수점 제거)."""
    return f"{int(round(v)):,}{unit}"


# ── 띄어쓰기 교정 사전 ──────────────────────────────────
# 자주 나오는 어색한 어휘를 자연스러운 표현으로
REPLACEMENTS = [
    # 어휘 부자연스러움
    (r"간극(?!이\.)", "격차"),
    (r"간극을", "격차를"),
    (r"간극이죠", "격차가죠"),
    # 띄어쓰기 오류 — 조사/어미
    (r"사흘\s*새", "사흘 만에"),
    (r"일주일\s*새", "일주일 만에"),
    (r"약\b", "약 "),
    (r"\s{2,}", " "),
]


def clean_korean(text: str) -> str:
    """한국어 띄어쓰기·어휘 교정."""
    if not text:
        return text
    out = text
    for pat, rep in REPLACEMENTS:
        out = re.sub(pat, rep, out)

    # 부자연스러운 어귀 반복 정리
    out = re.sub(r"것을\s*것", "것을", out)
    out = re.sub(r"있습니다\s*있습니다", "있습니다", out)

    return out.strip()


def normalize_numbers_in_text(text: str) -> str:
    """대본 안의 소수점 수치를 정수로 바꾼다.

    예: '65.22%' → '65%', '4.58배' → '5배', '524.52억' → '524억', '1100.32억' → '1,100억'
    단위(%, 배, 억, 조, 만)는 반드시 보존한다.
    """
    if not text:
        return text

    def _round(m: re.Match) -> str:
        # 그룹이 소수점 앞뒤로 나뉘므로 전체 값을 다시 합쳐야 한다.
        # 0.62배 를 0배 로 만들면 방향이 사라진다.
        raw = float(m.group(1) + "." + m.group(2))
        unit = m.group(3)
        if unit == "배" and raw < 1:
            return f"{raw:.1f}배"
        # 금액은 문서의 규칙대로 버린다 (524.52억 → 524억).
        # % 반올림은 0.5 에서 올림 (78.5% → 79%) — 파이썬 기본 반올림은 짝수 쪽으로 가버린다.
        value = int(raw) if unit in ("억", "조", "만") else int(raw + 0.5)
        if unit in ("억", "조", "만"):
            return f"{value:,}{unit}"
        return f"{value}{unit}"

    # 소수 + 단위(%, 배, 억, 조, 만)를 한 번에 처리
    pattern = r"(\d+)\.(\d+)(%|배|억|조|만)"
    return re.sub(pattern, _round, text)


def clean_parentheses_for_tts(text: str) -> str:
    """TTS 낭독 시 불안한 괄호 문자를 자연스러운 한국어 구어체로 정제."""
    if not text:
        return text
    # 1. (+), (-) 기호 처리
    text = re.sub(r"\(\+\)", " 플러스 ", text)
    text = re.sub(r"\(-\)", " 마이너스 ", text)
    # 2. 부호 붙은 수치 (예: +85% -> 플러스 85%)
    text = re.sub(r"\+(\d+)", r"플러스 \1", text)
    text = re.sub(r"-(\d+)", r"마이너스 \1", text)
    # 3. 괄호 안의 영문 약어 한글 발음으로 변환
    acronym_map = {
        "PBR": "피비알",
        "PER": "피이알",
        "BPS": "비피에스",
        "EPS": "이피에스",
        "ROE": "알오이",
        "ROIC": "알오아이씨",
        "RSI": "알에스아이",
        "POC": "피오씨",
        "MACD": "엠에이씨디",
        "SMR": "에스엠알",
        "WACC": "더블유에이씨씨",
        "FCF": "에프씨에프",
        "IR": "아이알",
    }
    for ac, kr in acronym_map.items():
        text = re.sub(rf"\b{ac}\b", kr, text)
    # 4. 괄호 기호 자체 제거 (발화 단절 및 괄호 열고/닫고 낭독 방지)
    text = re.sub(r"\(|\)", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def polish_for_speech(text: str) -> str:
    """발화용 텍스트 최종 정리: 괄호 정제 + 띄어쓰기 + 수치 정규화."""
    cleaned = clean_parentheses_for_tts(text)
    return normalize_numbers_in_text(clean_korean(cleaned))