/**
 * 가격(상단) + RSI(하단).
 *
 * 모션: 과매수/과매도 존이 먼저 스윕되고, 가격선이 그려진 뒤
 *       RSI 선이 축에서 밀려 나오며 기준선(70/30)이 자리를 잡는다.
 */

import React from 'react';
import { C, FONT, MONO, type Panel } from './theme';
import {
  buildAreaPath,
  buildLinePath,
  easeOutCubic,
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

const PANELS: Panel[] = ['price', 'rsi'];
const REVEAL_TAIL = 0.66;
const RSI_DOMAIN: [number, number] = [0, 100];

export const MomentumChart: React.FC<{
  series: Series;
  name: string;
  ticker: string;
  progress: number;
}> = ({ series, name, ticker, progress }) => {
  const n = series.c.length;
  const rects = usePanels(PANELS);
  const priceRect = rects.price;
  const rsiRect = rects.rsi;

  const count = revealedCount(n, progress, REVEAL_TAIL);
  const rsi = series.rsi ?? [];

  const priceDomain = extentOf([series.c], count, 0.08);
  const py = scaleY(priceDomain, [priceRect.y + priceRect.h, priceRect.y]);
  const ry = scaleY(RSI_DOMAIN, [rsiRect.y + rsiRect.h, rsiRect.y]);

  const priceLine = buildLinePath(series.c, count, priceRect, py);
  const rsiDraw = segment(progress, 0.3, 0.5);
  const rsiPath = buildLinePath(rsi, Math.max(2, Math.round(count * rsiDraw)), rsiRect, ry);

  // 과매수/과매도 존 — 좌→우 스윕
  const bandSweep = easeOutCubic(segment(progress, 0.06, 0.4));
  const bandW = rsiRect.w * bandSweep;

  // RSI 영역 절반을 색칠하기 위한 경로 (선은 별도)
  const rsiArea = buildAreaPath(
    rsi,
    Math.max(2, Math.round(count * rsiDraw)),
    rsiRect,
    ry,
    rsiRect.y + rsiRect.h
  );

  return (
    <ChartFrame
      series={series}
      panels={PANELS}
      domains={{ price: priceDomain, rsi: RSI_DOMAIN }}
      formatters={{ price: fmtPrice }}
      count={count}
      progress={progress}
    >
      {/* 가격 영역 채움 */}
      <path
        d={buildAreaPath(series.c, count, priceRect, py, priceRect.y + priceRect.h)}
        fill={C.accent}
        opacity={0.08 * bandSweep}
      />
      <path d={priceLine} fill="none" stroke={C.accent} strokeWidth={3} opacity={0.95} />

      {/* RSI 과매수 / 과매도 존 */}
      <g opacity={0.9 * bandSweep}>
        <rect
          x={rsiRect.x}
          y={ry(100)}
          width={bandW}
          height={Math.max(0, ry(70) - ry(100))}
          fill={C.up}
          opacity={0.22}
        />
        <rect
          x={rsiRect.x}
          y={ry(30)}
          width={bandW}
          height={Math.max(0, ry(0) - ry(30))}
          fill={C.down}
          opacity={0.22}
        />
      </g>

      {/* 기준선 — 좌→우로 밀려온다 */}
      <g opacity={bandSweep}>
        {[70, 30].map((lv) => (
          <g key={lv}>
            <line
              x1={rsiRect.x}
              y1={ry(lv)}
              x2={rsiRect.x + bandW}
              y2={ry(lv)}
              stroke={lv === 70 ? C.up : C.down}
              strokeWidth={2}
              strokeDasharray="10 8"
            />
            <text
              x={rsiRect.x + bandW - 10}
              y={ry(lv) - 10}
              textAnchor="end"
              fill={C.dim}
              fontSize={22}
              fontFamily={FONT}
            >
              {lv === 70 ? '과매수 70' : '과매도 30'}
            </text>
          </g>
        ))}
      </g>

      {/* RSI 선 */}
      {rsiPath && <path d={rsiPath} fill="none" stroke={C.purple} strokeWidth={3.2} strokeLinejoin="round" />}
      {rsiArea && <path d={rsiArea} fill={C.purple} opacity={0.12} />}

      {/* 현재 RSI 수치 */}
      {(() => {
        const t = segment(progress, 0.72, 0.24);
        if (t <= 0) return null;
        const lastIdx = Math.min(count, rsi.length) - 1;
        const v = rsi[lastIdx];
        if (!num(v)) return null;
        const shown = v * easeOutCubic(t);
        return (
          <g opacity={t}>
            <rect
              x={rsiRect.x + rsiRect.w + 8}
              y={ry(shown) - 24}
              width={120}
              height={48}
              fill={shown >= 70 ? C.up : shown <= 30 ? C.down : C.purple}
              rx={6}
            />
            <text
              x={rsiRect.x + rsiRect.w + 68}
              y={ry(shown) + 9}
              textAnchor="middle"
              fill="#0B1220"
              fontSize={25}
              fontWeight={800}
              fontFamily={MONO}
            >
              {shown.toFixed(1)}
            </text>
          </g>
        );
      })()}
    </ChartFrame>
  );
};
