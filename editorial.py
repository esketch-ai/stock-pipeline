"""종목별 편집 브리프와 배치 대본 중복 검사."""
import re


def stock_brief(facts: dict, reason: str) -> str:
    def number(key):
        try:
            return float(str(facts[key]).replace('%', '').replace(',', ''))
        except (KeyError, TypeError, ValueError):
            return None

    change = number('change_raw')
    position = number('range_pos')
    distance = number('from_high')
    angles = []
    if change is not None and change < 0:
        angles.append('당일 하락을 출발점으로, 연중 가격 위치와 함께 조정의 크기를 비교한다. 반등을 전제하지 않는다.')
    elif change is not None and change >= 10:
        angles.append('급격한 하루 상승폭이 중심이다. 단기 변화와 연중 위치의 차이를 설명하고 지속 여부를 확인할 조건을 찾는다.')
    if position is not None and position >= 85:
        angles.append('연중 고가권에 있다는 점이 핵심이다. 고점 접근과 돌파 확정을 구분하고 확인 가능한 거래량 근거를 비교한다.')
    elif position is not None and position <= 25:
        angles.append('연중 저가권이라는 위치가 핵심이다. 가격이 낮다는 사실과 저평가라는 판단을 구분한다.')
    if distance is not None and distance <= -40:
        angles.append('고점과 현재가 사이의 큰 거리를 중심으로 설명한다. 하루 상승만으로 과거 하락을 회복했다고 말하지 않는다.')
    if not angles:
        angles.append('제공된 가격 위치·일간 변화·거래량 중 가장 설명력이 높은 대비 하나를 직접 선택하고 선택 근거를 명시한다.')
    return (
        f"분석 대상: {facts.get('name', '')} ({facts.get('ticker', '')})\n"
        + '\n'.join(f'- {a}' for a in angles)
        + f'\n확인된 기술 관찰: {reason}\n'
        '이 자료로 이 종목에만 해당하는 질문 하나와 이를 지지하는 근거 두 개를 정한다. '
        '이름과 숫자를 지웠을 때 다른 종목에 그대로 붙일 수 있는 설명은 다시 쓴다. '
        '업종·제품·경쟁사·실적·공시가 제공되지 않았다면 회사 이름으로 추측하지 않는다. '
        '섹션은 제작용 구분일 뿐 매번 같은 질문·비유·접속어를 쓰지 않는다. '
        '자료 신청 이유도 이 종목에서 확인한 조건과 연결한다.'
    )

def _sentences(text: str, names: list[str]) -> list[str]:
    for name in sorted(filter(None, names), key=len, reverse=True):
        text = text.replace(name, '종목')
    result = []
    for sentence in re.split(r'(?<=[.!?])\s+|\n+', text):
        # 공통 법적 고지와 연락 안내는 독창성 평가에서 제외한다.
        if any(x in sentence for x in ('투자 권유', '투자 판단과 책임', '설명란', '신청 링크')):
            continue
        sentence = re.sub(r'\d[\d,.]*', '#', sentence)
        sentence = re.sub(r'[^가-힣a-zA-Z#]', '', sentence)
        if len(sentence) >= 15:
            result.append(sentence)
    return result


def overlap(text: str, previous: str, names: list[str]) -> float:
    """이름·숫자를 제거한 문장과 18자 연속 구절의 중복률 중 큰 값."""
    a, b = _sentences(text, names), _sentences(previous, names)
    if not a or not b:
        return 0.0
    sentence_ratio = len(set(a) & set(b)) / max(1, min(len(set(a)), len(set(b))))
    def grams(sentences):
        return {s[i:i + 18] for s in sentences for i in range(max(0, len(s) - 17))}
    ga, gb = grams(a), grams(b)
    phrase_ratio = len(ga & gb) / max(1, min(len(ga), len(gb)))
    return max(sentence_ratio, phrase_ratio)
