"""TTS용 숫자 정규화 — 숫자를 '읽는 대로' 한글로 바꿔 TTS에 넘긴다.

왜 필요한가:
    LLM 기반 TTS(gpt-4o-mini-tts, gemini-*-tts)는 숫자 문자열을 자릿수로
    분해해 읽는다. 라운드트립 테스트 결과:
        '37,200원'  → '3만 7천 2백원'    (37만이 아님)
        '172,800원' → '172 801'         (오독)
        '524억'     → '5,244억'         (오독)
        '1100억'    → '만 100억원'      (오독)
    시청자는 '오십칠만' 처럼 엉뚱한 숫자를 듣게 된다.

방법:
    숫자를 한국어 기준 Amount(만/억)로 분해해 한글로 읽는다.
      37,200   → 삼십칠만 이천원
      172,800  → 십칠만이천팔백원
      1,100억  → 천백억
      524억    → 오백이십사억
    숫자가 아니라 '읽을 문자열' 을 TTS 에 넘기므로 자릿수 분해가 불가능해진다.
"""

from __future__ import annotations

import re

DIGITS = "영일이삼사오육칠팔구"
SMALL_UNITS = ["", "만", "억", "조", "경"]

# 숫자가 붙는 단위 (앞/뒤 모두 처리)
NUM_UNIT = (
    "원|억원|억|천원|백원|만원|조원|조|%|퍼센트|배|배수|포인트|명|일|주|주차|개월|년|분기|개"
)


def num_to_korean(n: int) -> str:
    """정수를 한국어 기준 금액 낭독으로 변환. 37200 -> 삼십칠만이천"""
    if n == 0:
        return "영"
    if n < 0:
        return "마이너 " + num_to_korean(-n)

    groups: list[int] = []
    x = n
    while x > 0:
        groups.append(x % 10000)
        x //= 10000

    pieces: list[str] = []
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if g == 0:
            continue
        unit = SMALL_UNITS[i] if i < len(SMALL_UNITS) else ""
        head = DIGITS[g] if g < 10 else _four_digit(g)
        pieces.append(f"{head}{unit}")

    # 만/억/조 는 앞 묶음과 붙여 읽는다 (37200 -> 삼만칠천이백)
    return "".join(pieces)


def _four_digit(g: int) -> str:
    """0~9999 → '삼백칠십이'"""
    units = ["", "십", "백", "천"]
    out = []
    started = False
    for i in range(3, -1, -1):
        d = (g // (10 ** i)) % 10
        if d == 0:
            # 십/백/천 은 읽지 않는다 (삼십 vs 삼십일)
            if started and i < 3:
                pass
            continue
        started = True
        if d == 1 and i in (1, 2, 3):
            out.append(units[i])  # 십/백/천
        else:
            out.append(DIGITS[d] + units[i])
    return "".join(out)


def korean_number_with_unit(num_str: str, unit: str) -> str:
    """숫자 문자열 + 단위 -> TTS 가 정확히 읽을 한글로.

    단위 처리:
      억/조 등 큰 단위는 **값을 그 단위로 환산**해 읽는다.
        524 + 억  -> 오백이십사억
        1100 + 억 -> 천백억
      소수 단위(원/개/명)는 숫자를 그대로 읽고 단어를 붙인다.
        37200 + 원 -> 삼만칠천이백원
    """
    try:
        n = int(num_str.replace(",", ""))
    except (ValueError, AttributeError):
        return f"{num_str}{unit}"

    u = (unit or "").replace(" ", "")

    # 퍼센트/배/포인트
    if u in ("%", "퍼센트"):
        return f"{num_to_korean(n)}퍼센트"
    if u in ("배", "배수"):
        return f"{num_to_korean(n)}배"
    if u == "포인트":
        return f"{num_to_korean(n)}포인트"

    # 억/조 = 값 환산 후 읽기
    m = re.fullmatch(r"(조|억)(원)?", u)
    if m:
        big, won = m.group(1), m.group(2) or ""
        scale = {"억": 100_000_000, "조": 1_000_000_000_000}[big]
        return num_to_korean(n) + big + won

    # 만원/천원/백원 = 값 환산
    m = re.fullmatch(r"(만|천|백)원", u)
    if m:
        scale = {"백": 100, "천": 1000, "만": 10000}[m.group(1)]
        return num_to_korean(n * scale) + "원"

    # 만/억 이 단독으로 붙은 경우에도 값 환산
    if u in ("만", "억", "조"):
        scale = {"만": 10_000, "억": 100_000_000, "조": 1_000_000_000_000}[u]
        return num_to_korean(n * scale)

    # 개/명/주/일/년 등
    if u:
        return num_to_korean(n) + u

    return num_to_korean(n)


_NUM_TOKEN = re.compile(
    r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>조원|억원|천원|백원|만원|억|조|퍼센트|포인트|배수|배|%|원|명|주|개|년|개월|주차|분기|일)?"
)


def normalize_for_tts(text: str, keep_percent_sign: bool = False) -> str:
    """대본에서 숫자 표현을 TTS 가 정확히 읽을 수 있는 한글로 바꾼다.

    예:
      '동양고속 37,200원'            → '동양고속 삼십칠만이천원'
      '52주 신고가 172,800원'        → '오십이주 신고가 십칠만이천팔백원'
      '3일 동안 65%'                → '삼일 동안 육십오퍼센트'
      '1100억'                      → '천백억'
    """
    if not text:
        return text

    def repl(m: re.Match) -> str:
        num = m.group("num")
        unit = (m.group("unit") or "").strip()

        # 퍼센트 기호를 유지하는 옵션
        if keep_percent_sign and unit == "%":
            return f"{num}%"

        raw = num.replace(",", "")
        try:
            n = float(raw)
        except ValueError:
            return m.group(0)

        if n.is_integer():
            n = int(n)

        # 소수점은 그대로 (퍼센트 소수점은 정제 대상 아님)
        if isinstance(n, float) and n != int(n):
            return m.group(0)

        return korean_number_with_unit(str(int(n)), unit)

    return _NUM_TOKEN.sub(repl, text)
