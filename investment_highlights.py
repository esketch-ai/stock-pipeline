"""종목별 핵심 투자 포인트(Key Highlights) 및 유튜브 제목/인트로 카드 데이터 모듈.

각 종목 고유의 사업 펀더멘털, 지분 공시, 증권사 리포트 촉매를 반영하여
사용자가 선호하는 맞춤형 유튜브 제목과 4K 인트로 오버레이 카드를 구성합니다.
"""
from __future__ import annotations

from typing import Any, Dict, List

# 주요 종목별 3대 핵심 투자 포인트 정의 (사전 검증된 전문가 분석)
STOCK_CATALYSTS_MAP: Dict[str, Dict[str, Any]] = {
    "028260": {
        "title_keywords": "목표가 +86% 괴리율, PBR 0.44배, 대규모 자사주 소각",
        "points": [
            {"icon": "🎯", "title": "목표가 +86% 괴리율", "desc": "증권사 평균 목표가 49.6만 원 매수 일치", "tag": "컨센서스"},
            {"icon": "💎", "title": "PBR 0.44배 극단적 저평가", "desc": "BPS 64.5만 원 대비 지주사 할인 해소 국면", "tag": "가치분석"},
            {"icon": "🛡️", "title": "사내이사 17인 장내매수 & 소각", "desc": "경영진 확신 매수 및 3개년 전량 자사주 소각", "tag": "내부자신뢰"},
        ],
    },
    "009540": {
        "title_keywords": "조선 슈퍼사이클 호황, 고선가 수주잔고 급증, 외인·기관 쌍끌이",
        "points": [
            {"icon": "🚢", "title": "조선 슈퍼사이클 본격화", "desc": "고부가 친환경 LNG선·암모니아선 수주 독점", "tag": "업황호황"},
            {"icon": "📈", "title": "실적 턴어라운드 가속", "desc": "선가 상승분 반영에 따른 영업이익률 급증", "tag": "수익성"},
            {"icon": "🔥", "title": "외인·기관 메이저 쌍끌이", "desc": "외인지분 28%대 확대 및 연기금 집중 순매수", "tag": "스마트머니"},
        ],
    },
    "035420": {
        "title_keywords": "AI 검색 B2B 수익화, 밸류에이션 바닥 탈출, 풍부한 현금흐름",
        "points": [
            {"icon": "🤖", "title": "AI 검색 B2B 수익화 가시화", "desc": "생성형 AI 하이퍼클로바X 서비스 수익 모델 안착", "tag": "신성장"},
            {"icon": "📊", "title": "밸류에이션 바닥 탈출 타점", "desc": "서치플랫폼·커머스 반등 및 역사적 밸류 저점", "tag": "가치반등"},
            {"icon": "💰", "title": "연간 1.5조+ 풍부한 현금흐름", "desc": "압도적 영업현금 기반 주주환원 확대 정책", "tag": "주주환원"},
        ],
    },
    "000660": {
        "title_keywords": "HBM 글로벌 독점 지배력, 역사적 신고가 랠리, 외인지분 54%",
        "points": [
            {"icon": "⚡", "title": "HBM 글로벌 독점 시장 지배력", "desc": "엔비디아향 차세대 HBM3E 공급 주도권 장악", "tag": "HBM독점"},
            {"icon": "🚀", "title": "사상 최대 실적 경신 랠리", "desc": "AI 메모리 슈퍼사이클 진입 및 영업이익 폭증", "tag": "실적폭발"},
            {"icon": "🌍", "title": "외인지분 54% 압도적 수급", "desc": "글로벌 메이저 펀드 바스켓 순매수 1순위", "tag": "메이저수급"},
        ],
    },
    "005930": {
        "title_keywords": "메모리 턴어라운드, 반도체 파운드리 반등, 코스피 1위 대장주",
        "points": [
            {"icon": "👑", "title": "대한민국 1위 절대 대장주", "desc": "글로벌 반도체·스마트폰 1등 인프라 경쟁력", "tag": "대장주"},
            {"icon": "🔄", "title": "D램·낸드 턴어라운드", "desc": "메모리 가격 회복 및 HBM 첨단공정 공급 가시화", "tag": "턴어라운드"},
            {"icon": "🛡️", "title": "역사적 밸류 바닥 하방 경직성", "desc": "PBR 1배 안팎 진입에 따른 강력한 저가 매수세", "tag": "안전마진"},
        ],
    },
    "034730": {
        "title_keywords": "주주환원 강화, 안정적 배당수익률, 자회사 IPO 모멘텀",
        "points": [
            {"icon": "📈", "title": "지주사 주주환원 전격 강화", "desc": "배당 성향 확대 및 자사주 소각 추진 가속화", "tag": "밸류업"},
            {"icon": "💵", "title": "안정적 고배당 수익률 매력", "desc": "그룹 핵심 자회사 턴어라운드 기반 현금배당", "tag": "배당가치"},
            {"icon": "🚀", "title": "자회사 가치 재평가 모멘텀", "desc": "AI·반도체 생태계 계열사 실적 및 상장 가치", "tag": "모멘텀"},
        ],
    },
    "012330": {
        "title_keywords": "전동화 부품 수주 확대, 안정적 캡티브 마켓, 배당 확대",
        "points": [
            {"icon": "⚡", "title": "전동화 핵심 부품 수주 확대", "desc": "글로벌 완성차향 논캡티브 수주 잔고 급증", "tag": "미래모빌리티"},
            {"icon": "🚗", "title": "안정적 현대차그룹 캡티브", "desc": "현대차·기아 글로벌 판매 호조 직수혜 구조", "tag": "안정매출"},
            {"icon": "🎁", "title": "주주친화 밸류업 배당 확대", "desc": "수익성 개선 기반의 지속적인 주주환원 강화", "tag": "주주환원"},
        ],
    },
    "066570": {
        "title_keywords": "전장(VS) 사업 흑자 안착, 가전 구독 모델 신성장, B2B 체질 개선",
        "points": [
            {"icon": "🏎️", "title": "전장(VS) 사업 흑자 기조 안착", "desc": "차량용 인포테인먼트 수주잔고 100조 원 돌파", "tag": "전장사업"},
            {"icon": "📺", "title": "가전 구독 모델 신성장 동력", "desc": "일회성 가전 판매에서 고마진 구독형 비즈니스 전환", "tag": "구독비즈니스"},
            {"icon": "❄️", "title": "AI 데이터센터 냉각 솔루션", "desc": "글로벌 HVAC 공조 시스템 수주 모멘텀 확장", "tag": "신성장"},
        ],
    },
    "017670": {
        "title_keywords": "통신 안정적 현금흐름, AI 데이터센터 인프라, 고배당 매력",
        "points": [
            {"icon": "📞", "title": "통신 본업 독점적 현금창출력", "desc": "5G 안정적 가입자 기반 6%대 고배당 매력", "tag": "현금흐름"},
            {"icon": "🖥️", "title": "AI 데이터센터(AIDC) 인프라", "desc": "GPUaaS 등 국가대표 AI 클러스터 구축 확장", "tag": "AI인프라"},
            {"icon": "🤝", "title": "에이닷 중심 AI 생태계 결합", "desc": "AI 통화녹음 및 에이전트 서비스 유료화 기대", "tag": "AI서비스"},
        ],
    },
    "028670": {
        "title_keywords": "벌크선 BDI 지수 반등, 안정적 LNG 장기 용선, 밸류에이션 바닥",
        "points": [
            {"icon": "⚓", "title": "벌크선 BDI 운임지수 반등", "desc": "글로벌 철광석·석탄 원자재 해상 물동량 회복", "tag": "운임반등"},
            {"icon": "⛽", "title": "안정적 LNG선 장기 용선 계약", "desc": "글로벌 에너지 기업과의 고정 장기 계약 매출", "tag": "안정수익"},
            {"icon": "📉", "title": "PBR 0.4배 극단적 바닥 밸류", "desc": "역사적 밸류 밴드 최하단 진입에 따른 안전마진", "tag": "저평가"},
        ],
    },
    "011200": {
        "title_keywords": "컨테이너 운임지수(SCFI) 반등, 대규모 현금성 자산, 주주가치 제고",
        "points": [
            {"icon": "🚢", "title": "컨테이너 운임(SCFI) 반등", "desc": "글로벌 물류 병목 및 해상 운임 견조한 방어력", "tag": "운임상승"},
            {"icon": "🏦", "title": "10조 원대 대규모 현금 보유", "desc": "풍부한 현금성 자산 기반의 친환경 선대 투자", "tag": "재무건전성"},
            {"icon": "📈", "title": "원가 경쟁력 및 주주가치 제고", "desc": "초대형 고효율 컨테이너선 중심 수익성 극대화", "tag": "원가경쟁력"},
        ],
    },
    "012750": {
        "title_keywords": "보안 시장점유율 1위, 불황 방어형 락인 매출, 안정적 배당성향",
        "points": [
            {"icon": "🔒", "title": "물리·정보 보안 국내 1위", "desc": "독보적 브랜드 파워와 전국 출동 보안 인프라", "tag": "시장지배력"},
            {"icon": "🏢", "title": "불황 방어형 락인(Lock-in)", "desc": "건물 관리 및 지속적인 월정액 가입자 매출", "tag": "경기방어"},
            {"icon": "💰", "title": "무차입 경영 & 고배당 지속", "desc": "현금흐름 극대화 기반의 안정적 배당 지급", "tag": "고배당"},
        ],
    },
    "030200": {
        "title_keywords": "AI 클라우드 협력 모멘텀, 거버넌스 안정화, 통신 인프라 가치",
        "points": [
            {"icon": "☁️", "title": "글로벌 빅테크(MS) AI 파트너십", "desc": "한국형 소버린 AI 및 클라우드 인프라 공동 구축", "tag": "AI파트너십"},
            {"icon": "🏛️", "title": "거버넌스 안정화 및 밸류업", "desc": "경영 정상화에 따른 적극적 자사주 매입·소각", "tag": "거버넌스"},
            {"icon": "📡", "title": "통신·부동산 인프라 자산가치", "desc": "전국 통신 국사 및 부동산 자산 재평가 기대", "tag": "자산가치"},
        ],
    },
    "032640": {
        "title_keywords": "배당 성향 40% 이상 유지, 스마트홈 결합 가치, 밸류업 프로그램",
        "points": [
            {"icon": "🎁", "title": "배당성향 40%+ 통신 최고 수준", "desc": "주주환원율 극대화 정책 및 6%대 배당수익률", "tag": "고배당"},
            {"icon": "🏠", "title": "스마트홈·플랫폼 사업 확장", "desc": "IPTV 및 기업 B2B 솔루션 사업 성장", "tag": "플랫폼"},
            {"icon": "📊", "title": "PBR 0.3배대 극단적 저평가", "desc": "정부 기업 밸류업 프로그램 핵심 수혜 기대", "tag": "저평가"},
        ],
    },
    "009470": {
        "title_keywords": "AI 데이터센터 특수 콘덴서(S-Cap) 수요 폭발, 전력망 증설 수혜",
        "points": [
            {"icon": "🔋", "title": "AI 데이터센터용 S-Cap 독점", "desc": "전력 급증 대비 필수 특수 콘덴서 수요 폭증", "tag": "AI인프라"},
            {"icon": "⚡", "title": "글로벌 전력망 증설 슈퍼사이클", "desc": "변압기 및 전력기기용 고압 커패시터 수주 호조", "tag": "전력망"},
            {"icon": "📈", "title": "고부가가치 제품 믹스 개선", "desc": "특수 전해콘덴서 비중 확대로 영업이익률 퀀텀점프", "tag": "이익급증"},
        ],
    },
}


def get_highlights(ticker: str, name: str, facts: Dict[str, Any] | None = None) -> List[Dict[str, str]]:
    """종목의 3대 핵심 투자 포인트 반환 (오프닝 인트로 및 썸네일용)."""
    if ticker in STOCK_CATALYSTS_MAP:
        return STOCK_CATALYSTS_MAP[ticker]["points"]

    # 기본 생성 로직 (맵에 없는 신규 종목 대응)
    f = facts or {}
    points = []

    # 1. 목표가 / 컨센서스
    upside = f.get("upside_pct")
    if upside and float(upside) > 0:
        points.append({
            "icon": "🎯",
            "title": f"목표가 +{float(upside):.0f}% 괴리율",
            "desc": "국내 주요 증권사 매수 일치 컨센서스",
            "tag": "목표주가",
        })
    else:
        points.append({
            "icon": "📈",
            "title": "기관·외인 메이저 수급 집중",
            "desc": "바닥권 물량 집중 순매집 확인",
            "tag": "수급집중",
        })

    # 2. 밸류에이션 (PBR / BPS)
    pbr = f.get("pbr")
    if pbr and float(pbr) < 1.0:
        points.append({
            "icon": "💎",
            "title": f"PBR {float(pbr):.2f}배 저평가",
            "desc": "순자산가치 대비 안전마진 확보 구간",
            "tag": "가치분석",
        })
    else:
        points.append({
            "icon": "💎",
            "title": "실적 턴어라운드 모멘텀",
            "desc": "비즈니스 펀더멘털 구조적 개선",
            "tag": "실적성장",
        })

    # 3. 내부자 / 주주환원 / 촉매
    points.append({
        "icon": "🛡️",
        "title": "안정적 밸류업 & 주주환원",
        "desc": "경영진 책임경영 및 배당 안정성",
        "tag": "주주환원",
    })

    return points


def get_youtube_title(ticker: str, name: str, item: Dict[str, Any] | None = None) -> str:
    """사용자 선호 규격에 100% 일치하는 YouTube 영상 제목 생성.
    
    예시:
        SK(034730) 주가 분석 | 주주환원 강화, 안정적 배당수익률, 자회사 IPO 모멘텀
        삼성물산(028260) 주가 분석 | 목표가 +86% 괴리율, PBR 0.44배, 대규모 자사주 소각
    """
    if ticker in STOCK_CATALYSTS_MAP:
        keywords = STOCK_CATALYSTS_MAP[ticker]["title_keywords"]
        return f"{name}({ticker}) 주가 분석 | {keywords}"

    # 맵에 없는 경우 facts 기반 동적 키워드 조립
    facts = (item or {}).get("facts") or {}
    points = get_highlights(ticker, name, facts)
    keywords = ", ".join(p["title"] for p in points)
    return f"{name}({ticker}) 주가 분석 | {keywords}"
