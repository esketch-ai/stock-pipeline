/**
 * 기간 누적 수익률 + 거래량.
 *
 * 모션: 영역 채움이 좌→우로 스윕하고(0선 기준 위/아래 색이 갈린다),
 *       거래량 막대가 따라 자라며, 최종 수익률이 스프링으로 튀어 오른다.
 */

import React from 'react';
import { C, FONT, MONO, type Panel } from './theme';
import {
  buildAreaPath,
  buildLinePath,
  easeOutBack,
  easeOutCubic,
  extentOf,
  fmtPct,
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

const PANELS: Panel[] = ['return', 'volume'];
const REVEAL_TAIL = 0.66;

export const ReturnChart: React.FC<{
  series: Series;
  name: string;
  ticker: string;
  progress: number;
}> = ({ series, name, ticker, progress }) => {
  const n = series.c.length;
  const rects = usePanels(PANELS);
  const retRect = rects.return;
  const volRect = rects.volume;

  const count = revealedCount(n, progress, REVEAL_TAIL);
  const ret = series.ret ?? [];

  // 0선을 축 안에 반드시 포함 (누적 수익률은 0을 가로지른다)
  const retRaw = extentOf([ret], count, 0.12);
  const span = Math.max(Math.abs(retRaw[0]), Math.abs(retRaw[1]), 5);
  const domain: [number, number] = [-span, span];

  const ry = scaleY(domain, [retRect.y + retRect.h, retRect.y]);
  const zeroY = ry(0);

  const volRaw = extentOf([series.v], count, 0.1);
  const volDomain: [number, number] = [0, Math.max(volRaw[1], 1)];
  const vy = scaleY(volDomain, [volRect.y + volRect.h, volRect.y]);

  // 스윕: 영역이 채워지는 폭을 키운다
  const sweep = easeOutCubic(segment(progress, 0.12, 0.55));
  const sweepCount = Math.max(2, Math.round(count * sweep));
  const lastX = scaleX(Math.max(0, sweepCount - 1), n, retRect);

  const line = buildLinePath(ret, sweepCount, retRect, ry);
  const area = buildAreaPath(ret, sweepCount, retRect, ry, zeroY);
  const posColor = (ret[Math.min(count, n) - 1] ?? 0) >= 0 ? C.up : C.down;

  // 최종 수익률 배지 — 스프링으로 튀어 오른다
  const badgeT = easeOutBack(segment(progress, 0.7, 0.3));
  const lastRet = ret[Math.min(count, n) - 1];

  const band = retRect.w / n;
  const cw = Math.max(2, band * 0.62);

  return (
    <ChartFrame
      series={series}
      panels={PANELS}
      domains={{ return: domain, volume: volDomain }}
      formatters={{ return: fmtPct, volume: fmtVolume }}
      count={count}
      progress={progress}
    >
      <defs>
        <clipPath id="sweep-clip">
          <rect x={retRect.x} y={retRect.y} width={lastX - retRect.x} height={retRect.h} />
        </clipPath>
      </defs>

      {/* 수익률 영역 */}
      <g clipPath="url(#sweep-clip)">
        <path d={area} fill={posColor} opacity={0.18} />
        <path d={line} fill="none" stroke={posColor} strokeWidth={3.4} strokeLinejoin="round" />
        <line
          x1={retRect.x}
          y1={zeroY}
          x2={retRect.x + retRect.w}
          y2={zeroY}
          stroke={C.dim}
          strokeWidth={2}
        />
        <text x={retRect.x + 14} y={zeroY - 14} fill={C.dim} fontSize={22} fontFamily={FONT}>
          0%
        </text>
      </g>

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
            opacity={0.55}
            rx={1}
          />
        );
      })}

      {/* 최종 수익률 배지 */}
      {num(lastRet) && badgeT > 0 && (
        <g opacity={Math.min(1, badgeT)}>
          <rect
            x={retRect.x + retRect.w + 8}
            y={ry(lastRet) - 28}
            width={140}
            height={56}
            fill={posColor}
            rx={8}
            transform={`translate(${retRect.x + retRect.w + 70}, ${ry(lastRet)}) scale(${badgeT}) translate(${
              -(retRect.x + retRect.w + 70)
            }, ${-ry(lastRet)})`}
          />
          <text
            x={retRect.x + retRect.w + 78}
            y={ry(lastRet) + 10}
            textAnchor="middle"
            fill="#0B1220"
            fontSize={27}
            fontWeight={800}
            fontFamily={MONO}
          >
            {fmtPct(lastRet * Math.min(1, badgeT))}
          </text>
        </g>
      )}
    </ChartFrame>
  );
};
