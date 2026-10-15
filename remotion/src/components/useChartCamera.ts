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
  const defaultState: CameraState = { scale: 1.0, tx: 0, ty: 0 };
  if (!series || !annotations?.length) {
    return defaultState;
  }

  const n = series.c.length;
  if (!n) return defaultState;

  const panels = PANELS_OF[chartKind] ?? PANELS_OF.price;
  const rects = stackPanels(panels);
  const priceRect = rects.price;
  const volRect = rects.volume;
  const priceDomain = domainForPanel('price', series);
  const volDomain = domainForPanel('volume', series);

  const py = priceDomain && priceRect ? scaleY(priceDomain, [priceRect.y + priceRect.h, priceRect.y]) : null;
  const vy = volDomain && volRect ? scaleY(volDomain, [volRect.y + volRect.h, volRect.y]) : null;

  // 줌 대상인 어노테이션만 필터링
  const zoomable = annotations.filter(
    (a) =>
      ZOOMABLE_IDS.has(a.id) &&
      (a.kind === 'box' || a.kind === 'pointer' || a.kind === 'circle' || a.kind === 'underline') &&
      a.index !== undefined &&
      a.index >= 0
  );

  for (const ann of zoomable) {
    const start = ann.from;
    const end = ann.to;
    const inDur = 1.3;
    const outDur = 1.0;

    // 해당 어노테이션 활성 구간 (진입 0.25초 전 ~ 종료 0.1초 후)
    if (t >= start - 0.25 && t <= end + 0.1) {
      const panel = ann.panel ?? 'price';
      const rect = rects[panel] ?? priceRect;
      if (!rect) continue;

      const cx = scaleX(ann.index!, n, rect);
      let cy = 480;

      if (panel === 'volume' && vy) {
        const v = series.v[ann.index!] ?? 0;
        cy = vy(v);
      } else if (py) {
        const val = valueForPanel('price', series, ann.index!) ?? 0;
        cy = py(val);
      }

      // 목표 줌 배율 (거래량은 1.82배, 캔들/이평선은 1.76배)
      const targetScale = panel === 'volume' ? 1.82 : 1.76;

      // 목표 화면 위치 (1920x1080 기준 화면 상의 가장 편안한 위치)
      // 캔들이 우측에 있으면 화면의 약 68%(1300px)에 배치하여 좌측 콜아웃 카드가 돋보이게 함
      const isRightSide = cx > rect.x + rect.w * 0.6;
      const targetScreenX = isRightSide ? 1320 : cx < rect.x + rect.w * 0.35 ? 620 : 960;

      // Y축 목표 위치: 거래량 패널은 살짝 올려서 520px 중심, 가격 패널은 380px 중심
      const targetScreenY = panel === 'volume' ? 520 : 380;

      let progress = 0; // 0 = 1.0x overview, 1.0 = targetScale zoom

      if (t < start) {
        progress = interpolate(t, [start - 0.25, start], [0, 0.12], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
      } else if (t <= start + inDur) {
        progress = interpolate(t, [start, start + inDur], [0.12, 1.0], {
          easing: Easing.bezier(0.25, 0.1, 0.25, 1),
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
      } else if (t < end - outDur) {
        // 미세 시네마틱 드리프트 (+2% 확대)
        const drift = interpolate(t, [start + inDur, end - outDur], [1.0, 1.025], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
        progress = drift;
      } else {
        // 줌아웃 부드러운 복귀
        progress = interpolate(t, [end - outDur, end], [1.025, 0], {
          easing: Easing.bezier(0.35, 0, 0.2, 1),
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
      }

      const pClamped = Math.max(0, progress);
      const scale = 1.0 + (targetScale - 1.0) * pClamped;

      // 수학적으로 정확한 X, Y 변환:
      // 화면 좌표: x_screen = x * scale + tx
      // 목표 위치 cx_dest = cx + (targetScreenX - cx) * pClamped
      // 따라서 tx = cx_dest - cx * scale
      const cxDest = cx + (targetScreenX - cx) * pClamped;
      const cyDest = cy + (targetScreenY - cy) * pClamped;

      const tx = cxDest - cx * scale;
      const ty = cyDest - cy * scale;

      return { scale, tx, ty };
    }
  }

  return defaultState;
};
