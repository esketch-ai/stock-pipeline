/**
 * 캔들 + 거래량.
 *
 * 모션: 봉이 좌→우로 하나씩 솟고(overshoot), 거래량 막대가 아래에서 자란다.
 *       Y축 범위가 공개된 봉만 보고 매 프레임 다시 잡히므로 축이 함께 벌어진다.
 */

import React from 'react';
import { C, MONO, type Panel } from './theme';
import {
  buildLinePath,
  easeOutBack,
  easeOutCubic,
  extentOf,
  fmtPrice,
  fmtVolume,
  num,
  periodLabel,
  revealedCount,
  scaleX,
  scaleY,
  segment,
  stagger,
  type Series,
} from './scale';
import { ChartFrame, usePanels } from './ChartFrame';

const PANELS: Panel[] = ['price', 'volume'];
const REVEAL_TAIL = 0.7;
const TAG_W = 140;

export const CandleChart: React.FC<{
  series: Series;
  name: string;
  ticker: string;
  progress: number;
}> = ({ series, name, ticker, progress }) => {
  const n = series.c.length;
  const rects = usePanels(PANELS);
  const count = revealedCount(n, progress, REVEAL_TAIL);

  const priceRect = rects.price;
  const volRect = rects.volume;

  // Y축은 '지금까지 공개된 봉'만 보고 매 프레임 다시 계산된다.
  const priceDomain = extentOf([series.h, series.l], count, 0.08);
  const volRaw = extentOf([series.v], count, 0.1);
  const volDomain: [number, number] = [0, Math.max(volRaw[1], 1)];

  const py = scaleY(priceDomain, [priceRect.y + priceRect.h, priceRect.y]);
  const vy = scaleY(volDomain, [volRect.y + volRect.h, volRect.y]);

  const band = priceRect.w / n;
  const cw = Math.max(2, band * 0.62);

  const closeLine = buildLinePath(series.c, count, priceRect, py);

  // 마지막 가격 태그 — 첫 가격에서 마지막 가격으로 카운트업
  const last = Math.min(count, n) - 1;
  const firstClose = num(series.c[0]) ? (series.c[0] as number) : null;
  const lastClose = num(series.c[last]) ? (series.c[last] as number) : null;
  const tagIn = segment(progress, 0.74, 0.24);
  const shownPrice =
    firstClose !== null && lastClose !== null
      ? firstClose + (lastClose - firstClose) * easeOutCubic(tagIn)
      : lastClose;

  // VFX 효과: 파티클 및 빛 효과 추가
  const particles = Array.from({ length: Math.floor(count / 2) }, (_, i) => {
    const x = scaleX(i * 2, n, priceRect);
    const y = py(series.c[i * 2] ?? 0);
    
    // 파티클 애니메이션 (점점 커졌다 사라지는 효과)
    const particleOpacity = easeOutCubic(segment(progress, i * 0.2, 0.5));
    const scale = 1 + Math.sin(progress * 3 + i) * 0.5;
    
    // 캔들 뿌옇게 빛나는 효과
    const glowIntensity = Math.sin(progress * 2 + i) > 0 ? 0.4 : 0.8;
    
    return (
      <circle
        key={`particle${i}`}
        cx={x}
        cy={y}
        r={1 + particleOpacity * 3}
        fill={C.up}
        opacity={particleOpacity * 0.6}
        transform={`scale(${scale})`}
      />
    );
  });

  const glowEffect = (
    <filter id="glow">
      <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
      <feMerge> 
        <feMergeNode in="coloredBlur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  );

  return (
    <ChartFrame
      series={series}
      panels={PANELS}
      domains={{ price: priceDomain, volume: volDomain }}
      formatters={{ price: fmtPrice, volume: fmtVolume }}
      count={count}
      progress={progress}
    >
      {/* 거래량 막대 */}
      {Array.from({ length: count }, (_, i) => {
        const v = series.v[i];
        if (!num(v)) return null;
        const g = easeOutBack(stagger(progress, i, n, REVEAL_TAIL, 0.05));
        const x = scaleX(i, n, volRect);
        const h = Math.max(1, (volRect.y + volRect.h - vy(v)) * g);
        const up = (series.c[i] ?? 0) >= (series.o[i] ?? 0);
        return (
          <rect
            key={`v${i}`}
            x={x - cw / 2}
            y={volRect.y + volRect.h - h}
            width={cw}
            height={h}
            fill={up ? C.up : C.down}
            opacity={0.6}
            rx={1}
          />
        );
      })}

      {/* 캔들 — 몸통이 가운데에서 세로로 자란다 */}
      {Array.from({ length: count }, (_, i) => {
        const o = series.o[i];
        const h = series.h[i];
        const l = series.l[i];
        const c = series.c[i];
        if (!num(o) || !num(h) || !num(l) || !num(c)) return null;

        const g = easeOutBack(stagger(progress, i, n, REVEAL_TAIL, 0.05));
        const x = scaleX(i, n, priceRect);
        const up = c >= o;
        const color = up ? C.up : C.down;

        const yH = py(h);
        const yL = py(l);
        const mid = (yH + yL) / 2;
        const half = Math.abs(py(c) - py(o)) / 2;

        const bodyH = Math.max(2, half * 2 * g);
        return (
          <g key={`c${i}`} opacity={Math.min(1, g * 1.6)}>
            <line
              x1={x}
              y1={yH}
              x2={x}
              y2={yL}
              stroke={color}
              strokeWidth={Math.max(1.5, cw * 0.14)}
            />
            <rect
              x={x - cw / 2}
              y={mid - bodyH / 2}
              width={cw}
              height={bodyH}
              fill={up ? C.up : C.down}
              stroke={color}
              strokeWidth={1.5}
              rx={1}
              filter="url(#glow)"
            />
          </g>
        );
      })}

      {/* VFX 파티클 효과 */}
      {particles}

      {/* 종가 추세선 — 캔들이 다 나온 뒤 겹쳐 그린다 */}
      <path
        d={closeLine}
        fill="none"
        stroke={C.accent}
        strokeWidth={3}
        opacity={0.7 * segment(progress, 0.55, 0.35)}
        strokeLinejoin="round"
      />

      {/* 마지막 가격 태그 */}
      {shownPrice !== null && tagIn > 0 && (
        <g opacity={tagIn}>
          <rect
            x={priceRect.x + priceRect.w + 8}
            y={py(shownPrice) - 26}
            width={TAG_W}
            height={52}
            fill={C.accent}
            rx={6}
          />
          <text
            x={priceRect.x + priceRect.w + 8 + TAG_W / 2}
            y={py(shownPrice) + 9}
            textAnchor="middle"
            fill="#0B1220"
            fontSize={26}
            fontWeight={800}
            fontFamily={MONO}
          >
            {fmtPrice(shownPrice)}
          </text>
        </g>
      )}
    </ChartFrame>
  );
};
