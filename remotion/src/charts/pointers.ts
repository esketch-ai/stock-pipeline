/**
 * 포인터 좌표 해석.
 *
 * cues.py 는 "어느 봉·패널을 가리킬지" 만 정해 보내고(x/y 를 실어 보내지 않는다),
 * 좌표는 여기서 차트가 그릴 때 쓴 스케일로 계산한다.
 *
 * 이유: 좌표를 Python 과 TypeScript 에 두 벌로 두면 반드시 어긋난다.
 * 포인터와 차트가 같은 스케일 함수를 공유하면 정의상 어긋날 수 없다.
 */

import { stackPanels, type Panel, VB } from './theme';
import { extentOf, scaleX, scaleY, type Series } from './scale';
import type { ChartKind } from './index';

export const PANELS_OF: Record<ChartKind, Panel[]> = {
  price: ['price', 'volume'],
  trend: ['price'],
  momentum: ['price', 'rsi'],
  return: ['return', 'volume'],
};

/**
 * (봉 인덱스, 패널) → 프레임 정규화 좌표.
 * series 가 없거나 범위를 벗어나면 null.
 */
export const specToXY = (
  spec: { index: number; panel: Panel },
  series: Series,
  kind: ChartKind
): { x: number; y: number } | null => {
  const n = series.c.length;
  if (!n || spec.index < 0 || spec.index >= n) return null;

  const panels = PANELS_OF[kind] ?? PANELS_OF.price;
  const rects = stackPanels(panels);
  // 이 차트에 없는 패널의 포인터는 그리지 않는다.
  // (momentum 에 '거래량 급증' 포인터를 가격축에 그리는 식의 잘못된 표시 방지)
  const rect = rects[spec.panel];
  if (!rect) return null;

  // 축은 차트가 '전부 공개된' 상태의 도메인을 쓴다.
  // (포인터는 차트가 다 그려진 뒤에 나타나므로 이쪽이 맞다)
  const domain = domainForPanel(spec.panel, series);
  if (!domain) return null;

  const y = scaleY(domain, [rect.y + rect.h, rect.y]);
  const v = valueForPanel(spec.panel, series, spec.index);
  if (v === null) return null;

  return {
    x: scaleX(spec.index, n, rect) / VB.w,
    y: y(v) / VB.h,
  };
};

export const valueForPanel = (
  panel: Panel,
  series: Series,
  i: number
): number | null => {
  const pick = (arr?: (number | null)[]): number | null => {
    const v = arr?.[i];
    return v === null || v === undefined || !Number.isFinite(v) ? null : v;
  };
  if (panel === 'price') return pick(series.h) ?? pick(series.c);
  if (panel === 'volume') return pick(series.v);
  if (panel === 'rsi') return pick(series.rsi);
  if (panel === 'return') return pick(series.ret);
  return null;
};

export const domainForPanel = (panel: Panel, series: Series): [number, number] | null => {
  const n = series.c.length;
  if (panel === 'rsi') return [0, 100];
  if (panel === 'volume') {
    const d = extentOf([series.v], n, 0.1);
    return [0, Math.max(d[1], 1)];
  }
  if (panel === 'return') {
    const d = extentOf([series.ret ?? []], n, 0.12);
    const span = Math.max(Math.abs(d[0]), Math.abs(d[1]), 5);
    return [-span, span];
  }
  const d = extentOf([series.h, series.l], n, 0.08);
  return num0(d) ? d : null;
};

const num0 = (d: [number, number]) => Number.isFinite(d[0]) && Number.isFinite(d[1]);
