import React from 'react';
import { interpolate, Easing } from 'remotion';
import type { ChartAnnotation } from './ChartAnnotationLayer';
import { C, PAD, VB, stackPanels, type Panel } from '../charts/theme';
import { scaleX, scaleY, type Series } from '../charts/scale';
import { domainForPanel, valueForPanel, PANELS_OF } from '../charts/pointers';
import type { ChartKind } from '../charts';

export type CameraState = {
  scale: number;
  tx: number; // px translation
  ty: number; // px translation
};

const ZOOMABLE_IDS = new Set([
  'ann-candle-breakout',
  'ann-candle-wick',
  'ann-vol-surge',
  'ann-vol-pullback',
  'ann-ma-goldencross',
  'ann-ma-align',
]);

export const useChartCamera = ({
  t,
  annotations,
  series,
  chartKind,
}: {
  t: number;
  annotations?: ChartAnnotation[];
  series: Series | null;
  chartKind: ChartKind;
}): CameraState => {
  // 전문가 차트 분석: 전체 캔들 흐름, 이동평균선 배열, 좌측 최대 매물벽(POC)이
  // 화면 밖으로 잘리거나 왜곡되지 않도록 안정적인 1.0x 풀샷 프레임을 유지한다.
  return { scale: 1.0, tx: 0, ty: 0 };
};

