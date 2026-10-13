"""한국어 문법·맞춤법·표기 검출기.

규칙으로 잡을 수 있는 것만 잡는다. 의미层面的 오류(어색한 표현, 논리
부조)는 llm_proofread 가 담당한다.

검사 항목:
  1. 띄어쓰기 — 단위/고정어/조사
  2. 표기 — 숫자+단위, 숫자+퍼센트
  3. 맞춤법 — 오탈자, 자주 틀리는 어미
  4. 일관성 — 문체 혼용(합니다체/해요체), 숫자 표기 혼용
  5. 어휘 — 어려운 한자어, 군더더기 수식어
  6. 구조 — 반복, 종결어 누락, 문장 길이
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── 1. 표기: 숫자와 단위는 붙여 쓴다 ────────────────────
UNIT_RE = re.compile(
    r"(?<=\d)\s+(원|억|조|만|천|배|대|개|명|일|년|월|주|%|퍼센트|포인트|배수|분|초|주가|주)\b"
)

# 붙여 써야 하는 고정어 (흔히 띄어쓰는 오류)
# 띄어쓰기로 잘못 쓰인 경우를 잡기 위해 띄어쓰기 형태만 검사한다.
ATTACH_PATTERNS = [
    (r"나누어\s", "나누어 "),
    (r"나눠\s", "나눠 "),
    (r"\s넓이(?![가-힣])", "넓이"),
    (r"\s높이(?![가-힣])", "높이"),
    (r"더\s*나눠", "더 나누어"),
    (r"\s각각\s", "각각 "),
    (r"제\s*각각", "제각각"),
    (r"뒤\s*늦게", "뒤늦게"),
    (r"\s대비\s+(?=[\d\-+])", " 대비 "),
    (r"기준\s*으로(?![가-힣])", " 기준으로"),
]

# 띄어 써야 하지만 붙여 쓰는 오류
DETACH = [
    (r"어떻게\s*했습니다", "어떻게 했습니다"),
    (r"왜\s*냐면", "왜냐면"),
    (r"그럼\s*있죠", "그럼 있죠"),
]

# ── 2. 오탈자 ────────────────────────────────────────────
TYPOS = [
    # 공백이 있을 때만 오탈자다. \s* 로 두면 올바른 "없다" 를 스스로 지적한다.
    (r"\b없\s+다\b", "없다"),
    (r"되있", "되어 있"),
    (r"하겠습니", "하겠습니다"),
    (r"되서", "돼서"),
    (r"되만", "됐지만"),
    (r"안\s*된\s*것\s*같", "안 된 것 같"),
    (r"많이\s*들어\s*올\s*수", "많이 들어올 수"),
    (r"어떻\w*\s*때문", "어떤 때까지"),
]

# ── 3. 어려운 어휘 → 쉬운 말 ────────────────────────────
HARD = {
    "간극": "차이",
    "역전 개연성": "뒤집힐 가능성",
    "가격 발견 효과": "주가가 반등하는 현상",
    "유동성 제약": "거래가 제한되는 상황",
    "미시총주": "작은 회사",
    "테마성": "테마로 불리는",
    "펀더멘털": "기업의 본질",
    "레벨": "단계",
    "체감": "느껴지는",
    "업사": "어려움",
    "리스크 헨지": "위험 방어",
}

# ── 4. 군더더기 수식어 ───────────────────────────────────
FILLER = [
    "아주", "역시", "다시 한번", "정말로", "진짜로", "굉장히",
    "엄청난", "엄청히", "꽤", "생각보다", "상당히", "무조건",
]


@dataclass
class Issue:
    level: str      # error | warn
    kind: str       # spacing | 표기 | 맞춤법 | 어휘 | 문체 | 구조
    message: str
    excerpt: str = ""
    position: int = 0
    suggestion: str = ""


@dataclass
class LintResult:
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warn"]

    @property
    def score(self) -> int:
        return max(0, 100 - len(self.errors) * 12 - len(self.warnings) * 4)

    def summary(self) -> str:
        return (
            f"오류 {len(self.errors)} · 경고 {len(self.warnings)} · 점수 {self.score}"
        )


def _mk(level: str, kind: str, message: str, m: re.Match, suggestion: str = "") -> Issue:
    text = m.group(0)
    return Issue(
        level=level, kind=kind, message=message,
        excerpt=text, position=m.start(), suggestion=suggestion,
    )


def check(text: str) -> LintResult:
    """대본 텍스트의 한국어 표기/맞춤법을 검사한다."""
    res = LintResult()
    if not text:
        return res

    # 1. 숫자 + 단위 붙여쓰기
    for m in UNIT_RE.finditer(text):
        res.issues.append(Issue(
            level="warn", kind="표기",
            message=f'"{m.group().strip()}" — 숫자와 단위는 붙여 씁니다',
            excerpt=m.group(), position=m.start(),
            suggestion=m.group().replace(" ", ""),
        ))

    # 2. 오탈자
    for pat, fixed in TYPOS:
        m = re.search(pat, text)
        if m:
            res.issues.append(_mk("error", "맞춤법",
                                  f'"{m.group()}" 는 올바른 표기가 아닙니다', m, fixed))

    # 3. 어려운 어휘
    for hard, easy in HARD.items():
        m = re.search(re.escape(hard), text)
        if m:
            res.issues.append(_mk(
                "warn", "어휘",
                f'어려운 어휘 "{hard}" — 시청자가 바로 이해하지 못할 수 있습니다',
                m, easy,
            ))

    # 4. 고정어 (띄어쓰기 형태만 검사)
    for pat, fixed in ATTACH_PATTERNS:
        m = re.search(pat, text)
        if m:
            res.issues.append(_mk("warn", "띄어쓰기",
                                  f'"{m.group().strip()}" 표기 확인 필요', m, fixed))

    for pat, fixed in DETACH:
        m = re.search(pat, text)
        if m:
            res.issues.append(_mk("warn", "띄어쓰기",
                                  f'"{m.group()}" 는 띄어 씁니다', m, fixed))

    # 5. 문체 혼용 (합니다체 / 해요체)
    _check_register(text, res)

    # 6. 군더더기 수식어
    hits = [(w, text.count(w)) for w in FILLER if w in text]
    for w, c in hits:
        if c >= 2:
            m = re.search(re.escape(w), text)
            res.issues.append(_mk(
                "warn", "어휘",
                f'군더더기 수식어 "{w}" 가 {c}회 반복됩니다', m, "삭제 권장"
            ))

    # 7. 같은 단어 과다 반복
    _check_repetition(text, res)

    # 8. 종결어 없는 문장
    _check_sentence_endings(text, res)

    return res


def _check_register(text: str, res: LintResult) -> None:
    """합니다체와 해요체가 섞여 있으면 일관성 문제."""
    has_ayo = len(re.findall(r"(습니다|ㅂ니다|입니다|됩니다)[.]?\s", text))
    has_haeyo = len(re.findall(r"(해요|해요\.|이에요|예요|네요|죠)[.]?\s", text))
    if has_ayo and has_haeyo:
        total = has_ayo + has_haeyo
        minor = min(has_ayo, has_haeyo)
        if total and minor / total > 0.3:
            m = re.search(r"(해요|예요|네요|죠)[.]?\s", text)
            res.issues.append(Issue(
                level="warn", kind="문체",
                message=f"문체가 섞여 있습니다 (해요체 {has_haeyo}회 / 합쇼체 {has_ayo}회)",
                excerpt=m.group() if m else "",
                position=m.start() if m else 0,
                suggestion="한 문체로 통일 (추천: 해요체)",
            ))


def _check_repetition(text: str, res: LintResult) -> None:
    """같은 어간이 지나치게 반복되는지."""
    words = re.findall(r"[가-힣]{2,}", text)
    counts: dict[str, int] = {}
    for w in words:
        stem = w
        for suf in ("입니다", "했죠", "거든요", "합니다", "합니다", "하는", "되는",
                    "에서", "으로", "라는", "이라고", "은", "는", "이", "가", "을", "를", "의", "에", "도"):
            if stem.endswith(suf) and len(stem) > len(suf) + 1:
                stem = stem[: -len(suf)]
                break
        counts[stem] = counts.get(stem, 0) + 1

    for stem, c in sorted(counts.items(), key=lambda x: -x[1]):
        if c >= 6 and len(stem) >= 2:
            m = re.search(re.escape(stem), text)
            res.issues.append(Issue(
                level="warn", kind="구조",
                message=f'"{stem}" 류 어간이 {c}회 반복됩니다',
                excerpt=stem, position=m.start() if m else 0,
                suggestion="다른 표현으로 바꾸기",
            ))
            break  # 가장 심한 것만


def _check_sentence_endings(text: str, res: LintResult) -> None:
    """마침표가 없는 긴 문장."""
    chunks = re.split(r"(?<=[.!?])\s+", text.strip())
    for ch in chunks:
        ch = ch.strip()
        if len(ch) > 120 and not ch.endswith((".", "?", "!")):
            idx = text.find(ch)
            res.issues.append(Issue(
                level="warn", kind="구조",
                message=f"종결어 없는 긴 문장 ({len(ch)}자) — 끊어 읽히지 않습니다",
                excerpt=ch[:40] + "…",
                position=idx if idx > 0 else 0,
                suggestion="문장 중간에 마침표 추가",
            ))


def auto_fix(text: str) -> tuple[str, list[Issue]]:
    """확실히 안전한 것만 자동 교정한다. 나머지는 제안만."""
    issues: list[Issue] = []
    out = text

    # 숫자+단위 붙여쓰기
    def _join(m):
        return m.group(0).replace(" ", "")
    out = UNIT_RE.sub(_join, out)

    # 오탈자
    for pat, fixed in TYPOS:
        if re.search(pat, out):
            out = re.sub(pat, fixed, out)
            issues.append(Issue("error", "맞춤법", f"'{pat}' → '{fixed}'", fixed, 0, fixed))

    return out, issues