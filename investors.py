"""유명 투자자 인사이트 DB + 인용 생성기.

출처: https://the-modellers.com/blog/top-10-famous-investors
(세계에서 가장 유명한 투자자 10명과 그들의 전략)

각 투자자의 전략/분석 프레임/설명 톤을 정리해 두고,
현재 종목의 팩트에 맞는 투자자를 골라 대본에 인용 구간을 삽입한다.

추가 방법: INVESTORS 리스트에 항목을 하나 더 넣으면 자동으로 반영된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Investor:
    id: str
    name_ko: str
    name_en: str
    nickname: str            # 한국어 별칭/브랜드
    strategy: str            # 전략 한 줄
    keywords: list[str]      # 매칭 키워드
    principle: str           # 핵심 원칙
    case: str                # 대표 사례
    tone: str                # 설명 톤 (대본 문장 스타일 가이드)
    # 어떤 상황에서 인용하면 자연스러운가
    best_for: list[str] = field(default_factory=list)


INVESTORS: list[Investor] = [
    Investor(
        id="buffett",
        name_ko="워렌 버핏",
        name_en="Warren Buffett",
        nickname="오마하의 현인",
        strategy="가치 투자(Value Investing)",
        keywords=["저평가", "밸류에이션", "장기", "우수기업", "내재가치", "고점", "고평가", "현금흐름", "안정"],
        principle="훌륭한 회사를 적당한 가격에 사서 오래 붙들어라. 자기자본이익률(ROE)과 부채비율로 기업의 질을 재라.",
        case="1980년대 후반 코카콜라에 약 13억 달러를 투자해 장기 보유",
        tone="차분하고 단정적인 존댓말. 숫자로 근거를 말한 뒤 한 줄로 원칙을 닫는다.",
        best_for=["저평가", "고점", "고평가", "밸류에이션", "장기투자"],
    ),
    Investor(
        id="lynch",
        name_ko="피터 린치",
        name_en="Peter Lynch",
        nickname="성장 투자자",
        strategy="알고 있는 것에 투자하라(Invest in What You Know)",
        keywords=["성장", "업종", "소재", "비즈니스", "실제", "직접", "제품", "관찰"],
        principle="내가 이해하는 산업에서만 찾으라. 그리고 결정 전에 숙제를 하라. 소비자가 매일 만지는 곳이 최고의 아이디어다.",
        case="던킨도너츠처럼 소비자가 매일 사 오는 제품을 관찰해 기회를 발견",
        tone="구어체에 가깝고 친근하다. '무엇을 아느냐'가 관건이라는 관점을 생활감 있게 말한다.",
        best_for=["성장", "업종", "소재", "관찰", "비즈니스모델"],
    ),
    Investor(
        id="graham",
        name_ko="벤저민 그레이엄",
        name_en="Benjamin Graham",
        nickname="가치투자의 아버지",
        strategy="안전마진(Margin of Safety)",
        keywords=["저평가", "하락", "바닥", "폭락", "리스크", "손실", "저가", "낙폭"],
        principle="내재 가치보다 훨씬 싸게 사라. 판단이 틀려도 괜찮도록 여유분을 남겨라. 손실을 줄이는 것이 이익을 쫓는 것만큼 중요하다.",
        case="부실해 보이는 저평가 기업을 사서 시장이 본래 가치로 돌아올 때까지 보유",
        tone="격려가 아니라 경고의 톤. 방어적. 숫자와 원칙으로 방어선을 논리적으로 제시.",
        best_for=["저평가", "폭락", "바닥", "리스크", "낙폭", "손실"],
    ),
    Investor(
        id="dalio",
        name_ko="레이 달리오",
        name_en="Ray Dalio",
        nickname="헤지펀드 개척자",
        strategy="위험 균형(Risk Parity)과 분산 투자",
        keywords=["분산", "위험", "변동성", "경기", "금리", "인플레이션", "포트폴리오", "사이클"],
        principle="위험을 균형 있게 나눠라. 분산은 종류를 늘리는 게 아니라 위험의 균형을 맞추는 것이다.",
        case="2008년 금융위기 전 경제 주기를 읽고 미리 대응",
        tone="구조를 그리는 톤. 한 장면이 하나의 사이클이라고 생각한다.",
        best_for=["분산", "변동성", "경기", "사이클", "포트폴리오"],
    ),
    Investor(
        id="soros",
        name_ko="조지 소로스",
        name_en="George Soros",
        nickname="투기의 대가",
        strategy="거시 투자(Macro Investing)",
        keywords=["환율", "통화", "매크로", "지진", "반전", "과대평가", "역전", "반대"],
        principle="시장의 잘못된 가격을 찾아라. 확신이 서면 크게 움직여도 된다.",
        case="1992년 파운드화를 공매도해 하루 만에 10억 달러 수익",
        tone="확신과 긴장감. 리스크를 감수하는 논리를 논리적으로 증명한다.",
        best_for=["환율", "매크로", "과대평가", "역전", "반대_CASE"],
    ),
    Investor(
        id="bogle",
        name_ko="존 보글",
        name_en="John Bogle",
        nickname="인덱스 펀드의 선구자",
        strategy="수동적 투자(Passive Investing)",
        keywords=["비용", "수수료", "장기", "지수", "운용", "꾸준히"],
        principle="시장을 이기려 하지 말고 시장 자체를 소유하라. 비용을 낮추고 오래 두는 것이 부를 쌓는 유일한 방법이다.",
        case="1976년 뱅가드 500 인덱스 펀드 출시",
        tone="담담하고 정직한 톤. 비용과 기간이라는 두 가지 숫자로 충분하다.",
        best_for=["비용", "수수료", "장기", "꾸준히"],
    ),
    Investor(
        id="icahn",
        name_ko="칼 아이칸",
        name_en="Carl Icahn",
        nickname="행동주의 투자자",
        strategy="기업 행동주의(Corporate Activism)",
        keywords=["지분", "경영진", "구조", "분할", "주주", "투쟁", "압박", "계속가"],
        principle="기다리는 시간이 아니라 우호적인 변화를 밀어붙여라. 소수의 지분이 회사를 바꿀 수 있다.",
        case="애플·넷플릭스·이베이에서 지분 매수와 사업 분할을 주장",
        tone="직설적이고 밀도 높은 톤. 한 문장이 짧고 강하다.",
        best_for=["지분", "경영진", "분할", "주주", "투쟁"],
    ),
    Investor(
        id="swensen",
        name_ko="데이비드 스웬슨",
        name_en="David Swensen",
        nickname="기금 관리자",
        strategy="대체 투자(Alternative Investments)",
        keywords=["분산", "자산배분", "사모", "부동산", "대체", "균형", "오일러", "전체"],
        principle="주식과 채권만으로는 부족하다. 다양한 자산군으로 위험을 관리하는 장기 모델이 필요하다.",
        case="예일대학교 endowment fund를 수십억 달러의 수익으로 운영",
        tone="체계적. 여러 축을 동시에 보여주는 구성을 좋아한다.",
        best_for=["분산", "자산배분", "대체", "오일러"],
    ),
    Investor(
        id="simons",
        name_ko="짐 사이먼스",
        name_en="Jim Simons",
        nickname="퀀트의 왕",
        strategy="알고리즘 트레이딩",
        keywords=["데이터", "패턴", "알고리즘", "숫자", "정량", "모델", "통계", "작은우위"],
        principle="데이터 안의 미세한 패턴이 눈에 보이지 않는 우위를 만든다.",
        case="르네상스 테크놀로지 — 메달리온 펀드의 압도적 수익",
        tone="간결하고 논리적인 톤. 감정보다 데이터로 말한다.",
        best_for=["데이터", "패턴", "정량", "통계", "작은우위"],
    ),
    Investor(
        id="munger",
        name_ko="찰리 멍거",
        name_en="Charlie Munger",
        nickname="합리성의 현자",
        strategy="정신 모델(Mental Models)과 합리적 투자",
        keywords=["비즈니스", "이해", "규율", "합리", "다학제", "실수", "숙제", "철학"],
        principle="비즈니스를 깊이 이해한 후에 투자한다. 투기적 행동을 피하고, 결정의 이면을 늘 점검하라.",
        case="버핏의 오른팔 — 다학문적 사고를 투자에 적용",
        tone="명제형. 짧고 단정적인 문장. \"~하라\"로 끝나는 구어체.",
        best_for=["비즈니스", "이해", "규율", "합리", "철학"],
    ),
]

_BY_ID = {inv.id: inv for inv in INVESTORS}


def get(investor_id: str) -> Investor | None:
    return _BY_ID.get(investor_id)


def all_ids() -> list[str]:
    return [inv.id for inv in INVESTORS]


def format_quote_block(investor: Investor) -> str:
    """프롬프트에 주입할 투자자 인용 블록."""
    return (
        f"- {investor.name_ko}({investor.name_en}, {investor.nickname})\n"
        f"  · 전략: {investor.strategy}\n"
        f"  · 원칙: {investor.principle}\n"
        f"  · 사례: {investor.case}\n"
        f"  · 톤: {investor.tone}"
    )


def catalog_block() -> str:
    """전체 카탈로그 — LLM 이 상황에 맞는 투자자를 고르게 한다."""
    return "\n".join(f"- {inv.name_ko} / {inv.strategy} / {inv.nickname}" for inv in INVESTORS)


# ── LLM 호출 실패 시 사용할 결정론적 폴백 ──────────────────

def _score(inv: Investor, keywords: list[str]) -> int:
    return sum(1 for k in keywords if any(k and k in w for w in inv.keywords))


def pick_investors(reason: str, top_n: int = 2) -> list[Investor]:
    """장면 키워드로 가장 잘 맞는 투자자를 고른다 (LLM 불필요)."""
    kws = [w.strip() for w in (reason or "").replace("/", " ").split() if w.strip()]
    ranked = sorted(INVESTORS, key=lambda i: _score(i, kws), reverse=True)
    # 점수 0 이면 전략 다양성 확보용 기본 조합
    picked = [i for i in ranked if _score(i, kws) > 0][:top_n]
    if len(picked) < top_n:
        for inv in INVESTORS:
            if len(picked) >= top_n:
                break
            if inv not in picked:
                picked.append(inv)
    return picked


def build_fallback_section(stock_name: str, reason: str,
                           from_high: str = "", range_pos: str = "") -> str:
    """LLM 이 죽어도 투자자 DB 로 본문을 만드는 결정론적 폴백.

    조사 붙이기가 걸리는 이름(린치, 멍거 등)을 피하기 위해
    '~의 말입니다' 형태로 통일한다.
    """
    picked = pick_investors(reason, 2)
    if not picked:
        return ""

    strategy_phrase = {
        "가치 투자(Value Investing)": "좋은 회사를 적당한 가격에 사 오래 붙드는 것",
        "알고 있는 것에 투자하라(Invest in What You Know)": "내가 직접 아는 업종에서만 찾는 것",
        "안전마진(Margin of Safety)": "내재 가치보다 훨씬 싸게 사 여유분을 남기는 것",
        "위험 균형(Risk Parity)과 분산 투자": "위험을 균형 있게 나누는 것",
        "거시 투자(Macro Investing)": "거시 흐름에서 잘못된 가격을 찾는 것",
        "수동적 투자(Passive Investing)": "시장을 이기지 않고 그대로 보유하는 것",
        "기업 행동주의(Corporate Activism)": "지분을 모아 변화를 밀어붙이는 것",
        "대체 투자(Alternative Investments)": "주식과 채권 밖에서 위험을 분산하는 것",
        "알고리즘 트레이딩": "데이터 안의 작은 패턴으로 우위를 만드는 것",
        "정신 모델(Mental Models)과 합리적 투자": "여러 각도에서 따져 보고 규칙을 지키는 것",
    }

    # 위치 설명은 마지막에 한 번만 붙인다
    position = ""
    if from_high:
        position = f"지금 이 종목은 52주 신고가 대비 {from_high} 지점에 있습니다. "
    if range_pos:
        position += f"52주 레인지 안에서는 {range_pos} 자리입니다. "

    parts = []
    for inv in picked:
        phrase = strategy_phrase.get(inv.strategy, inv.strategy)
        parts.append(
            f"{inv.name_ko}의 말입니다. {phrase}. {inv.principle} {inv.case}도 같은 원칙에서 나왔습니다."
        )
    return " ".join(parts) + position