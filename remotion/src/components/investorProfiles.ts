/** 해설용 원칙 요약. 직접 인용·수익률·현재 보유종목 주장이 아니다.
 * 참고: https://brunch.co.kr/@kimwoss/84
 */
export const investorProfiles = [
  {id: 'buffett', name: '워렌 버핏', role: '가치와 복리', principle: '시장 가격과 기업의 장기 가치를 구분한다.', color: '#E9BD69', hair: '#F2EBDF', glasses: true, style: 'side', tie: '#D95D59'},
  {id: 'soros', name: '조지 소로스', role: '기대와 반증', principle: '시장에 대한 가설을 반대 증거로 점검한다.', color: '#9DADDC', hair: '#D4D6DB', glasses: false, style: 'swept', tie: '#526DA0'},
  {id: 'dalio', name: '레이 달리오', role: '위험과 원칙', principle: '서로 다른 위험을 나누어 판단한다.', color: '#7AC9B2', hair: '#E5E1D8', glasses: false, style: 'side', tie: '#4A8F91'},
  {id: 'wood', name: '캐시 우드', role: '혁신과 상용화', principle: '기술의 가능성과 사업 성과를 구분한다.', color: '#D4A5E4', hair: '#523A32', glasses: true, style: 'long', tie: '#7A557E'},
  {id: 'simons', name: '짐 사이먼스', role: '데이터와 검증', principle: '눈에 띄는 패턴을 반복 가능한 근거와 구분한다.', color: '#81C7E2', hair: '#EAE8E3', glasses: false, style: 'beard', tie: '#6299B0'},
  {id: 'icahn', name: '칼 아이칸', role: '변화와 주주가치', principle: '기업의 변화가 주주에게 미치는 영향을 따진다.', color: '#E6A581', hair: '#DFDBD5', glasses: false, style: 'side', tie: '#A05449'},
  {id: 'ackman', name: '빌 애크먼', role: '집중과 투자 논리', principle: '집중된 판단일수록 가정과 실패 조건을 명확히 한다.', color: '#AABCE6', hair: '#D2D4D5', glasses: false, style: 'swept', tie: '#5369A2'},
  {id: 'burry', name: '마이클 버리', role: '반대 증거와 손실', principle: '낙관적인 설명에서 빠진 손실 경로를 찾는다.', color: '#C0BF83', hair: '#604C3E', glasses: false, style: 'short', tie: '#777649'},
  {id: 'einhorn', name: '데이비드 아인혼', role: '회계와 실질', principle: '기업의 설명과 재무 자료가 일치하는지 확인한다.', color: '#D6A0B1', hair: '#6D5344', glasses: false, style: 'swept', tie: '#9B5773'},
  {id: 'lutke', name: '토비아스 뤼트케', role: '제품과 실행', principle: '기술의 이야기가 고객 가치와 사업 실행으로 이어지는지 묻는다.', color: '#8ACFA0', hair: '#654D3B', glasses: false, style: 'cap', tie: '#467F63'},
] as const;

export type InvestorId = typeof investorProfiles[number]['id'];
export type InvestorInsight = {id: string; principle: string; question?: string};
