"""투자 원칙을 종목별 질문·근거·반증·장면으로 변환하는 편집 계획.

참고: https://wikidocs.net/212441 (2026-10-13 열람).
아래 문구는 편집용 요약이며 해당 인물의 직접 인용이 아니다.
"""
from collections import Counter
import json

SOURCE = 'https://wikidocs.net/212441'
LENSES = [
    dict(id='business_value', investor='워렌 버핏',
         principle='주가 변화와 기업의 장기 가치를 구분한다.',
         question='시장 가격이 변한 만큼 기업 가치도 변했다고 말할 근거가 있는가?',
         evidence='현재가·시가총액은 가격의 관찰값이다. 수익·현금흐름이 제공될 때만 가치와 비교한다.',
         missing='재무 자료가 없으면 적정가나 저평가를 판정하지 않는다.',
         visual='가격 변화와 기업 가치 확인 항목을 분리한 비교 카드'),
    dict(id='expectations', investor='조지 소로스',
         principle='시장 움직임에 대한 가설을 세우고 반대 증거로 점검한다.',
         question='최근 움직임을 설명하는 기대가 틀렸다면 어떤 관찰이 먼저 나타나는가?',
         evidence='동일 기준의 기간별 수익률·거래량을 비교해 관찰과 가설을 구분한다.',
         missing='수급 주체·뉴스 원인·환율 영향은 제공된 근거 없이 확정하지 않는다.',
         visual='시간축별 변화와 가설/반증을 대조하는 카드'),
    dict(id='business_understanding', investor='피터 린치',
         principle='관심을 갖게 된 계기와 실제 사업에 대한 조사를 구분한다.',
         question='이 종목에 대한 관심 중 확인한 사실은 무엇이고 더 조사해야 할 사업 질문은 무엇인가?',
         evidence='제공된 사업·제품·매출 자료에서 질문을 도출한다. 시세만 있으면 관심 신호와 미확인 사업 정보를 구분한다.',
         missing='회사 이름에서 업종·고객·제품을 추측하지 않는다. 자료가 없다는 말로 분량을 채우지 않는다.',
         visual='관찰된 시세/확인된 사업 사실/추가 조사 항목의 세 칸 카드'),
    dict(id='risk_budget', investor='레이 달리오',
         principle='확신의 크기보다 위험을 구분하고 판단 기준을 일관되게 둔다.',
         question='이 종목을 판단할 때 서로 다른 위험을 하나의 상승률로 뭉뚱그리고 있지 않은가?',
         evidence='기간별 가격 변화와 거래량, 연중 범위로 단기 변동과 장기 낙폭을 구분한다.',
         missing='다른 자산의 자료 없이 상관관계·최적 비중·분산 효과를 수치로 주장하지 않는다.',
         visual='단기 변동/장기 가격 위치/정보 부족의 위험 지도'),
    dict(id='corporate_change', investor='칼 아이칸',
         principle='기업의 변화가 주주에게 어떤 경제적 의미를 갖는지 살핀다.',
         question='가격 변동과 별개로 기업에 실제 확인된 변화가 있는가?',
         evidence='날짜와 출처가 있는 지분·지배구조·분할·자본배분 공시가 있을 때 적용한다.',
         missing='공시 근거가 없으면 이 관점을 배정하지 않는다.',
         visual='공시 시점과 주주 영향의 사건 타임라인'),
]
STRUCTURES = [
    ('evidence_first', '가장 특이한 관찰 → 가능한 해석 둘 → 판별 근거 → 남는 질문'),
    ('counterexample', '흔한 해석 하나 → 이 종목에서 맞지 않는 근거 → 수정한 해석 → 판단을 바꿀 조건'),
    ('investigation', '종목별 질문 → 확인된 사실 추적 → 처음 예상과 달랐던 점 → 답과 후속 확인'),
]

BRUNCH_SOURCE = 'https://brunch.co.kr/@kimwoss/84'
LENSES.extend([
    dict(id='quant_validation', investor='짐 사이먼스', principle='패턴의 인상과 검증된 규칙을 구분한다.',
         question='기간과 비교 기준을 바꾸어도 이 움직임에 대한 해석이 유지되는가?',
         evidence='기간별 수익률과 거래량의 비교 기준을 점검한다.',
         missing='백테스트 없이 승률·예측력·통계적 유의성을 주장하지 않는다.', visual='기간별 관찰값 비교'),
    dict(id='downside', investor='마이클 버리', principle='낙관적인 설명에서 빠진 손실 경로를 찾는다.',
         question='이 종목에 대한 낙관적 해석에서 빠진 반대 증거는 무엇인가?',
         evidence='제공된 가격 범위·변화·거래량에서 기대와 어긋나는 관찰을 찾는다.',
         missing='부실이나 거품을 근거 없이 확정하지 않는다.', visual='기대와 반대 증거의 대조'),
    dict(id='innovation', investor='캐시 우드', principle='혁신 가능성과 상용화 성과를 구분한다.',
         question='제품의 가능성이 실제 매출이나 이용으로 연결되는 근거가 있는가?',
         evidence='출처가 있는 사업·제품·상용화 자료를 비교한다.',
         missing='회사 이름만으로 AI·기술 테마를 붙이지 않는다.', visual='제품에서 고객 가치까지의 흐름'),
    dict(id='investment_thesis', investor='빌 애크먼', principle='투자 논리의 가정과 실패 조건을 명확히 한다.',
         question='이 기업을 설명하는 핵심 가정이 깨지면 결론이 어떻게 달라지는가?',
         evidence='기업의 사업 자료에서 검증 가능한 핵심 가정과 반대 근거를 뽑는다.',
         missing='실제 보유종목이나 매수 의견처럼 말하지 않는다.', visual='가정과 확인 근거 비교'),
    dict(id='accounting_quality', investor='데이비드 아인혼', principle='기업의 설명과 재무 자료가 일치하는지 점검한다.',
         question='기업이 제시한 성장 설명과 실제 재무 수치는 같은 방향인가?',
         evidence='출처가 있는 재무제표·현금흐름 자료를 비교한다.',
         missing='재무 자료 없이 회계 부정이나 부실을 암시하지 않는다.', visual='설명과 재무 근거 대조'),
    dict(id='product_execution', investor='토비아스 뤼트케', principle='기술을 고객 가치와 사업 실행의 관점에서 살핀다.',
         question='이 기업의 제품은 누구의 문제를 해결하고 성과는 무엇으로 확인하는가?',
         evidence='출처가 있는 사업·제품·고객 자료를 활용한다.',
         missing='기업가 관점을 투자 수익 보장이나 추천으로 바꾸지 않는다.', visual='제품·고객·실행의 연결'),
])


def character_insight(plan: dict | None) -> dict | None:
    if not plan:
        return None
    ids = {'워렌 버핏': 'buffett', '조지 소로스': 'soros', '레이 달리오': 'dalio',
           '캐시 우드': 'wood', '짐 사이먼스': 'simons', '칼 아이칸': 'icahn',
           '빌 애크먼': 'ackman', '마이클 버리': 'burry', '데이비드 아인혼': 'einhorn',
           '토비아스 뤼트케': 'lutke'}
    identity = ids.get(plan.get('investor'))
    if not identity:
        return None
    return {'id': identity, 'principle': plan['principle'],
            'question': (plan.get('outline') or {}).get('question', plan.get('question', ''))}


def allocate(facts: dict, reserved: list[dict]) -> dict:
    """근거가 있는 관점만 선택하며 같은 관점/전개 조합은 배치에서 분산."""
    eligible = [lens for lens in LENSES if lens['id'] != 'corporate_change'
                or facts.get('verified_corporate_events')]
    # 사업 자료가 없는 상태에서는 사업 해설을 약속하지 않는다.
    if not facts.get('business'):
        eligible = [lens for lens in eligible if lens['id'] not in {
            'business_understanding', 'innovation', 'investment_thesis', 'product_execution'}]
    if not facts.get('financials'):
        eligible = [lens for lens in eligible if lens['id'] != 'accounting_quality']
    counts = Counter(p['lens_id'] for p in reserved)
    lens = min(eligible, key=lambda x: counts[x['id']])
    used = Counter(p['structure_id'] for p in reserved if p['lens_id'] == lens['id'])
    sid, structure = min(STRUCTURES, key=lambda x: used[x[0]])
    plan = dict(lens_id=lens['id'], structure_id=sid, structure=structure,
                **{k: v for k, v in lens.items() if k != 'id'}, source=SOURCE if lens in LENSES[:5] else BRUNCH_SOURCE,
                ticker=facts.get('ticker'), name=facts.get('name'))
    reserved.append(plan)
    return plan


def instruction(plan: dict) -> str:
    return ('[이번 종목의 주 분석 관점 — 전 구간에서 유지]\n'
            + json.dumps(plan, ensure_ascii=False, indent=2)
            + '\n위 원칙은 편집용 요약이지 직접 인용문이 아니다. 따옴표 명언을 만들지 않는다. '
            '투자자 이름은 꼭 필요할 때 한 번만 소개한다. 이름을 바꿔 같은 멘트를 반복하지 않는다. '
            '핵심 수치·심층 해석·리스크·정리의 역할은 유지하되 배정된 질문과 전개로 구성한다. '
            '현재가 위/옆/아래 세 시나리오, 신고가까지 거리, 오른 자리 유지라는 공통 틀로 되돌아가지 않는다. '
            '연락 CTA는 이 관점에서 도출한 구체적인 확인 항목과 연결한다.')


async def make_outline(facts_block, reason, brief, plan, previous, call_llm):
    """대본보다 먼저 종목 고유 질문과 실제 근거를 명시한다."""
    prompt = f'''당신은 15편 종목 분석 영상의 편집자다. 완성 대본 전에 이번 종목의 취재·편집 계획을 작성한다.
{instruction(plan)}
[확인된 자료]
{facts_block}
[기술 관찰]
{reason}
[종목 브리프]
{brief}
[다른 종목에 이미 사용한 계획 — 중심 질문과 결론 반복 금지]
{json.dumps(previous, ensure_ascii=False)}
JSON 객체만 출력한다: {{"question":"이 종목 자료에서 나온 구체적인 질문", "evidence":["자료에 실제 있는 근거1","근거2"], "counterpoint":"다른 해석 또는 반증 조건", "conclusion":"이 근거로 답할 수 있는 결론", "sections":{{"hook":"도입 내용", "setup":"배경", "reveal":"핵심 발견", "deep_dive":"해석", "risk":"이 종목의 반증 조건", "wisdom":"다시 확인할 항목", "outro":"질문 회수"}}}}
미제공 재무/공시 사실을 만들지 않는다. 누구에게나 해당하는 경고로 분량을 늘리지 않는다.'''
    raw = await call_llm(prompt, as_json=True)
    raw = raw.strip()
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[1].rsplit('```', 1)[0]
    outline = json.loads(raw)
    for field in ('question', 'counterpoint', 'conclusion'):
        if not isinstance(outline.get(field), str) or not outline[field].strip():
            raise ValueError(f'편집 계획 필드 누락: {field}')
    if not isinstance(outline.get('evidence'), list) or len(outline['evidence']) < 2:
        raise ValueError('편집 계획에 실제 근거 두 개가 필요합니다.')
    if not isinstance(outline.get('sections'), dict) or not all(outline['sections'].get(s) for s in ('hook', 'setup', 'reveal', 'deep_dive', 'risk', 'wisdom', 'outro')):
        raise ValueError('편집 계획에 7개 구간이 필요합니다.')
    return outline
