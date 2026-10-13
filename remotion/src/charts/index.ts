/**
 * 차트 종류 레지스트리.
 *
 * Python 의 stage4_render._chart_kind() 와 같은 규칙을 쓴다.
 * 차트 종류 ↔ 컴포넌트 대응을 한곳에 묶어 StockVideo 가 알지 않게 한다.
 */

import React from 'react';
import type { Series } from './scale';
import { CandleChart } from './CandleChart';
import { TrendChart } from './TrendChart';
import { MomentumChart } from './MomentumChart';
import { ReturnChart } from './ReturnChart';

export type ChartKind = 'price' | 'trend' | 'momentum' | 'return';

export const CHART_ORDER: ChartKind[] = ['price', 'trend', 'momentum', 'return'];

type ChartProps = {
  series: Series;
  name: string;
  ticker: string;
  progress: number;
};

export const CHART_COMPONENTS: Record<ChartKind, React.FC<ChartProps>> = {
  price: CandleChart,
  trend: TrendChart,
  momentum: MomentumChart,
  return: ReturnChart,
};

/** 차트 파일명으로 종류를 추정 (PNG 폴백 경로용) */
export const chartKindOf = (path: string): ChartKind => {
  const n = path.toLowerCase();
  if (n.includes('momentum') || n.includes('rsi')) return 'momentum';
  if (n.includes('return') || n.includes('수익률')) return 'return';
  if (n.includes('trend') || n.includes('_ma')) return 'trend';
  return 'price';
};

export type { Series };
