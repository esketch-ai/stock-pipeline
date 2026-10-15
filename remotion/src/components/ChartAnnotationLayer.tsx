import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { C, PAD, VB, stackPanels, type Panel } from '../charts/theme';
import { scaleX, scaleY, type Series } from '../charts/scale';
import { domainForPanel, valueForPanel, PANELS_OF } from '../charts/pointers';
import type { ChartKind } from '../charts';

export type AnnotationTone = 'up' | 'down' | 'accent' | 'purple';

export type ChartAnnotation = {
  id: string;
  from: number; // 시작 시각 (초)
  to: number;   // 종료 시각 (초)
  kind: 'box' | 'pointer' | 'hlevel';
  panel?: Panel;
  index?: number; // 봉 인덱스
  price?: number; // 수평선 가격
  title: string;
  sub?: string;
  tone?: AnnotationTone;
};

const TONE_COLORS: Record<AnnotationTone, string> = {
  up: '#FF3B30',      // 상승/양봉 (Red)
  down: '#0A84FF',    // 하락/윗꼬리 (Blue)
  accent: '#FFD60A',  // 거래량/돌파 (Gold)
  purple: '#BF5AF2',  // 고점/추세 (Purple)
};

export const ChartAnnotationLayer: React.FC<{
  annotations?: ChartAnnotation[];
  series: Series | null;
  chartKind: ChartKind;
  t: number;
  cameraScale?: number;
}> = ({ annotations, series, chartKind, t, cameraScale = 1.0 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  if (!series || !annotations?.length) return null;

  const n = series.c.length;
  if (!n) return null;

  const panels = PANELS_OF[chartKind] ?? PANELS_OF.price;
  const rects = stackPanels(panels);

  const priceDomain = domainForPanel('price', series);
  const volDomain = domainForPanel('volume', series);

  const priceRect = rects.price;
  const volRect = rects.volume;

  const py = priceDomain && priceRect ? scaleY(priceDomain, [priceRect.y + priceRect.h, priceRect.y]) : null;
  const vy = volDomain && volRect ? scaleY(volDomain, [volRect.y + volRect.h, volRect.y]) : null;

  const active = annotations.filter((a) => t >= a.from - 0.1 && t <= a.to + 0.2);
  if (!active.length) return null;

  const pulse = 1 + Math.sin(frame / 4.5) * 0.15;
  const invScale = 1 / (cameraScale || 1.0);

  return (
    <svg
      viewBox={`0 0 ${VB.w} ${VB.h}`}
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 20,
      }}
    >
      <defs>
        <filter id="ann-glow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="card-shadow" x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="6" stdDeviation="12" floodColor="#000000" floodOpacity="0.85" />
        </filter>
      </defs>

      {active.map((ann) => {
        const color = TONE_COLORS[ann.tone ?? 'accent'];
        const localFrame = Math.max(0, (t - ann.from) * fps);
        const appear = spring({
          frame: localFrame,
          fps,
          config: { damping: 16, stiffness: 130 },
        });
        const fadeOut = interpolate(t, [ann.to - 0.4, ann.to], [1, 0], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
        const alpha = Math.min(1, Math.max(0, appear * fadeOut));
        if (alpha <= 0.01) return null;

        // ── 1. 수평 지지선 / 저항선 (hlevel) ──
        if (ann.kind === 'hlevel' && ann.price && py && priceRect) {
          const y = py(ann.price);
          const tagW = 152;
          const tagH = 32;
          const tagX = priceRect.x + priceRect.w + 6;
          const tagY = y - tagH / 2;

          return (
            <g key={ann.id} opacity={alpha}>
              {/* 대시 라인 */}
              <line
                x1={priceRect.x}
                y1={y}
                x2={priceRect.x + priceRect.w}
                y2={y}
                stroke={color}
                strokeWidth={3}
                strokeDasharray="10 6"
                filter="url(#ann-glow)"
              />
              {/* 우측 가격 축 태그 배지 */}
              <rect
                x={tagX}
                y={tagY}
                width={tagW}
                height={tagH}
                rx={6}
                fill={color}
                filter="url(#card-shadow)"
              />
              <text
                x={tagX + tagW / 2}
                y={tagY + 21}
                fill="#FFFFFF"
                fontSize={14}
                fontWeight={900}
                textAnchor="middle"
                fontFamily="SF Mono, Menlo, monospace"
              >
                {ann.title} {ann.price.toLocaleString()}원
              </text>
            </g>
          );
        }

        // ── 2. 하이라이트 박스 (box) ──
        if (ann.kind === 'box' && ann.index !== undefined && ann.index >= 0 && ann.index < n) {
          const targetPanel = ann.panel ?? 'price';
          const rect = rects[targetPanel] ?? priceRect;
          if (!rect) return null;

          const cx = scaleX(ann.index, n, rect);
          const barW = Math.max(32, (rect.w / n) * 4.2);
          const boxX = cx - barW / 2;

          let boxY = rect.y;
          let boxH = rect.h;

          if (targetPanel === 'price' && py) {
            const h = series.h[ann.index] ?? series.c[ann.index] ?? 0;
            const l = series.l[ann.index] ?? series.c[ann.index] ?? 0;
            const yTop = py(h);
            const yBottom = py(l);
            boxH = Math.max(48, yBottom - yTop + 28);
            boxY = yTop - 14;
          } else if (targetPanel === 'volume' && vy && volRect) {
            const v = series.v[ann.index] ?? 0;
            const yTop = vy(v);
            boxY = yTop - 6;
            boxH = Math.max(24, (volRect.y + volRect.h) - yTop + 6);
          }

          // 콜아웃 카드 배치 (좌측 vs 우측)
          const isRightSide = cx > rect.x + rect.w * 0.62;
          const cardW = 380;
          const cardH = 78;
          const cardX = isRightSide ? cx - cardW - 36 : cx + barW / 2 + 36;
          const cardY = Math.min(Math.max(rect.y + 12, boxY - 32), VB.h - cardH - 120);

          const anchorX = isRightSide ? boxX : boxX + barW;
          const anchorY = boxY + boxH * 0.4;
          const targetX = isRightSide ? cardX + cardW : cardX;
          const targetY = cardY + cardH / 2;

          return (
            <g key={ann.id} opacity={alpha}>
              {/* 타겟 캔들/거래량 감싸는 포커스 박스 */}
              <rect
                x={boxX}
                y={boxY}
                width={barW}
                height={boxH}
                rx={8}
                fill={`${color}22`}
                stroke={color}
                strokeWidth={3.5}
                strokeDasharray="8 5"
                filter="url(#ann-glow)"
              />
              {/* 중심 펄스 링 */}
              <circle cx={cx} cy={boxY} r={14 * pulse} fill="none" stroke={color} strokeWidth={2.8} />
              <circle cx={cx} cy={boxY} r={5} fill={color} />

              {/* 지시 연결선 */}
              <path
                d={`M ${anchorX} ${anchorY} Q ${(anchorX + targetX) / 2} ${anchorY} ${targetX} ${targetY}`}
                fill="none"
                stroke={color}
                strokeWidth={2.5}
                strokeDasharray="5 3"
                opacity={0.85}
              />

              {/* 방송용 설명 카드 */}
              <g
                filter="url(#card-shadow)"
                transform={`translate(${targetX}, ${targetY}) scale(${invScale}) translate(${-targetX}, ${-targetY})`}
              >
                <rect
                  x={cardX}
                  y={cardY}
                  width={cardW}
                  height={cardH}
                  rx={12}
                  fill="rgba(11, 18, 32, 0.94)"
                  stroke={color}
                  strokeWidth={2}
                />
                <rect x={cardX} y={cardY} width={7} height={cardH} rx={3} fill={color} />
                <text
                  x={cardX + 22}
                  y={cardY + 32}
                  fill={color}
                  fontSize={18}
                  fontWeight={900}
                  fontFamily="Apple SD Gothic Neo, Pretendard, sans-serif"
                >
                  {ann.title}
                </text>
                {ann.sub && (
                  <text
                    x={cardX + 22}
                    y={cardY + 58}
                    fill="#E2E8F0"
                    fontSize={14}
                    fontWeight={700}
                    fontFamily="Apple SD Gothic Neo, Pretendard, sans-serif"
                  >
                    {ann.sub}
                  </text>
                )}
              </g>
            </g>
          );
        }

        // ── 3. 포인트 포인터 (pointer) ──
        if (ann.kind === 'pointer' && ann.index !== undefined && ann.index >= 0 && ann.index < n) {
          const targetPanel = ann.panel ?? 'price';
          const rect = rects[targetPanel] ?? priceRect;
          if (!rect) return null;

          const cx = scaleX(ann.index, n, rect);
          const val = valueForPanel(targetPanel, series, ann.index);
          const scaleFunc = targetPanel === 'volume' ? vy : py;
          if (!scaleFunc || val === null) return null;

          const cy = scaleFunc(val);

          const isRightSide = cx > rect.x + rect.w * 0.62;
          const cardW = 380;
          const cardH = 78;
          const cardX = isRightSide ? cx - cardW - 36 : cx + 36;
          const cardY = Math.min(Math.max(rect.y + 12, cy - 40), VB.h - cardH - 120);

          const targetX = isRightSide ? cardX + cardW : cardX;
          const targetY = cardY + cardH / 2;

          return (
            <g key={ann.id} opacity={alpha}>
              {/* 펄스 포인터 핀 */}
              <circle cx={cx} cy={cy} r={18 * pulse} fill="none" stroke={color} strokeWidth={3} filter="url(#ann-glow)" />
              <circle cx={cx} cy={cy} r={6} fill={color} />

              {/* 지시 연결선 */}
              <path
                d={`M ${cx} ${cy} Q ${(cx + targetX) / 2} ${cy} ${targetX} ${targetY}`}
                fill="none"
                stroke={color}
                strokeWidth={2.5}
                strokeDasharray="5 3"
                opacity={0.85}
              />

              {/* 방송용 설명 카드 */}
              <g
                filter="url(#card-shadow)"
                transform={`translate(${targetX}, ${targetY}) scale(${invScale}) translate(${-targetX}, ${-targetY})`}
              >
                <rect
                  x={cardX}
                  y={cardY}
                  width={cardW}
                  height={cardH}
                  rx={12}
                  fill="rgba(11, 18, 32, 0.94)"
                  stroke={color}
                  strokeWidth={2}
                />
                <rect x={cardX} y={cardY} width={7} height={cardH} rx={3} fill={color} />
                <text
                  x={cardX + 22}
                  y={cardY + 32}
                  fill={color}
                  fontSize={18}
                  fontWeight={900}
                  fontFamily="Apple SD Gothic Neo, Pretendard, sans-serif"
                >
                  {ann.title}
                </text>
                {ann.sub && (
                  <text
                    x={cardX + 22}
                    y={cardY + 58}
                    fill="#E2E8F0"
                    fontSize={14}
                    fontWeight={700}
                    fontFamily="Apple SD Gothic Neo, Pretendard, sans-serif"
                  >
                    {ann.sub}
                  </text>
                )}
              </g>
            </g>
          );
        }

        return null;
      })}
    </svg>
  );
};
