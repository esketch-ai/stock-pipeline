/**
 * 종가 + 이동평균 (5 / 20 / 60).
 *
 * 모션: 종가선을 먼저 긋고, MA 60 → 20 → 5 순으로 긴 기간부터 그린다.
 *       선이 완성될 때마다 오른쪽 위 범례가 하나씩 나타난다.
 */

import React from 'react';
import { C, FONT, type Panel } from './theme';
import {
  buildLinePath,
  extentOf,
  fmtPrice,
  num,
  periodLabel,
  revealedCount,
  scaleY,
  segment,
  type Series,
} from './scale';
import { ChartFrame, usePanels } from './ChartFrame';

const PANELS: Panel[] = ['price'];
const REVEAL_TAIL = 0.72;

type LineDef = {
  key: string;
  label: string;
  values: (number | null)[];
  color: string;
  width: number;
  /** 그리기 시작 시각과 길이 */
  start: number;
  dur: number;
};

export const TrendChart: React.FC<{
  series: Series;
  name: string;
  ticker: string;
  progress: number;
}> = ({ series, name, ticker, progress }) => {
  const n = series.c.length;
  const rects = usePanels(PANELS);
  const rect = rects.price;
  const count = revealedCount(n, progress, REVEAL_TAIL);

  const lines: LineDef[] = [
    { key: 'close', label: '종가', values: series.c, color: C.accent, width: 3.5, start: 0.1, dur: 0.45 },
    { key: 'ma120', label: '120일', values: series.ma120 ?? [], color: '#BF5AF2', width: 2.2, start: 0.22, dur: 0.35 },
    { key: 'ma60', label: '60일', values: series.ma60 ?? [], color: '#0A84FF', width: 2.2, start: 0.34, dur: 0.34 },
    { key: 'ma20', label: '20일', values: series.ma20 ?? [], color: '#FF9500', width: 2.5, start: 0.48, dur: 0.32 },
    { key: 'ma5', label: '5일', values: series.ma5 ?? [], color: '#FF3B30', width: 2.5, start: 0.6, dur: 0.3 },
  ];

  const domain = extentOf(
    [series.c, series.ma5 ?? [], series.ma20 ?? [], series.ma60 ?? [], series.ma120 ?? []],
    count,
    0.08
  );
  const y = scaleY(domain, [rect.y + rect.h, rect.y]);

  // 드로잉 진행률만큼 경로만 잘라 그린다 (stroke-dasharray 없이 정확히 잘림)
  const drawnPath = (values: (number | null)[], t: number) => {
    if (t <= 0) return '';
    const upto = Math.max(2, Math.round(count * t));
    return buildLinePath(values, upto, rect, y);
  };

  const legend = lines.filter((l) => l.values.some(num));
  const lx = rect.x + 24;
  const ly = rect.y + 34;

  return (
    <ChartFrame
      series={series}
      panels={PANELS}
      domains={{ price: domain }}
      formatters={{ price: fmtPrice }}
      count={count}
      progress={progress}
      title="이동평균선 추세 분석"
    >
      {lines.map((l) => {
        const t = segment(progress, l.start, l.dur);
        const d = drawnPath(l.values, t);
        if (!d) return null;
        return (
          <path
            key={l.key}
            d={d}
            fill="none"
            stroke={l.color}
            strokeWidth={l.width}
            strokeLinejoin="round"
            strokeLinecap="round"
            opacity={0.95}
          />
        );
      })}

      {/* 범례 — 각 선이 완성될 때 하나씩 나타난다 */}
      {legend.map((l, k) => {
        const t = segment(progress, l.start + l.dur * 0.85, 0.1);
        if (t <= 0) return null;
        return (
          <g key={`lg-${l.key}`} opacity={t}>
            <rect x={lx + k * 190} y={ly - 20} width={172} height={40} rx={6} fill={C.panel} opacity={0.8} />
            <line
              x1={lx + k * 190 + 14}
              y1={ly}
              x2={lx + k * 190 + 52}
              y2={ly}
              stroke={l.color}
              strokeWidth={4}
            />
            <text x={lx + k * 190 + 64} y={ly + 9} fill={C.fg} fontSize={24} fontFamily={FONT}>
              {l.label}
            </text>
          </g>
        );
      })}
    </ChartFrame>
  );
};
