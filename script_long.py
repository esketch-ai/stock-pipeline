"""7분 풀버전 대본 생성 — 시네마틱 구조.

60~90초 숏폼이 아니라, 약 7분(420초) 분량의 딥다이브 대본을 만든다.
LLM 을 한 번에 호출하면 3,000자 이상을 안정적으로 못 뽑으므로
섹션 단위로 나누어 순차 생성하고, 이어붙인 뒤 한 번 더 다듬는다.

섹션 구성 (목표 총 길이 ≈ 420초 / 약 2,100~2,600자):
    1. HOOK        0:00 - 0:25   시네마틱 오프닝
    2. SETUP       0:25 - 1:20   오늘 장면의 배경 (지수/업종 맥락)
    3. REVEAL      1:20 - 2:30   핵심 수치 공개
    4. DEEP DIVE   2:30 - 4:40   차근히 파고드는 해석 (최장 구간)
    5. RISK        4:40 - 5:50   리스크와 반대편 논리
    6. OUTRO       5:50 - 7:00   정리와 고지
"""

from __future__ import annotations

import asyncio
import json
import re

import config
import campaign
from logger import log

# 섹션 정의: (id, 한글 이름, 목표 글자수, 담당 LLM 지시)
SECTIONS = [
    ("hook", "오프닝", 180,
     "첫 30초. 화면이 검게 열리고 첫 문장이 떨어지는 순간 시청자를 붙잡아야 한다. "
     "확인된 변화와 시청자의 질문을 연결한다. 서론/인사/채널소개 금지. 바로 시작."),

    ("setup", "상황 설정", 480,
     "오늘 장면의 큰 그림. 지수 흐름, 시장 분위기, 이 종목이 속한 맥락. "
     "구체적 지수는 팩트 블록에 없으므로 '오늘 장면'이라는 일반 표현을 쓰고 "
     "'지수가+X%' 같은 없는 수치는 쓰지 마라. 이 종목이 왜 지금 주목받는 상황인지를 그린다."),

    ("reveal", "핵심 수치", 620,
     "이 종목의 숫자를 하나씩 공개. 시가총액, 현재가, 등락률, 52주 신고가 대비 위치. "
     "숫자를 나열하지 말고 발견하듯. 각 숫자가 왜 의미있는지 붙여라. "
     "종목별 편집 브리프의 핵심 질문에 답하는 수치만 골라 설명한다. 고정 전환 문구를 반복하지 않는다."),

    ("deep_dive", "심층 해석", 780,
     "가장 긴 구간. 이 주가의 움직임이 의미하는 것. "
     "가격·거래량에서 관찰되는 변화와 해석을 구분한다. "
     "확인된 수급·업종·밸류에이션 데이터가 있을 때만 해당 맥락을 연결한다. "
     "청자에게 질문을 던지는 리듬으로 계속 끌어당겨라."),

    ("risk", "리스크", 620,
     "반대편 논리. 이게 함정일 가능성. 변동성, 과도한 기대, 이미 빠진 사람들. "
     "단정하지 말고 시나리오로. '만약 ~한다면 이 된다' 같은 조건부 시나리오를 3가지 제시."),

    ("wisdom", "투자자의 지혜", 620,
     "유명 투자자의 철학으로 이 종목을 비춰본다. "
     "아래 '인용 가능한 투자자' 블록에서 이 장면과 가장 맞는 1~2인을 고르고, "
      "그 사람의 원칙이 실제 분석에 도움이 될 때만 이 종목의 숫자에 적용한다. "
      "인용이 억지스러우면 생략하고 이 종목에 특화된 확인 항목 세 개를 설명한다. "
      "항상 같은 투자자 이름이나 가정형 질문으로 시작하지 않는다."),

    ("outro", "정리와 고지", 320,
     "지금까지의 요약. 다만 단순 나열이 아니라 한 문장으로 묶는 결론. "
     "오프닝의 질문을 회수하고 설정된 자료 신청 행동 하나로 연결한다. 마지막에 투자 권유 고지 반드시 포함."),
]

TOTAL_TARGET_CHARS = 2400

# LLM 호출은 섹션(7회) + 다듬기(1회) = 8회.
# Gemini free-tier 는 분당 요청 수 제한이 있어 순차 호출 + 간격이 필수다.
DEFAULT_SECTION_GAP = 20.0


def build_section_prompt(section_id: str, title: str, target: int,
                         facts_block: str, reason: str,
                         stock_name: str, ticker: str,
                         prev_section: str = "",
                         investor_block: str = "", editorial_brief: str = "") -> str:

    continuity = ""
    if prev_section:
        continuity = f"""
[직전 섹션 — 이 흐름이 자연스럽게 이어지도록 중복을 피하고 자연스럽게 연결하세요]
{prev_section[:400]}
직전 구간의 첫 문장을 그대로 다시 쓰지 않는다. 같은 수치·같은 비유·같은 질문으로 구간을 다시 시작하지 않는다.

"""

    investors_ref = ""
    if investor_block:
        investors_ref = f"""
[인용 가능한 유명 투자자 — '투자자의 지혜' 섹션에서만 사용]
{investor_block}

"""

    return f"""당신은 한국 주식 유튜브 채널의 프로 라이터입니다.
설명식 브리딩이 아니라, 시청자가 끝까지 들을 만한 이야기를 씁니다.

지금부터 "{title}" 구간 대본만 작성하세요. {target}자 내외.
다른 구간은 다른 사람이 쓰므로, 이 구간만 독립적으로 완성도 있게 쓰면 됩니다.

[확인된 팩트 — 반드시 이 안의 수치만 사용]
{facts_block}

[기술적 지표]
- {reason}
[종목별 편집 브리프 — 모든 구간에 일관되게 적용]
{editorial_brief}
[시청 유지와 자료 신청 시나리오 — 이 구간의 행동 유도는 이 지시를 우선]
{campaign.scenario_instruction(section_id, ticker)}
{investors_ref}{continuity}
═══════════════════════════════════════════
## 절대 금지
═══════════════════════════════════════════
1. 팩트 블록에 없는 수치를 만들지 마라. (계산으로 유도 가능한 것은 가능)
2. "공시가 있습니다/없습니다", "테마입니다", "기관이 사들였습니다",
   "외국인이 유입", "실적이 개선/부진" → 확인 불가한 정보. 쓰지 마라.
   팩트 블록에 근거가 있는 경우에만 기간·출처와 함께 쓴다. 완곡한 표현으로 없는 근거를 대신하지 마라.
3. "여러분, ~보셨나요?" / "오늘은 ~다루겠습니다" 같은 클리셰 오프닝.
4. 같은 단어 3회 이상 반복 금지.
5. 군더더기 수식어("아주", "역시", "무려", "정말로") 남발 금지.
6. 같은 문장을 두 번 쓰지 않는다. 같은 질문을 구간마다 다시 던지지 않는다.
7. 12자 이상 연속 구절을 반복하지 않는다. 같은 숫자에서 출발해 같은 결론으로 돌아오지 않는다.

═══════════════════════════════════════════
## ★ 한국어 표기 규칙 (반드시 준수)
═══════════════════════════════════════════
A. **소수점 금지** — 퍼센트·배수·금액 모두 정수로 쓴다.
   ✅ "65%", "약 5배", "524억", "30%"     ❌ "65.22%", "4.58배", "524.52억"

B. **띄어쓰기를 정확히** — 조사는 붙여 쓰고, 의존 명사는 띄운다.
   ✅ "사흘 만에", "그 격차가죠", "이틀이나"
   띄어쓰기가 어색하면 그 어휘 자체를 더 쉬운 말로 바꾼다.
   어려운 말 금지: 간극, 역전 개연성, 가격 발견 효과 등
   쉬운 말: 격차→차이, 간극→벌어지는 거리, 역전 개연성→뒤집힐 가능성

C. **숫자 하나에 문장 하나** — 한 문장에 숫자가 두 개 이상 몰리면 끊어서 쓴다.
   긴 문장은 숨 쉴 틈을 남기고 끊어라.

D. **한자어 남용 금지** — "지표/추세/반등/변동성" 같은 전문 용어는 꼭 필요할 때만.
   나머지는 "숫자/기세/올라섬/들쭂날쭂함" 같은 평이한 말로 쓴다.
   전문가 말투가 과하면 시청자가 빠져나간다.

═══════════════════════════════════════════
## 이 채널의 톤 — 시네마틱
═══════════════════════════════════════════
- 긴장감. 영화 내레이션처럼 한 문장씩 잘라 말하고, 때로는 짧게 끊어 리듬을 만든다.
- 숫자 공개·관찰 장면·비교·반론 중 이 종목의 근거에 맞는 시작 방식을 선택한다.
- 비유는 이해를 돕는 경우만 사용하고, 다른 종목에도 그대로 붙는 산·파도·갈림길 비유를 반복하지 않는다.
- 청자에게 질문으로 떠넘겨 다음 문장을 끌어당겨라.
- 긴장 → 질문 → 충격적인 사실 → 성찰, 이 파동을 반복해라.
- 존댓말 구어체. "~입니다"보다 "~했죠", "~거든요".
- 목표 분량을 참고하되 근거 없는 반복으로 길이를 채우지 마라.

[출력]
이 구간의 대본 본문 텍스트만 출력하세요.
JSON, 마크다운, 제목, 부제, 설명 금지. 대본만 통으로.
"""


def build_final_prompt(full_text: str, stock_name: str, ticker: str, editorial_brief: str = "") -> str:
    """연결부 다듬기 — 중복 제거와 흐름 정리."""
    return f"""아래는 한국 주식 영상 대본의 전체 초안입니다. 이 구간을 다듬어 최종본으로 만들어 주세요.

[완성도 점검]
- 중복되는 표현이나 같은 내용 반복 삭제
- 몰리고 있는 설명 분산
- 목차처럼 되는 어색한 문장 자연스럽게
- 억지로 맞추는 숫자 삭제
- 오프닝 질문과 본문에서의 답을 유지한다. 신청 행동은 중간 한 문장과 마지막 한 번으로 제한한다.
- 초안에 있는 제공 자료명과 신청 경로를 바꾸거나 새 혜택을 추가하지 않는다.

═══════════════════════════════════════════
절대 금지 (이 초안의 문제점을 고쳐야 합니다)
═══════════════════════════════════════════
1. 팩트 블록에 없는 수치를 만들지 마라. (계산으로 유도 가능한 것은 가능)
2. "공시가 있습니다/없습니다", "테마입니다", "기관이 사들였습니다",
   "외국인이 유입", "실적이 개선/부진" → 확인 불가한 정보. 쓰지 마라.
3. 같은 단어 3회 이상 반복 금지.
4. 군더더기 수식어("아주", "역시", "무려", "정말로") 남발 금지.
5. 투자 권유 금지 (매수/매도/보유 권유 없음).
6. **초안에 있는 숫자는 어떤 경우에도 바꾸지 않는다.** 반올림·단위 변환·다른 값 대체 금지.
   새 숫자를 덧붙이지 않는다. 초안이 없던 수치는 쓰지 않는다.
   (숫자를 바꾸면 실제 시세와 어긋나 생산이 차단된다)

[출력]
완성된 대본 본문 텍스트만 출력하세요. JSON, 마크다운, 제목 금지. 본문만.

[종목]
{stock_name} ({ticker})
[유지할 종목별 편집 브리프]
{editorial_brief}
[다듬을 초안]
{full_text}
"""


def _clean(text: str) -> str:
    """LLM 출력 정리 — 마크다운/제목/코드펜스 제거 + 한국어/수치 교정."""
    import text_polish

    t = (text or "").strip()
    # 코드펜스
    t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
    t = re.sub(r"\n?```$", "", t)
    # JSON 이 섞여 나오면 문자열만 추출
    if t.startswith("{") or t.startswith("["):
        try:
            data = json.loads(t)
            if isinstance(data, dict):
                parts = [str(data.get(k, "")) for k in ("hook", "body", "closing", "text", "script")]
                t = "\n".join(p for p in parts if p)
                if isinstance(data.get("body"), list):
                    t = "\n".join(data.get("body", []) + [t])
        except json.JSONDecodeError:
            # 부분 JSON 복구
            strings = re.findall(r'"(?:hook|body|closing|text|script)"\s*:\s*(?:"([^"]*)"|\[([^\]]*)\])', t)
            if strings:
                out = []
                for a, b in strings:
                    if a:
                        out.append(a)
                    elif b:
                        out.extend(re.findall(r'"([^"]*)"', b))
                t = "\n".join(out)
    # 제목/섹션 헤더 제거
    t = re.sub(r"^#{1,6}\s*.*$", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*\[.*?\]\s*$", "", t, flags=re.MULTILINE)
    # HTML 태그
    t = re.sub(r"<[^>]+>", "", t)
    # 한국어 띄어쓰기 교정 + 소수점 없는 수치 표기
    t = text_polish.polish_for_speech(t)
    return t.strip()


def _split_sentences(text: str) -> list[str]:
    """문장 단위 분리 — 자막 싱크용.

    구두점이 없는 원문도 흔하므로 줄바꿈을 먼저 경계로 삼는다.
    """
    chunks: list[str] = []
    for line in (text or "").split("\n"):
        chunks.extend(p.strip() for p in re.split(r"(?<=[.!?])\s+", line.strip()))
    return [c for c in chunks if c]


# ── 반복 방지 ───────────────────────────────────────────
SECTION_IDS = [s[0] for s in SECTIONS]

# 상장·신고가 같은 숫자로 시작하는 문장은 서로 다른 근거여도 겹쳐 보인다.
_OPENER_NOISE = re.compile(r"^(이|그|저)?(종목|주식|종)|^(이|그|저)?(는|가|은|을|의)\s|^[가-힣]{0,4}[가-힣]?")


def _fingerprint(sentence: str) -> str:
    """숫자와 띄어쓰기를 지운 비교용 형태."""
    s = re.sub(r"\d[\d,.]*", "", sentence)
    s = re.sub(r"[^가-힣A-Za-z]", "", s)
    return s


# 짧은 문장도 반복되면 지루하다. 7자 미만은 형식적 반복이라 본다.
MIN_SENTENCE_CHARS = 7
# 숫자만 바뀌고 되풀이되는 멘트를 잡기 위한 구절 단위 길이.
PHRASE_CHARS = 12
PHRASE_MAX_REPEAT = 3


def repeated_sentences(sections: list[dict]) -> list[dict]:
    """같은 멘트가 되풀이된 구간을 찾는다.

    1) 숫자를 지운 문장이 두 번 이상 나오면 잡는다.
    2) 12자 구절이 세 번 이상 나오면 '숫자만 다른 반복' 으로 잡는다.
    """
    sentence_rows: list[tuple[str, str]] = []  # (구간 id, 문장)
    for section in sections:
        for sentence in _split_sentences(section.get("text", "")):
            if len(_fingerprint(sentence)) >= MIN_SENTENCE_CHARS:
                sentence_rows.append((section.get("id"), sentence.strip()))

    counts: dict[str, int] = {}
    for _, sentence in sentence_rows:
        key = _fingerprint(sentence)
        counts[key] = counts.get(key, 0) + 1

    phrases: dict[str, int] = {}
    for _, sentence in sentence_rows:
        key = _fingerprint(sentence)
        for i in range(max(0, len(key) - PHRASE_CHARS + 1)):
            gram = key[i:i + PHRASE_CHARS]
            phrases[gram] = phrases.get(gram, 0) + 1

    hits: dict[str, dict] = {}
    running: dict[str, int] = {}
    for section_id, sentence in sentence_rows:
        key = _fingerprint(sentence)
        running[key] = running.get(key, 0) + 1
        # 뒤에 나온 쪽이 '반복' 이다 — 첫 등장 문장은 그대로 두고 반복만 고친다.
        duplicate = running[key] >= 2
        # '숫자만 다른 같은 문장' 은 문장 단위로는 1회로 센다.
        # 그래서 구절 반복 횟수를 문장 횟수까지 끌어올려야 반복으로 잡힌다.
        repeat_grams = [
            phrases[key[i:i + PHRASE_CHARS]] for i in range(max(0, len(key) - PHRASE_CHARS + 1))
        ]
        phrase_repeat = max(repeat_grams, default=0) >= PHRASE_MAX_REPEAT
        if not (duplicate or phrase_repeat):
            continue
        count = max(running[key], max(repeat_grams, default=1) if phrase_repeat else 1)
        current = hits.get(key)
        if current is None or count > current["count"]:
            hits[key] = {
                "id": section_id,
                "text": sentence,
                "count": count,
                "reason": "문장 중복" if duplicate else "구절 반복",
            }
    return list(hits.values())


async def regenerate_section(call_llm, *, section_id: str, title: str, base_target: int,
                             facts_block: str, reason: str, stock_name: str, ticker: str,
                             bad: list[dict], editorial_brief: str,
                             avoid: list[str] | None = None) -> str:
    """반복이 생긴 구간만 다시 쓴다. 전체를 다시 만들지 않는다."""
    bad_text = "\n".join(f"- {b['text']}" for b in bad)
    avoid_text = "\n".join(f"- {a}" for a in (avoid or [])[:24])
    prompt = f"""아래 한국 주식 대본의 "{title}" 구간이 같은 멘트를 여러 번 반복해 다시 작성한다.
다른 구간은 이미 확정되어 있으므로 이 구간만 독립적으로 완성도 있게 쓴다.

[확인된 팩트 — 이 안의 수치만 사용]
{facts_block}

[종목 브리프]
{editorial_brief[:1200]}

[반복해서 버린 문장 — 절대 다시 쓰지 않는다]
{bad_text}
[이미 다른 구간에서 쓴 시작 표현 — 다른 각도로 여는 법을 찾는다]
{avoid_text or "- (없음)"}

[규칙]
- 위 문장과 같은 구조·같은 시작 말·같은 나열 순서로 시작하지 않는다.
- 같은 질문으로 열지 않는다. '~할까요?' '~라는 건데요' 식 도입을 반복하지 않는다.
- 같은 숫자로 두 번 출발하지 않는다. 이미 나온 수치는 새 논거로 다시 쓰지 않는다.
- 한 구간 안에서 같은 주어를 두 번 연속 쓰지 않는다.
- 12자 이상 연속 구절을 반복하지 않는다.
- 목표 {base_target}자 내외. 금지 표현과 표기 규칙은 기존 지침을 그대로 따른다.

[출력]
이 구간의 대본 본문 텍스트만. JSON·마크다운·제목 금지.
"""
    return _clean(await call_llm(prompt))


def _hint(facts_block: str, label: str) -> str:
    """팩트 블록에서 특정 라벨의 값을 뽑는다."""
    for line in (facts_block or "").splitlines():
        if f"- {label}" in line:
            return line.split(":", 1)[1].strip()
    return ""


def estimate_duration(text: str, chars_per_sec: float = 4.3) -> float:
    """한국어 낭독 속도 기준 예상 길이(초). 자막 구간 계산에 사용."""
    return len(text) / chars_per_sec


def extract_investors(text: str) -> list[dict]:
    """대본에 실제로 등장한 투자자를 찾아낸다 (대시보드 표기용)."""
    import investors as inv_mod

    found = []
    for inv in inv_mod.INVESTORS:
        if inv.name_ko in text or inv.name_en in text or inv.nickname in text:
            found.append({
                "id": inv.id,
                "name": inv.name_ko,
                "name_en": inv.name_en,
                "nickname": inv.nickname,
                "strategy": inv.strategy,
            })
    return found


def build_investor_block(reason: str, facts_block: str = "") -> str:
    """상황에 맞는 투자자 카탈로그를 LLM 에 제공한다 (전체 노출)."""
    import investors as inv_mod

    lines = []
    for inv in inv_mod.INVESTORS:
        lines.append(
            f"- {inv.name_ko} ({inv.nickname}) — 전략: {inv.strategy}\n"
            f"    원칙: {inv.principle}\n"
            f"    이 장면에서 유효한 이유: {', '.join(inv.best_for) or '일반적'} "
            f"(매칭 키워드: {', '.join(inv.keywords)})"
        )
    header = (
        "아래 투자자 중 이 장면에 가장 맞는 1~2인을 고르세요. "
        "목록에 있는 사람만 인용하고, 없는 이름을 지어내지 마세요.\n"
    )
    return header + "\n".join(lines)


async def generate_long_script(facts_block: str, reason: str,
                               stock_name: str, ticker: str,
                               call_llm, target_chars: int = TOTAL_TARGET_CHARS,
                               section_gap: float = DEFAULT_SECTION_GAP,
                               editorial_brief: str = "", editorial_plan: dict | None = None) -> dict:
    """섹션별로 생성 → 연결 → 다듬기.

    call_llm: async (prompt: str) -> str  주입형 (테스트/대체 모델 용이)
    section_gap: API 레이트리밋 회피용 섹션 간 대기 초
    """
    sections_out: list[dict] = []
    prev = ""

    # 목표 총 글자수에 맞춰 섹션별 배분 (비례 배분)
    weight_total = sum(s[2] for s in SECTIONS)
    scale = target_chars / weight_total

    for idx, (sid, title, base_target, instruction) in enumerate(SECTIONS):
        target = max(120, int(base_target * scale))
        # 'wisdom' 섹션에서만 투자자 카탈로그를 주입한다
        inv_block = (
            build_investor_block(reason, facts_block) if sid == "wisdom" else ""
        )
        if editorial_plan:
            # 전체 투자자 목록에서 매번 같은 인물을 선택하는 경로를 사용하지 않는다.
            inv_block = ''
        prompt = build_section_prompt(
            sid, title, target, facts_block, reason, stock_name, ticker, prev,
            investor_block=inv_block, editorial_brief=editorial_brief,
        )
        section_instruction = editorial_plan['sections'][sid] if editorial_plan else instruction
        prompt += f"\n\n[구간 지시 — 편집 계획의 근거와 질문을 구체적으로 전개]\n{section_instruction}\n"

        # Gemini free-tier 레이트리밋 방지: 섹션 사이에 간격을 둔다.
        if idx > 0:
            await asyncio.sleep(section_gap)

        try:
            raw = await call_llm(prompt)
        except Exception as exc:
            log.error("섹션 생성 실패 [%s/%s]: %s", sid, title, exc)
            # 'wisdom' 섹션은 LLM 이 죽어도 투자자 DB 로 폴백 생성한다.
            if sid == "wisdom" and not editorial_plan:
                import investors as inv_mod

                text = inv_mod.build_fallback_section(
                    stock_name, reason,
                    from_high=_hint(facts_block, "신고가 대비"),
                    range_pos=_hint(facts_block, "52주 레인지"),
                )
                if text:
                    log.warning("wisdom 섹션 → 투자자 DB 폴백 사용 (%d자)", len(text))
                    sentences = _split_sentences(text)
                    sections_out.append({
                        "id": sid, "title": title, "text": text,
                        "sentences": sentences, "chars": len(text),
                        "target": target, "duration": estimate_duration(text),
                        "fallback": True,
                    })
                    prev = text[-400:]
                    continue
            sections_out.append({"id": sid, "title": title, "text": "", "error": str(exc)})
            continue

        text = _clean(raw)
        sentences = _split_sentences(text)
        sections_out.append({
            "id": sid,
            "title": title,
            "text": text,
            "sentences": sentences,
            "chars": len(text),
            "target": target,
            "duration": estimate_duration(text),
        })
        prev = text[-400:] if text else ""
        log.info("섹션 [%s/%s] %d자 (목표 %d, %.0f초)", sid, title, len(text), target, estimate_duration(text))

    full = "\n\n".join(s["text"] for s in sections_out if s["text"])

    # 최종 다듬기 — 추가 LLM 호출 1회.
    # 섹션이 여러 개 실패했다면 이미 LLM 한도에 걸린 상태이므로 아낀다.
    failed = [s for s in sections_out if not s["text"]]
    if full and not failed:
        try:
            await asyncio.sleep(section_gap)
            raw = await call_llm(build_final_prompt(full, stock_name, ticker, editorial_brief))
            polished = _clean(raw)
            if len(polished) >= len(full) * 0.75:
                full = polished
                log.info("최종 다듬기 적용 (%d자)", len(full))
        except Exception as exc:
            log.warning("최종 다듬기 실패 — 초안 사용: %s", exc)
    elif failed:
        log.warning("섹션 %d개 실패 → 다듬기 생략 (LLM 한도 보호)", len(failed))

    total_chars = len(full)
    return {
        "text": full,
        "sections": sections_out,
        "total_chars": total_chars,
        "estimated_duration": estimate_duration(full),
        "sentences": _split_sentences(full),
        "investors": extract_investors(full),
    }


async def repair_repetitions(call_llm, *, result: dict, facts_block: str, reason: str,
                             stock_name: str, ticker: str, editorial_brief: str,
                             weights: dict[str, int], max_repairs: int = 2) -> dict:
    """반복이 생긴 구간만 다시 쓴다. 결과 dict 에 repetitions 를 붙여 돌려준다."""
    repaired = 0
    for attempt in range(max_repairs):
        hits = repeated_sentences(result["sections"])
        if not hits:
            break
        by_section: dict[str, list[dict]] = {}
        for hit in hits:
            by_section.setdefault(hit["id"], []).append(hit)
        log.warning("반복 문장 %d건 감지 — %s 구간 재생성",
                    len(hits), ", ".join(sorted(by_section)))
        for section in result["sections"]:
            bad = by_section.get(section["id"])
            if not bad:
                continue
            # 다른 구간이 이미 쓴 시작 표현은 다시 쓰지 않게 넘겨준다.
            avoid = [
                sentence for other in result["sections"] if other["id"] != section["id"]
                for sentence in _split_sentences(other.get("text", ""))[:6]
            ]
            try:
                text = await regenerate_section(
                    call_llm,
                    section_id=section["id"], title=section["title"],
                    base_target=weights.get(section["id"], 400),
                    facts_block=facts_block, reason=reason, stock_name=stock_name,
                    ticker=ticker, bad=bad, editorial_brief=editorial_brief, avoid=avoid,
                )
            except Exception as exc:
                log.warning("%s 구간 재생성 실패: %s", section["id"], exc)
                continue
            if not text:
                continue
            section["text"] = text
            section["sentences"] = _split_sentences(text)
            section["chars"] = len(text)
            section["regenerated_for_repetition"] = True
            repaired += 1
        result["text"] = "\n\n".join(s["text"] for s in result["sections"] if s["text"])
        result["total_chars"] = len(result["text"])
        result["estimated_duration"] = estimate_duration(result["text"])
        result["sentences"] = _split_sentences(result["text"])

    result["repetitions"] = repeated_sentences(result["sections"])
    result["regenerated_sections"] = repaired
    return result
