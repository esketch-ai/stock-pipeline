import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig, Easing } from 'remotion';
import { C, PAD, VB, stackPanels, type Panel, type Rect } from '../charts/theme';
import { scaleX, scaleY, type Series } from '../charts/scale';
import { domainForPanel, valueForPanel, PANELS_OF } from '../charts/pointers';
import type { ChartKind } from '../charts';

export type AnnotationTone = 'up' | 'down' | 'accent' | 'purple' | 'cyan' | 'green';

export type AnnotationKind = 'box' | 'pointer' | 'hlevel' | 'circle' | 'underline' | 'trendline';

export type ChartAnnotation = {
  id: string;
  from: number;          // 시작 시각 (초)
  to: number;            // 종료 시각 (초)
  kind: AnnotationKind;  // 어노테이션 종류
  panel?: Panel;
  index?: number;        // 시작 봉 인덱스
  endIndex?: number;     // 끝 봉 인덱스 (추세선, 밑줄)
  price?: number;        // 시작 가격 (수평선, 추세선 시작가, 밑줄 가격)
  endPrice?: number;     // 끝 가격 (추세선 끝가)
  title: string;
  sub?: string;
  tone?: AnnotationTone;
  drawDuration?: number; // 그리기 애니메이션 지속 시간 (초, 기본 0.5초)
  eraseDuration?: number;// 지우기 애니메이션 지속 시간 (초, 기본 0.4초)
};

const TONE_COLORS: Record<AnnotationTone, string> = {
  up: '#FF3B30',      // 상승/양봉 (Red)
  down: '#0A84FF',    // 하락/윗꼬리 (Blue)
  accent: '#FFD60A',  // 거래량/돌파 (Gold)
  purple: '#BF5AF2',  // 고점/추세 (Purple)
  cyan: '#00F0FF',    // 지지선/신호 (Neon Cyan)
  green: '#30D158',   // 성공/안착 (Green)
};

const isBrightColor = (c: string): boolean => {
  const lower = (c || '').toLowerCase();
  return (
    lower.includes('ffd6') ||
    lower.includes('ff95') ||
    lower.includes('ffd7') ||
    lower.includes('ffff') ||
    lower === '#ffd60a' ||
    lower === '#ff9500' ||
    lower === '#00f0ff' ||
    lower === '#30d158'
  );
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

  // 현재 활성화된 어노테이션 필터링 (from 직전 ~ to 직후)
  const active = annotations.filter((a) => t >= a.from - 0.1 && t <= a.to + 0.2);
  if (!active.length) return null;

  const pulse = 1 + Math.sin(frame / 4.5) * 0.15;
  const invScale = 1 / (cameraScale || 1.0);

  // 챠트 상단·하단 빈 공백 공간(Clean Shelves)에 설명 카드를 배치하여 캔들 가림을 원천 방지
  const getShelfPlacement = (
    targetXCenter: number,
    targetYTop: number,
    targetYBottom: number,
    rect: Rect,
    isVolumePanel = false
  ) => {
    const cardW = 380;
    const cardH = 68;

    // 배치 결정:
    // 1) 볼륨 패널이면 볼륨 상단 쉘프에 배치
    // 2) 타깃 캔들이 최상단(52주 최고점 등 targetYTop < rect.y + 140)이거나
    //    타깃이 4-MA 범례 아래인 우측 영역(targetXCenter > rect.x + rect.w - 560 = 1190)에 위치할 때는
    //    우측 하단 클린 쉘프(rect.y + rect.h - cardH - 14)에 배치하여 지시선이 화면을 가로지르지 않게 함
    // 3) 그 외(좌측/중앙의 캔들)는 상단 클린 쉘프(rect.y + 14)에 배치
    const isRightNearMa = targetXCenter > rect.x + rect.w - 580;
    const isUpper = !isVolumePanel && targetYTop >= rect.y + 140 && !isRightNearMa;

    let cardY = 0;
    let cardX = 0;

    if (isUpper) {
      // 상단 클린 쉘프: rect.y + 14 (189px ~ 257px 영역)
      // 캔들 최상단이 260px 이하이므로 캔들과 100% 비접촉
      cardY = rect.y + 14;
      // 좌측 네이버 증권 브랜드 로고(x ~ 330) 우측 및 우측 4-MA 범례(x >= 1190) 좌측 클린 공간
      const minX = Math.round(rect.x + 235); // 105 + 235 = 340px
      const maxX = Math.round(rect.x + rect.w - 565 - cardW); // 1750 - 565 - 380 = 805px
      cardX = Math.max(minX, Math.min(maxX, Math.round(targetXCenter - cardW / 2)));
    } else {
      // 하단 클린 쉘프: 캔들 하단 또는 볼륨 패널 헤드룸
      if (isVolumePanel) {
        cardY = rect.y + 10;
        cardX = Math.max(rect.x + 24, Math.min(rect.x + rect.w - cardW - 24, Math.round(targetXCenter - cardW / 2)));
      } else {
        cardY = rect.y + rect.h - cardH - 14;
        cardX = Math.max(rect.x + 24, Math.min(rect.x + rect.w - cardW - 24, Math.round(targetXCenter - cardW / 2)));
      }
    }

    const anchorX = targetXCenter;
    const anchorY = isUpper ? targetYTop : targetYBottom;
    const lineTargetX = Math.max(cardX + 36, Math.min(cardX + cardW - 36, targetXCenter));
    const lineTargetY = isUpper ? cardY + cardH : cardY;

    return {
      cardX,
      cardY,
      cardW,
      cardH,
      targetX: lineTargetX,
      targetY: lineTargetY,
      anchorX,
      anchorY,
      isUpper,
    };
  };

  // 공통 콜아웃 설명 카드 렌더러 (고대비 솔리드 다크 배경으로 뒤 챠트 투과 왜곡 차단)
  const renderCalloutCard = (
    ann: ChartAnnotation,
    color: string,
    targetX: number,
    targetY: number,
    cardX: number,
    cardY: number,
    cardW: number,
    cardH: number,
    cardAlpha: number
  ) => {
    if (cardAlpha <= 0.01) return null;
    return (
      <g
        key={`${ann.id}-card`}
        opacity={cardAlpha}
        filter="url(#card-shadow)"
        transform={`translate(${targetX}, ${targetY}) scale(${invScale}) translate(${-targetX}, ${-targetY})`}
      >
        <rect
          x={cardX}
          y={cardY}
          width={cardW}
          height={cardH}
          rx={10}
          fill="rgba(11, 18, 32, 0.94)"
          stroke={color}
          strokeWidth={1.8}
        />
        <rect x={cardX} y={cardY} width={6} height={cardH} rx={3} fill={color} />
        <text
          x={cardX + 20}
          y={cardY + 28}
          fill={color}
          fontSize={16}
          fontWeight={900}
          fontFamily="Apple SD Gothic Neo, Pretendard, sans-serif"
        >
          {ann.title}
        </text>
        {ann.sub && (
          <text
            x={cardX + 20}
            y={cardY + 50}
            fill="#E2E8F0"
            fontSize={13}
            fontWeight={700}
            fontFamily="Apple SD Gothic Neo, Pretendard, sans-serif"
          >
            {ann.sub}
          </text>
        )}
      </g>
    );
  };

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
        <filter id="ann-glow" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="card-shadow" x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="6" stdDeviation="12" floodColor="#000000" floodOpacity="0.85" />
        </filter>
        <marker
          id="trend-arrow"
          markerWidth="8"
          markerHeight="8"
          refX="6"
          refY="4"
          orient="auto"
        >
          <path d="M 0 0 L 8 4 L 0 8 z" fill="#FFD60A" />
        </marker>
      </defs>

      {active.map((ann) => {
        const color = TONE_COLORS[ann.tone ?? 'accent'];
        const drawDur = ann.drawDuration ?? 0.55;
        const eraseDur = ann.eraseDuration ?? 0.4;

        // 드로잉 진행률 (0 -> 1)
        const drawProgress = interpolate(t, [ann.from, ann.from + drawDur], [0, 1], {
          easing: Easing.bezier(0.16, 1, 0.3, 1),
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });

        // 지우기 진행률 (0 -> 1: 종료 직전 eraseDur 동안 진행)
        const eraseProgress = interpolate(t, [ann.to - eraseDur, ann.to], [0, 1], {
          easing: Easing.bezier(0.35, 0, 0.2, 1),
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });

        // 전체 가시 투명도
        const enterAlpha = interpolate(t, [ann.from, ann.from + 0.12], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
        const alpha = Math.min(1, Math.max(0, enterAlpha * (1 - eraseProgress)));
        if (alpha <= 0.01) return null;

        const targetPanel = ann.panel ?? 'price';
        const rect = rects[targetPanel] ?? priceRect;
        if (!rect) return null;

        // ─────────────────────────────────────────────────────
        // 1. 동그라미 긋기 (circle) — 캔들/구간을 펜으로 쓱 감싸는 타원 드로잉
        // ─────────────────────────────────────────────────────
        if (ann.kind === 'circle' && ann.index !== undefined && ann.index >= 0 && ann.index < n) {
          const cx = scaleX(ann.index, n, rect);
          let cy = rect.y + rect.h / 2;
          let rx = Math.max(34, (rect.w / n) * 3.2);
          let ry = 42;

          if (targetPanel === 'price' && py) {
            const h = series.h[ann.index] ?? series.c[ann.index] ?? 0;
            const l = series.l[ann.index] ?? series.c[ann.index] ?? 0;
            const yTop = py(h);
            const yBottom = py(l);
            cy = (yTop + yBottom) / 2;
            ry = Math.max(36, (yBottom - yTop) / 2 + 18);
          } else if (targetPanel === 'volume' && vy && volRect) {
            const v = series.v[ann.index] ?? 0;
            const yTop = vy(v);
            cy = (yTop + volRect.y + volRect.h) / 2;
            ry = Math.max(26, (volRect.y + volRect.h - yTop) / 2 + 12);
          }

          // 타원 둘레 계산 (Ramanujan 근사)
          const P = Math.PI * (3 * (rx + ry) - Math.sqrt((3 * rx + ry) * (rx + 3 * ry)));
          const strokeOffset = P * (1 - drawProgress);

          // 펜촉 끝점 계산 (상단 -90도에서 시계방향 회전)
          const penAngle = -Math.PI / 2 + 2 * Math.PI * drawProgress;
          const tipX = cx + rx * Math.cos(penAngle);
          const tipY = cy + ry * Math.sin(penAngle);

          // 상·하단 빈 공백 클린 쉘프에 카드 배치 (캔들 가림 원천 방지)
          const shelf = getShelfPlacement(cx, cy - ry, cy + ry, rect, targetPanel === 'volume');

          const cardAlpha = alpha * interpolate(drawProgress, [0.4, 0.85], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });

          return (
            <g key={ann.id} opacity={alpha}>
              {/* 타원 내부 은은한 하이라이트 채우기 */}
              <ellipse
                cx={cx}
                cy={cy}
                rx={rx}
                ry={ry}
                fill={`${color}18`}
                opacity={drawProgress}
              />

              {/* 펜으로 쓱 그리는 타원 스트로크 패스 */}
              <path
                d={`M ${cx} ${cy - ry} A ${rx} ${ry} 0 1 1 ${cx - 0.01} ${cy - ry}`}
                fill="none"
                stroke={color}
                strokeWidth={4.5}
                strokeDasharray={`${P}`}
                strokeDashoffset={`${strokeOffset}`}
                strokeLinecap="round"
                filter="url(#ann-glow)"
              />

              {/* 그리는 도중 끝점에서 빛나는 펜촉 불꽃 */}
              {drawProgress > 0 && drawProgress < 0.99 && (
                <g filter="url(#ann-glow)">
                  <circle cx={tipX} cy={tipY} r={7} fill="#FFFFFF" />
                  <circle cx={tipX} cy={tipY} r={12} fill="none" stroke={color} strokeWidth={2.5} />
                </g>
              )}

              {/* 콜아웃 지시선 (타깃 캔들과 상단/하단 빈 공백 카드를 우아하게 연결) */}
              {cardAlpha > 0.05 && (
                <g opacity={cardAlpha}>
                  <path
                    d={`M ${shelf.anchorX} ${shelf.anchorY} Q ${(shelf.anchorX + shelf.targetX) / 2} ${(shelf.anchorY + shelf.targetY) / 2} ${shelf.targetX} ${shelf.targetY}`}
                    fill="none"
                    stroke={color}
                    strokeWidth={2.2}
                    strokeDasharray="5 3"
                    opacity={0.85}
                  />
                  <circle cx={shelf.targetX} cy={shelf.targetY} r={3.5} fill={color} />
                </g>
              )}

              {/* 방송용 설명 카드 */}
              {renderCalloutCard(ann, color, shelf.targetX, shelf.targetY, shelf.cardX, shelf.cardY, shelf.cardW, shelf.cardH, cardAlpha)}
            </g>
          );
        }

        // ─────────────────────────────────────────────────────
        // 2. 밑줄 긋기 (underline) — 지지선/가격대 하단에 좌->우로 쓱 긋는 밑줄
        // ─────────────────────────────────────────────────────
        if (ann.kind === 'underline') {
          const startIndex = ann.index ?? 0;
          const endIndex = ann.endIndex ?? Math.min(n - 1, startIndex + 6);
          const xStart = scaleX(startIndex, n, rect) - 16;
          const xEnd = scaleX(endIndex, n, rect) + 16;
          const totalW = Math.max(80, xEnd - xStart);
          const currentW = totalW * drawProgress;

          let y = rect.y + rect.h - 20;
          if (ann.price && py) {
            y = py(ann.price) + 8;
          } else if (py && startIndex >= 0 && startIndex < n) {
            const l = series.l[startIndex] ?? series.c[startIndex] ?? 0;
            y = py(l) + 14;
          }

          const currentTipX = xStart + currentW;
          const badgeW = Math.min(340, ann.title.length * 15 + 36);

          return (
            <g key={ann.id} opacity={alpha}>
              {/* 좌 -> 우로 그어지는 굵은 밑줄 */}
              <line
                x1={xStart}
                y1={y}
                x2={currentTipX}
                y2={y}
                stroke={color}
                strokeWidth={5}
                strokeLinecap="round"
                filter="url(#ann-glow)"
              />
              {/* 그리는 펜촉 팁 */}
              {drawProgress > 0 && drawProgress < 0.99 && (
                <circle cx={currentTipX} cy={y} r={6} fill="#FFFFFF" filter="url(#ann-glow)" />
              )}

              {/* 밑줄 아래 고대비 인라인 배지 (중복 플로팅 카드를 제거하여 요소 겹침 방지) */}
              {drawProgress > 0.25 && (
                <g opacity={Math.min(1, drawProgress * 1.4)}>
                  <rect
                    x={xStart}
                    y={y + 8}
                    width={badgeW}
                    height={28}
                    rx={6}
                    fill="rgba(11, 18, 32, 0.75)"
                    stroke={color}
                    strokeWidth={1.5}
                  />
                  <text
                    x={xStart + 12}
                    y={y + 27}
                    fill={color}
                    fontSize={14}
                    fontWeight={900}
                    fontFamily="Apple SD Gothic Neo, Pretendard, sans-serif"
                  >
                    ▲ {ann.title}
                  </text>
                </g>
              )}
            </g>
          );
        }

        // ─────────────────────────────────────────────────────
        // 3. 추세선 긋기 (trendline) — 고점-고점, 저점-저점 연결 사선 드로잉
        // ─────────────────────────────────────────────────────
        if (ann.kind === 'trendline') {
          const startIndex = ann.index ?? 0;
          const endIndex = ann.endIndex ?? n - 1;

          const x1 = scaleX(startIndex, n, rect);
          const x2 = scaleX(endIndex, n, rect);

          let y1 = rect.y + rect.h * 0.3;
          let y2 = rect.y + rect.h * 0.7;

          if (py) {
            const p1 = ann.price ?? (series.h[startIndex] || series.c[startIndex] || 0);
            const p2 = ann.endPrice ?? (series.h[endIndex] || series.c[endIndex] || 0);
            y1 = py(p1);
            y2 = py(p2);
          }

          // 드로잉 현재 팁 위치
          const xt = x1 + (x2 - x1) * drawProgress;
          const yt = y1 + (y2 - y1) * drawProgress;

          // 상·하단 빈 공백 클린 쉘프에 카드 배치 (캔들 가림 원천 방지)
          const shelf = getShelfPlacement(x2, Math.min(y1, y2), Math.max(y1, y2), rect, targetPanel === 'volume');

          const cardAlpha = alpha * interpolate(drawProgress, [0.5, 0.9], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });

          return (
            <g key={ann.id} opacity={alpha}>
              {/* 시작 앵커 핀 */}
              <circle cx={x1} cy={y1} r={6} fill={color} filter="url(#ann-glow)" />
              <circle cx={x1} cy={y1} r={12 * pulse} fill="none" stroke={color} strokeWidth={2} />

              {/* 대각선 추세선 드로잉 */}
              <line
                x1={x1}
                y1={y1}
                x2={xt}
                y2={yt}
                stroke={color}
                strokeWidth={4.5}
                strokeLinecap="round"
                strokeDasharray="12 5"
                filter="url(#ann-glow)"
              />

              {/* 추세선 진행 펜촉 팁 */}
              {drawProgress > 0 && drawProgress < 0.99 && (
                <circle cx={xt} cy={yt} r={7} fill="#FFFFFF" filter="url(#ann-glow)" />
              )}

              {/* 끝점 도달 시 앵커 핀 */}
              {drawProgress >= 0.95 && (
                <g filter="url(#ann-glow)">
                  <circle cx={x2} cy={y2} r={7} fill={color} />
                  <circle cx={x2} cy={y2} r={14 * pulse} fill="none" stroke={color} strokeWidth={2.5} />
                </g>
              )}

              {/* 콜아웃 지시선 (추세선 끝점과 상단/하단 빈 공백 카드를 우아하게 연결) */}
              {cardAlpha > 0.05 && (
                <g opacity={cardAlpha}>
                  <path
                    d={`M ${shelf.anchorX} ${shelf.anchorY} Q ${(shelf.anchorX + shelf.targetX) / 2} ${(shelf.anchorY + shelf.targetY) / 2} ${shelf.targetX} ${shelf.targetY}`}
                    fill="none"
                    stroke={color}
                    strokeWidth={2.2}
                    strokeDasharray="5 3"
                    opacity={0.85}
                  />
                  <circle cx={shelf.targetX} cy={shelf.targetY} r={3.5} fill={color} />
                </g>
              )}

              {/* 콜아웃 카드 */}
              {renderCalloutCard(ann, color, shelf.targetX, shelf.targetY, shelf.cardX, shelf.cardY, shelf.cardW, shelf.cardH, cardAlpha)}
            </g>
          );
        }

        // ─────────────────────────────────────────────────────
        // 4. 수평선 긋기 (hlevel) — 지지선/저항선 좌->우 드로잉 & 우측 가격 태그
        // ─────────────────────────────────────────────────────
        if (ann.kind === 'hlevel' && ann.price && py && priceRect) {
          const y = py(ann.price);
          const totalW = priceRect.w;
          const currentW = totalW * drawProgress;
          const tagLabel = ann.title.includes('원')
            ? ann.title.replace(/\s*\([\d,]+원\)/, ` ${ann.price.toLocaleString()}원`)
            : `${ann.title} ${ann.price.toLocaleString()}원`;
          const tagW = 156;
          const tagH = 30;
          const tagX = priceRect.x + priceRect.w + 4;
          const tagY = y - tagH / 2;

          const tagScale = spring({
            frame: Math.max(0, (t - (ann.from + drawDur * 0.8)) * fps),
            fps,
            config: { damping: 14, stiffness: 140 },
          });

          return (
            <g key={ann.id} opacity={alpha}>
              {/* 좌 -> 우로 그어지는 수평 대시 라인 */}
              <line
                x1={priceRect.x}
                y1={y}
                x2={priceRect.x + currentW}
                y2={y}
                stroke={color}
                strokeWidth={3}
                strokeDasharray="10 6"
                filter="url(#ann-glow)"
              />
              {/* 우측 가격 축 태그 배지 (드로잉 완료 시 팝업) */}
              {tagScale > 0.05 && (
                <g transform={`translate(${tagX}, ${tagY}) scale(${tagScale}) translate(${-tagX}, ${-tagY})`}>
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
                    y={tagY + 20}
                    fill={isBrightColor(color) ? '#0D1117' : '#FFFFFF'}
                    fontSize={13}
                    fontWeight={900}
                    textAnchor="middle"
                    fontFamily="SF Mono, Menlo, monospace"
                  >
                    {tagLabel}
                  </text>
                </g>
              )}
            </g>
          );
        }

        // ─────────────────────────────────────────────────────
        // 5. 사각 영역 박스 (box) — 테두리 드로잉 및 지우기
        // ─────────────────────────────────────────────────────
        if (ann.kind === 'box' && ann.index !== undefined && ann.index >= 0 && ann.index < n) {
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
            boxH = Math.max(24, volRect.y + volRect.h - yTop + 6);
          }

          // 상·하단 빈 공백 클린 쉘프에 카드 배치 (캔들 가림 원천 방지)
          const shelf = getShelfPlacement(cx, boxY, boxY + boxH, rect, targetPanel === 'volume');

          // 박스 둘레
          const perimeter = 2 * (barW + boxH);
          const boxStrokeOffset = perimeter * (1 - drawProgress);

          const cardAlpha = alpha * interpolate(drawProgress, [0.4, 0.85], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });

          return (
            <g key={ann.id} opacity={alpha}>
              {/* 시계방향으로 테두리가 그려지는 포커스 박스 */}
              <rect
                x={boxX}
                y={boxY}
                width={barW}
                height={boxH}
                rx={8}
                fill={`${color}22`}
                stroke={color}
                strokeWidth={3.5}
                strokeDasharray={`${perimeter}`}
                strokeDashoffset={`${boxStrokeOffset}`}
                filter="url(#ann-glow)"
              />
              <circle cx={cx} cy={boxY} r={14 * pulse} fill="none" stroke={color} strokeWidth={2.8} />
              <circle cx={cx} cy={boxY} r={5} fill={color} />

              {/* 콜아웃 지시선 (캔들과 상단/하단 빈 공백 카드를 우아하게 연결) */}
              {cardAlpha > 0.05 && (
                <g opacity={cardAlpha}>
                  <path
                    d={`M ${shelf.anchorX} ${shelf.anchorY} Q ${(shelf.anchorX + shelf.targetX) / 2} ${(shelf.anchorY + shelf.targetY) / 2} ${shelf.targetX} ${shelf.targetY}`}
                    fill="none"
                    stroke={color}
                    strokeWidth={2.2}
                    strokeDasharray="5 3"
                    opacity={0.85}
                  />
                  <circle cx={shelf.targetX} cy={shelf.targetY} r={3.5} fill={color} />
                </g>
              )}

              {renderCalloutCard(ann, color, shelf.targetX, shelf.targetY, shelf.cardX, shelf.cardY, shelf.cardW, shelf.cardH, cardAlpha)}
            </g>
          );
        }

        // ─────────────────────────────────────────────────────
        // 6. 포인터 핀 (pointer)
        // ─────────────────────────────────────────────────────
        if (ann.kind === 'pointer' && ann.index !== undefined && ann.index >= 0 && ann.index < n) {
          const cx = scaleX(ann.index, n, rect);
          const val = valueForPanel(targetPanel, series, ann.index);
          const scaleFunc = targetPanel === 'volume' ? vy : py;
          if (!scaleFunc || val === null) return null;

          const cy = scaleFunc(val);
          // 상·하단 빈 공백 클린 쉘프에 카드 배치 (캔들 가림 원천 방지)
          const shelf = getShelfPlacement(cx, cy - 12, cy + 12, rect, targetPanel === 'volume');

          const cardAlpha = alpha * interpolate(drawProgress, [0.3, 0.75], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });

          return (
            <g key={ann.id} opacity={alpha}>
              <circle cx={cx} cy={cy} r={18 * pulse * drawProgress} fill="none" stroke={color} strokeWidth={3} filter="url(#ann-glow)" />
              <circle cx={cx} cy={cy} r={6 * drawProgress} fill={color} />

              {/* 콜아웃 지시선 (포인터 핀과 상단/하단 빈 공백 카드를 우아하게 연결) */}
              {cardAlpha > 0.05 && (
                <g opacity={cardAlpha}>
                  <path
                    d={`M ${shelf.anchorX} ${shelf.anchorY} Q ${(shelf.anchorX + shelf.targetX) / 2} ${(shelf.anchorY + shelf.targetY) / 2} ${shelf.targetX} ${shelf.targetY}`}
                    fill="none"
                    stroke={color}
                    strokeWidth={2.2}
                    strokeDasharray="5 3"
                    opacity={0.85}
                  />
                  <circle cx={shelf.targetX} cy={shelf.targetY} r={3.5} fill={color} />
                </g>
              )}

              {renderCalloutCard(ann, color, shelf.targetX, shelf.targetY, shelf.cardX, shelf.cardY, shelf.cardW, shelf.cardH, cardAlpha)}
            </g>
          );
        }

        return null;
      })}
    </svg>
  );
};
