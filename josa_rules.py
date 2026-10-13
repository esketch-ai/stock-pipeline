"""국어 신조법 조사 검사 — 외부 맞춤법 검사기(bareun) 부재 시 대체.

왜 별도 모듈인가:
    바른 API 는 라이선스/네트워크 문제로 죽을 수 있다.
    그때 조용히 통과시키면 '격차을' 같은 오류가 영상에 그대로 나간다.
    조사는 국어 신조법이라 **규칙만으로 판정 가능**하다.

    받침 있는 명사: 기간이, 자막을, 고속도로가
    받침 없는 명사: 판매가, 격차를

한글 음절 분해:
    code = ord(ch) - 0xAC00
    종성(받침) = code % 28   (0 이면 받침 없음)

★ 은/는 은 **검사하지 않는다.**
  '있는' '읽는' '솟는' '잃는' '남는' 은 '있다+는' 처럼 **연결어미** 다.
  받침 ㄴ(종성 7) 뒤에는 '는' 이 와도 맞기 때문에 조사를 구분할 수 없다.
  오탐이 커서 '을/를' '이/가' 만 검사한다.
"""

from __future__ import annotations

HANGUL_BASE = 0xAC00
HANGUL_LAST = 0xD7A3

# 조사 문자 -> 조사 이름 (조사 쌍만 다룬다)
_C2K = {
    chr(0xC744): "을",  # 을
    chr(0xB97C): "를",  # 를
    chr(0xC774): "이",  # 이
    chr(0xAC00): "가",  # 가
}
_K2C = {v: k for k, v in _C2K.items()}

# (조사, 이 조사가 맞으려면 앞글자에 받침이 필요한가, 짝이 되는 조사)
_PAIRS = [
    ("을", True, "를"),   # 받침 있는 명사 + 을
    ("를", False, "을"),  # 받침 없는 명사 + 를
    ("이", True, "가"),   # 받침 있는 명사 + 이
    ("가", False, "이"),  # 받침 없는 명사 + 가
]


def has_batchim(ch: str) -> bool:
    """한글 음절이 받침을 가지는지."""
    if not ch or not (HANGUL_BASE <= ord(ch) <= HANGUL_LAST):
        return False
    return (ord(ch) - HANGUL_BASE) % 28 != 0


def _prev_hangul(text: str, pos: int) -> str:
    """pos 바로 앞의 한글 음절. 한글이 아니면 ''."""
    if pos <= 0:
        return ""
    ch = text[pos - 1]
    return ch if HANGUL_BASE <= ord(ch) <= HANGUL_LAST else ""


# 조사로 오인되는 '이/가' 앞 어간 — 조사 교정 대상에서 제외한다.
#
# _word_before() 는 조사 **앞의 어간** 을 돌려준다
# ('누군가' → '누군', '가까이' → '가까').
#   '누군' '어떻게' — 의존어미라 받침 유무와 무관하게 가/이 가 맞다
#   '가까'         — 이/가 가 명사 자체의 끝음절이라 조사가 아니다
# ('사이' 는 앞 음절이 어절의 첫 글자라 아래 check_josa 의 첫 음절 가드로 처리된다)
_BOUND_FORMS = {
    "누군", "누가", "어떻게", "어째", "무것", "무언",
    "각자", "각개", "어쨌든", "누군들",
    "가까",
}

# 명사 자체가 이/가 로 끝나는 형태 — 어절 끝에서 조사로 오인하지 않도록 제외한다.
# ('평가.', '시가 3,860원' 처럼 뒤에 음절이 없을 때 오탐이 났다)
_NOUN_TAIL_GA = {
    "평가", "결합", "추가", "부가", "시가", "오가", "통가",
}


def _word_before(text: str, pos: int, max_len: int = 6) -> str:
    """pos 바로 앞 어절 (조사 앞의 한글 덩어리)."""
    start = pos
    while start > 0 and (pos - start) < max_len:
        ch = text[start - 1]
        if not (HANGUL_BASE <= ord(ch) <= HANGUL_LAST):
            break
        start -= 1
    return text[start:pos]


def _is_bound_noun(text: str, pos: int) -> bool:
    """조사 앞 어절이 조사 교정 대상이 아닌 형태인지.

    '누군가' '사이' 처럼 앞 어절(또는 그 끝부분)이 _BOUND_FORMS 에 있으면 제외한다.
    """
    word = _word_before(text, pos)
    if not word:
        return False
    if word in _BOUND_FORMS:
        return True
    if word[-2:] in _NOUN_TAIL_GA and _is_noun_word(word):
        return True
    # '저평가' 처럼 조사 후보 음절이 명사의 끝인 경우 — 어절 전체로 확인한다.
    whole = _word_around(text, pos)
    if whole and _is_noun_word(whole):
        return True
    return any(word[-n:] in _BOUND_FORMS for n in (2, 3) if len(word) >= n)


def _word_around(text: str, pos: int, max_len: int = 8) -> str:
    """pos 를 포함한 한글 어절 전체 — 명사 자체인지 판단할 때 쓴다."""
    start = pos
    while start > 0 and (pos - start) < max_len:
        ch = text[start - 1]
        if not (HANGUL_BASE <= ord(ch) <= HANGUL_LAST):
            break
        start -= 1
    end = pos
    while end < len(text) and (end - pos) < max_len:
        ch = text[end]
        if not (HANGUL_BASE <= ord(ch) <= HANGUL_LAST):
            break
        end += 1
    return text[start:end]


_NOMINAL_SUFFIX = ("평가", "결합", "추가", "부가", "시가")


def _is_noun_word(word: str) -> bool:
    """어절이 명사처럼 쓰였는지 보수적으로 판단한다."""
    return len(word) >= 2 and (word.endswith(_NOMINAL_SUFFIX) or word in _NOUN_TAIL_GA)


def check_josa(text: str) -> list[dict]:
    """조사 오류를 찾아 수정안을 반환.

    을/를, 이/가 만 검사한다 (은/는 은 연결어미와 구분 불가라 제외).
    """
    out: list[dict] = []
    if not text:
        return out

    want = {c: (josa, need, pair) for josa, need, pair in _PAIRS for c in [_K2C[josa]]}

    for pos, ch in enumerate(text):
        rule = want.get(ch)
        if rule is None:
            continue
        josa, need_batchim, pair = rule

        prev = _prev_hangul(text, pos)
        if not prev:
            continue

        # 조사 앞 음절이 어절의 첫 음절이면 이/가 는 명사의 끝음절일 가능성이 높다.
        # ('사이' 를 '사가' 로 고치는 사고를 막는다)
        if pos < 2 or not (HANGUL_BASE <= ord(text[pos - 2]) <= HANGUL_LAST):
            continue

        # 조사 바로 뒤에 한글 음절이 붙으면 이/가 는 조사가 아니라 더 긴 단어의 일부다.
        #   그레이엄 / 분명한가요 / 사이에는 / 합격자입니다
        # 조사는 어절 끝에 붙는 첨성이므로 뒤에 다른 음절이 오지 않는다.
        # 게이트가 MAX_ERRORS=0 이므로 오탐 하나가 생산을 통째로 막는다 —
        # 확실하지 않으면 안 잡는 쪽이 안전하다.
        if pos + 1 < len(text):
            nxt = text[pos + 1]
            if HANGUL_BASE <= ord(nxt) <= HANGUL_LAST:
                continue

        # '누군가' '가까이' 처럼 조사 교정 대상이 아닌 형태는 제외한다.
        if _is_bound_noun(text, pos):
            continue

        # 의문 종결어미('~인가?', '~는가?') 의 '가' 는 조사가 아니다.
        # 앞 음절이 '인'/'는' 이면 종결어미로 본다 (물인가? 는 의문문이라 정상).
        if pos >= 1 and text[pos - 1] in ("인", "는", "은"):
            continue

        if has_batchim(prev) == need_batchim:
            continue  # 정상

        correct = pair
        out.append({
            "level": "error",
            "kind": "조사(신조법)",
            "message": (
                f"'{prev}{josa}' 은(는) 잘못된 조사입니다 — "
                f"받침{'있음' if has_batchim(prev) else '없음'}이므로 "
                f"'{correct}' 이(가) 맞습니다"
            ),
            "excerpt": prev + ch,
            "position": pos - 1,
            "suggestion": prev + _K2C[correct],
        })

    return out


def auto_fix_josa(text: str) -> tuple[str, list[dict]]:
    """조사 오류를 자동 교정한다 (뒤에서부터 교체해 인덱스가 밀리지 않게)."""
    issues = check_josa(text)
    if not issues:
        return text, []

    out = text
    for iss in sorted(issues, key=lambda x: x["position"], reverse=True):
        p = iss["position"]
        out = out[:p] + iss["suggestion"] + out[p + len(iss["excerpt"]):]

    return out, issues


def summary(issues: list[dict]) -> str:
    """검사 결과를 사람이 읽는 한 줄로.

    script_gate 리포트가 "조사 검사: ..." 한 줄을 출력할 때 쓴다.
    """
    if not issues:
        return "이상 없음"
    errors = sum(1 for i in issues if i.get("level") == "error")
    warns = len(issues) - errors
    parts: list[str] = []
    if errors:
        parts.append(f"오류 {errors}건")
    if warns:
        parts.append(f"경고 {warns}건")
    return " · ".join(parts)