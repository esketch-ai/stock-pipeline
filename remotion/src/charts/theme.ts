/**
 * 차트 테마 — charts_extended.py 의 _COLORS 와 1:1 로 맞춘다.
 * matplotlib 과 Remotion 이 같은 팔레트를 쓰도록 한 곳에서 관리한다.
 */

export const C = {
  up: '#FF3B30',
  down: '#0A84FF',
  accent: '#FFD60A',
  purple: '#BF5AF2',
  grid: '#2A3550',
  fg: '#F5F7FA',
  dim: '#8FA3C8',
  panel: '#0E1728',
  backpad: '#0B1220',
} as const;

export const FONT = 'Apple SD Gothic Neo, Pretendard, sans-serif';
export const MONO = 'SF Mono, Menlo, monospace';

/** SVG 논리 해상도 — 실제 렌더 해상도와 무관하게 이 좌표계로 그린다. */
export const VB = { w: 1920, h: 1080 } as const;

/**
 * 차트 공통 여백.
 *
 * 세로 예산 (1080 기준):
 *    0 ~ 100   비움 — 상단 지표 스트립 제거
 *  142 ~ 330   장면 헤드라인 · 부제   ← SceneFrame
 *  330 ~ 880   차트 패널
 *  912         날짜 라벨
 *  920 ~ 960   핵심 수치 (stats)
 *  985 ~ 1045  자막 (CinematicCaption)
 *  1040 ~      진행 바 · 종목 라벨
 *
 * 차트 안에서 제목을 또 그리지 않는다 — 헤드라인은 장면이 이미 말하고 있다.
 */
export const PAD = {
  left: 90,
  right: 170, // 우측 가격 축 배지 및 수평선 태그 안전 마진 확보
  top: 175,   // 상단 헤드라인 바로 아래 (140px 뷰포트 시작, 175px 챠트 패널 시작)
  bottom: 150, // 하단 자막(970px) 위 (930px 챠트 패널 종료 — 높이 755px 극대화)
  gap: 16,
  statsY: 38,
  dateLabelY: 915,
} as const;

export type Rect = { x: number; y: number; w: number; h: number };

export type Panel = 'price' | 'volume' | 'rsi' | 'return';

/**
 * 패널 스택 — 차트 종류별로 세로 배분을 선언한다.
 * 비율에 따라 위에서부터 쌓인다.
 */
export const PANEL_RATIOS: Record<Panel, number> = {
  price: 3,
  volume: 1,
  rsi: 1,
  return: 3,
};

export const stackPanels = (panels: Panel[]): Record<Panel, Rect> => {
  const inner: Rect = {
    x: PAD.left,
    y: PAD.top,
    w: VB.w - PAD.left - PAD.right,
    h: VB.h - PAD.top - PAD.bottom,
  };
  const total = panels.reduce((s, p) => s + PANEL_RATIOS[p], 0);
  const usable = inner.h - PAD.gap * (panels.length - 1);

  const out = {} as Record<Panel, Rect>;
  let y = inner.y;
  panels.forEach((p) => {
    const h = (usable * PANEL_RATIOS[p]) / total;
    out[p] = { x: inner.x, y, w: inner.w, h };
    y += h + PAD.gap;
  });
  return out;
};
