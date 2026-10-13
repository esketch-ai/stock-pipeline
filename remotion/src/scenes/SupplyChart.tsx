/**
 * 수급 차트 — 투자자별 순매수(기관/개인/외국인).
 *
 * 참고 영상이 가장 오래 붙잡던 화면이 이거다 ("누가 왜 움직였는가").
 * 누적 순매수 곡선 3개 + 0선 위아래로 채워 그린다.
 */

import React from 'react';
import { interpolate } from 'remotion';
import { C, FONT, MONO, PAD, VB, stackPanels, type Panel } from '../charts/theme';
import { buildLinePath, easeOutCubic, num, scaleX, scaleY } from '../charts/scale';
import { ChartFrame } from '../charts/ChartFrame';

export type Supply = {
  d: string[];
  institution: number[];
  retail: number[];
  foreign: number[];
  other?: number[];
};

const PANELS: Panel[] = ['volume']; // 아래 stackPanels 재사용용 (supply 패널은 1개)

const SERIES = [
  { key: 'retail' as const, label: '개인', color: '#FFD60A' },
  { key: 'foreign' as const, label: '외국인', color: '#0A84FF' },
  { key: 'institution' as const, label: '기관', color: '#BF5AF2' },
];

export const SupplyChart: React.FC<{ supply: Supply; progress: number }> = ({
  supply,
  progress,
}) => {
  const n = supply.d.length;
  if (!n) return null;

  // 누적 합계 — "이 기간에 누가 얼마나 쥐고 있는가"
  const cum = (key: 'institution' | 'retail' | 'foreign'): number[] => {
    let acc = 0;
    return (supply[key] || []).map((v) => (acc += num(v) ? v : 0));
  };
  const lines = SERIES.map((s) => ({ ...s, values: cum(s.key) }));

  let lo = 0;
  let hi = 0;
  for (const l of lines) for (const v of l.values) { if (v < lo) lo = v; if (v > hi) hi = v; }
  const pad = (hi - lo) * 0.12 || 1;
  const domain: [number, number] = [lo - pad, hi + pad];

  const rect = stackPanels(PANELS).volume;
  const y = scaleY(domain, [rect.y + rect.h, rect.y]);

  const draw = easeOutCubic(interpolate(progress, [0.05, 0.75], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  }));
  const shown = Math.max(2, Math.round(n * draw));

  // 누적 합계 = 개별 막대를 더한 값 → 막대가 쌓이는 면적도 알 수 있다
  const totals = SERIES.map((s) => ({
    ...s,
    total: (supply[s.key] || []).reduce((a, b) => a + (num(b) ? b : 0), 0),
  }));

  const zeroY = y(0);
  const legendY = rect.y - 26;

  return (
    <ChartFrame
      series={{ d: supply.d, c: lines[0].values, o: [], h: [], l: [], v: [] }}
      panels={PANELS}
      domains={{ volume: domain }}
      formatters={{ volume: (v) => `${v >= 0 ? '' : ''}${v.toFixed(0)}억` }}
      count={shown}
      progress={progress}
    >
      {/* 0선 — 누적 수급의 분기점 */}
      <line
        x1={rect.x}
        y1={zeroY}
        x2={rect.x + rect.w}
        y2={zeroY}
        stroke={C.dim}
        strokeWidth={1.6}
        opacity={0.7}
      />
      <text x={rect.x + 10} y={zeroY - 12} fill={C.dim} fontSize={20} fontFamily={FONT}>
        0
      </text>

      {/* 누적 순매수 곡선 */}
      {lines.map((l, i) => {
        const d = buildLinePath(l.values, shown, rect, y);
        if (!d) return null;
        const t = interpolate(progress, [0.25 + i * 0.14, 0.55 + i * 0.14], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
        return (
          <g key={l.key} opacity={t}>
            <path d={d} fill="none" stroke={l.color} strokeWidth={3.6} strokeLinejoin="round" />
          </g>
        );
      })}

      {/* 끝값 라벨 — 라벨/색만. 박스 없음 */}
      {lines.map((l) => {
        const v = l.values[shown - 1];
        if (!num(v)) return null;
        return (
          <g key={`end-${l.key}`} opacity={interpolate(progress, [0.7, 0.85], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })}>
            <circle cx={scaleX(shown - 1, n, rect)} cy={y(v)} r={7} fill={l.color} />
            <text
              x={scaleX(shown - 1, n, rect) + 16}
              y={y(v) + 8}
              fill={l.color}
              fontSize={26}
              fontWeight={800}
              fontFamily={MONO}
            >
              {v >= 0 ? '+' : ''}
              {v.toFixed(1)}억
            </text>
          </g>
        );
      })}

      {/* 범례 — 위쪽, 나열만 */}
      <g opacity={interpolate(progress, [0.35, 0.6], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })}>
        {totals.map((t, i) => (
          <g key={t.key} transform={`translate(${rect.x + i * 300}, ${legendY})`}>
            <line x1={0} y1={0} x2={46} y2={0} stroke={t.color} strokeWidth={5} />
            <text x={60} y={9} fill={C.fg} fontSize={26} fontWeight={700} fontFamily={FONT}>
              {t.label}
            </text>
            <text
              x={60 + 62}
              y={9}
              fill={t.total >= 0 ? '#FF453A' : '#0A84FF'}
              fontSize={26}
              fontWeight={800}
              fontFamily={MONO}
            >
              {t.total >= 0 ? '+' : ''}
              {t.total.toFixed(1)}억
            </text>
          </g>
        ))}
      </g>
    </ChartFrame>
  );
};

void VB;
void PAD;
