/**
 * 차트 공통 껍데기 — 패널 배경 · 그리드 · 축 눈금 · 제목.
 *
 * 차트 종류별로 반복되는 부품을 한곳에 모았다.
 * 데이터 그림(캔들/선/막대)은 각 차트가 children 으로 주입한다.
 *
 * 레이아웃은 theme.stackPanels 하나만 쓴다 — 좌표 계산 경로를 하나로 두는 것이
 * 차트와 포인터가 어긋나지 않게 하는 유일한 방법이다.
 */

import React from 'react';
import { interpolate } from 'remotion';
import { C, FONT, PAD, VB, stackPanels, type Panel, type Rect } from './theme';
import { niceTicks, scaleX, type Series } from './scale';

type Props = {
  series: Series;
  panels: Panel[];
  domains: Partial<Record<Panel, [number, number]>>;
  formatters?: Partial<Record<Panel, (v: number) => string>>;
  /** 지금까지 공개된 봉 수 — 축 눈금도 이에 맞춰 움직인다 */
  count: number;
  progress: number;
  title?: string;
  children?: React.ReactNode;
};

const DEFAULT_FMT = (v: number) =>
  Math.abs(v) >= 1000 ? v.toLocaleString('en-US') : String(v);

export const ChartFrame: React.FC<Props> = ({
  series,
  panels,
  domains,
  formatters,
  count,
  progress,
  title,
  children,
}) => {
  const n = series.c.length;
  const rects = React.useMemo(() => stackPanels(panels), [panels.join('|')]);

  // 축/제목은 데이터가 대부분 그려진 뒤에 나타난다
  const chrome = interpolate(progress, [0.5, 0.85], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const panelIn = interpolate(progress, [0, 0.25], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const shown = Math.min(count, n);
  const xIdx = Array.from({ length: 6 }, (_, k) => Math.round((shown - 1) * (k / 5))).filter(
    (i, k, a) => i >= 0 && a.indexOf(i) === k
  );

  return (
    <svg viewBox={`0 0 ${VB.w} ${VB.h}`} width="100%" height="100%">
      {/* 패널 배경 */}
      {panels.map((p) => (
        <rect
          key={`bg-${p}`}
          x={rects[p].x}
          y={rects[p].y}
          width={rects[p].w}
          height={rects[p].h}
          fill={C.panel}
          fillOpacity={0.55 * panelIn}
          rx={6}
        />
      ))}

      {/* 네이버 증권 공식 브랜드 헤더 (상단 좌측) */}
      <g opacity={panelIn}>
        <rect
          x={rects[panels[0]].x + 16}
          y={rects[panels[0]].y + 14}
          width={24}
          height={24}
          rx={4}
          fill="#03C75A"
        />
        <text
          x={rects[panels[0]].x + 28}
          y={rects[panels[0]].y + 31}
          textAnchor="middle"
          fill="#FFFFFF"
          fontSize={15}
          fontWeight={900}
          fontFamily="system-ui, -apple-system, sans-serif"
        >
          N
        </text>
        <text
          x={rects[panels[0]].x + 48}
          y={rects[panels[0]].y + 32}
          fill="#FFFFFF"
          fontSize={18}
          fontWeight={800}
          fontFamily={FONT}
          letterSpacing={0.4}
        >
          NAVER 증권
        </text>
        <text
          x={rects[panels[0]].x + 158}
          y={rects[panels[0]].y + 32}
          fill="#5A667A"
          fontSize={15}
          fontFamily={FONT}
        >
          |
        </text>
        <text
          x={rects[panels[0]].x + 172}
          y={rects[panels[0]].y + 32}
          fill="#A1A7B4"
          fontSize={15}
          fontFamily={FONT}
          fontWeight={600}
        >
          {title ?? '일봉 매물대 차트'}
        </text>
      </g>

      {/* 가로 그리드 + Y 눈금 */}
      {panels.map((p) => {
        const rect = rects[p];
        const domain = domains[p];
        if (!domain) return null;
        const fmt = formatters?.[p] ?? DEFAULT_FMT;
        const ticks = niceTicks(domain[0], domain[1], p === 'volume' ? 2 : 5);
        const y = (v: number) =>
          rect.y + rect.h - ((v - domain[0]) / (domain[1] - domain[0] || 1)) * rect.h;

        return (
          <g key={`grid-${p}`} opacity={chrome}>
            {ticks.map((t) => (
              <g key={`${p}-${t}`}>
                <line
                  x1={rect.x}
                  y1={y(t)}
                  x2={rect.x + rect.w}
                  y2={y(t)}
                  stroke={C.grid}
                  strokeWidth={1.5}
                />
                <text
                  x={rect.x - 12}
                  y={y(t) + 6}
                  textAnchor="end"
                  fill={C.dim}
                  fontSize={18}
                  fontWeight={600}
                  fontFamily={FONT}
                >
                  {fmt(t)}
                </text>
              </g>
            ))}
          </g>
        );
      })}

      {/* 세로 그리드 + 날짜 */}
      <g opacity={chrome}>
        {xIdx.map((i) => {
          const x = scaleX(i, shown, rects[panels[0]]);
          return (
            <g key={`x-${i}`}>
              <line
                x1={x}
                y1={PAD.top}
                x2={x}
                y2={VB.h - PAD.bottom}
                stroke={C.grid}
                strokeWidth={1}
                strokeDasharray="4 10"
                opacity={0.55}
              />
              <text
                x={x}
                y={PAD.dateLabelY}
                textAnchor="middle"
                fill={C.dim}
                fontSize={22}
                fontFamily={FONT}
              >
                {series.d[i]?.slice(5) ?? ''}
              </text>
            </g>
          );
        })}
      </g>

      {/* 데이터 레이어 */}
      {children}

    </svg>
  );
};

/** 자식 차트가 패널 rect 를 얻는 유일한 경로 */
export const usePanels = (panels: Panel[]): Record<Panel, Rect> =>
  React.useMemo(() => stackPanels(panels), [panels.join('|')]);
