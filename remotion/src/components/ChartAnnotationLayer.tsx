import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig, Easing } from 'remotion';
import { C, PAD, VB, stackPanels, type Panel, type Rect } from '../charts/theme';
import { scaleX, scaleY, type Series } from '../charts/scale';
import { domainForPanel, valueForPanel, PANELS_OF } from '../charts/pointers';
import type { ChartKind } from '../charts';

export type AnnotationTone = 'up' | 'down' | 'accent' | 'purple' | 'cyan' | 'green';

export type AnnotationKind =
  | 'box'
  | 'pointer'
  | 'hlevel'
  | 'circle'
  | 'underline'
  | 'trendline'
  | 'laser_trace'
  | 'laser_target'
  | 'curved_arrow'
  | 'zigzag_wave'
  | 'range_bracket';

export type WavePoint = {
  index: number;
  price?: number;
  label?: string;
};

export type ChartAnnotation = {
  id: string;
  from: number;          // 시작 시각 (초)
  to: number;            // 종료 시각 (초)
  kind: AnnotationKind;  // 어노테이션 종류
  panel?: Panel;
  index?: number;        // 시작 봉 인덱스
  endIndex?: number;     // 끝 봉 인덱스 (추세선, 밑줄, 궤적)
  price?: number;        // 시작 가격 (수평선, 추세선 시작가, 밑줄 가격)
  endPrice?: number;     // 끝 가격 (추세선 끝가, 목표가)
  controlPrice?: number; // 베지어 곡선 제어점 가격 (curved_arrow)
  points?: WavePoint[];  // zigzag_wave 다중 정점용
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
        <filter id="laser-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="5" result="blur1" />
          <feGaussianBlur stdDeviation="12" result="blur2" />
          <feMerge>
            <feMergeNode in="blur2" />
            <feMergeNode in="blur1" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="laser-spark-glow" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="8" result="blur" />
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
        <marker
          id="laser-arrowhead"
          markerWidth="12"
          markerHeight="12"
          refX="10"
          refY="6"
          orient="auto"
        >
          <path d="M 0 1 L 11 6 L 0 11 Z" fill="#FFFFFF" />
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

        // ─────────────────────────────────────────────────────
        // 7. 레이저 포인트 실시간 궤적 드로잉 (laser_trace)
        //    — 강렬한 레이저 광원 오차드 & 4방향 렌즈 플레어 & 잔상 스파크 테일
        // ─────────────────────────────────────────────────────
        if (ann.kind === 'laser_trace') {
          const startIndex = ann.index ?? 0;
          const endIndex = ann.endIndex ?? Math.min(n - 1, startIndex + 10);
          const x1 = scaleX(startIndex, n, rect);
          const x2 = scaleX(endIndex, n, rect);

          let y1 = rect.y + rect.h * 0.3;
          let y2 = rect.y + rect.h * 0.7;
          if (py) {
            const p1 = ann.price ?? (series.h[startIndex] || series.c[startIndex] || 0);
            const p2 = ann.endPrice ?? (series.l[endIndex] || series.c[endIndex] || 0);
            y1 = py(p1);
            y2 = py(p2);
          }

          const xt = x1 + (x2 - x1) * drawProgress;
          const yt = y1 + (y2 - y1) * drawProgress;

          const shelf = getShelfPlacement(x2, Math.min(y1, y2), Math.max(y1, y2), rect, targetPanel === 'volume');
          const cardAlpha = alpha * interpolate(drawProgress, [0.4, 0.85], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });

          // 잔상 스파크 파티클 4개 (레이저 팁 후방에 감쇠 배치)
          const sparks = [0.15, 0.35, 0.6, 0.85].map((ratio, sIdx) => {
            const sx = xt - (x2 - x1) * ratio * 0.22;
            const sy = yt - (y2 - y1) * ratio * 0.22 + Math.sin(frame * 0.7 + sIdx * 2.2) * 4;
            const r = Math.max(1, 3.2 - ratio * 2);
            const op = Math.max(0, (1 - ratio) * 0.85);
            return { sx, sy, r, op };
          });

          return (
            <g key={ann.id} opacity={alpha}>
              {/* 시작점 앵커 에너지 펄스 */}
              <circle cx={x1} cy={y1} r={6} fill={color} filter="url(#laser-glow)" />
              <circle cx={x1} cy={y1} r={14 * pulse} fill="none" stroke={color} strokeWidth={2} />

              {/* 1단계: 외곽 네온 글로우 빔 */}
              <line
                x1={x1}
                y1={y1}
                x2={xt}
                y2={yt}
                stroke={color}
                strokeWidth={9}
                strokeLinecap="round"
                opacity={0.35}
                filter="url(#laser-glow)"
              />
              {/* 2단계: 메인 레이저 빔 */}
              <line
                x1={x1}
                y1={y1}
                x2={xt}
                y2={yt}
                stroke={color}
                strokeWidth={4.5}
                strokeLinecap="round"
                opacity={0.9}
                filter="url(#laser-glow)"
              />
              {/* 3단계: 초고온 화이트 코어 라인 */}
              <line
                x1={x1}
                y1={y1}
                x2={xt}
                y2={yt}
                stroke="#FFFFFF"
                strokeWidth={1.8}
                strokeLinecap="round"
                opacity={0.98}
              />

              {/* 실시간 레이저 포인트 헤드 (Draw 중 광원 플레어 & 스파크 방출) */}
              {drawProgress > 0 && drawProgress < 0.99 && (
                <g>
                  {/* 후방 잔상 스파크 */}
                  {sparks.map((sp, idx) => (
                    <circle
                      key={`spark-${idx}`}
                      cx={sp.sx}
                      cy={sp.sy}
                      r={sp.r}
                      fill="#FFFFFF"
                      opacity={sp.op}
                      filter="url(#laser-spark-glow)"
                    />
                  ))}
                  {/* 외곽 레이저 아우라 */}
                  <circle
                    cx={xt}
                    cy={yt}
                    r={18 + Math.sin(frame * 0.7) * 4}
                    fill={color}
                    opacity={0.45}
                    filter="url(#laser-spark-glow)"
                  />
                  {/* 코어 팁 */}
                  <circle cx={xt} cy={yt} r={7.5} fill={color} filter="url(#ann-glow)" />
                  <circle cx={xt} cy={yt} r={4} fill="#FFFFFF" />
                  {/* 4방향 렌즈 플레어 스파이크 */}
                  <line x1={xt - 24} y1={yt} x2={xt + 24} y2={yt} stroke="#FFFFFF" strokeWidth={2.2} opacity={0.9} />
                  <line x1={xt} y1={yt - 24} x2={xt + 24} y2={yt} stroke="#FFFFFF" strokeWidth={2.2} opacity={0.9} />
                  <line x1={xt - 12} y1={yt - 12} x2={xt + 12} y2={yt + 12} stroke={color} strokeWidth={1.8} opacity={0.75} />
                  <line x1={xt - 12} y1={yt + 12} x2={xt + 12} y2={yt - 12} stroke={color} strokeWidth={1.8} opacity={0.75} />
                </g>
              )}

              {/* 종착점 도달 시 피날레 임팩트 링 */}
              {drawProgress >= 0.95 && (
                <g filter="url(#laser-glow)">
                  <circle cx={x2} cy={y2} r={8} fill={color} />
                  <circle cx={x2} cy={y2} r={16 * pulse} fill="none" stroke={color} strokeWidth={2.8} />
                </g>
              )}

              {/* 콜아웃 지시선 */}
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
        // 8. 레이저 타깃 십자선 & 락온 스코프 드로잉 (laser_target)
        //    — 밀리터리/방송 HUD 스타일의 회전 조준경 & 락온 십자선 및 좌표 배지
        // ─────────────────────────────────────────────────────
        if (ann.kind === 'laser_target' && ann.index !== undefined && ann.index >= 0 && ann.index < n) {
          const cx = scaleX(ann.index, n, rect);
          const val = valueForPanel(targetPanel, series, ann.index);
          const scaleFunc = targetPanel === 'volume' ? vy : py;
          const cy = scaleFunc && val !== null ? scaleFunc(val) : rect.y + rect.h / 2;

          // 수축하는 조준경 링 (초기 62px -> 최종 26px)
          const reticleR = interpolate(drawProgress, [0, 0.65], [62, 26], {
            easing: Easing.bezier(0.16, 1, 0.3, 1),
            extrapolateRight: 'clamp',
          });
          const rotAngle = (frame * 3.5) % 360;

          const shelf = getShelfPlacement(cx, cy - 30, cy + 30, rect, targetPanel === 'volume');
          const cardAlpha = alpha * interpolate(drawProgress, [0.35, 0.8], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });

          return (
            <g key={ann.id} opacity={alpha}>
              {/* 회전하는 외곽 점선 락온 링 */}
              <circle
                cx={cx}
                cy={cy}
                r={reticleR}
                fill="none"
                stroke={color}
                strokeWidth={2.2}
                strokeDasharray="14 8"
                transform={`rotate(${rotAngle} ${cx} ${cy})`}
                filter="url(#laser-glow)"
              />
              {/* 내부 조준 원 */}
              <circle
                cx={cx}
                cy={cy}
                r={13}
                fill={`${color}24`}
                stroke={color}
                strokeWidth={1.8}
              />
              <circle cx={cx} cy={cy} r={4} fill="#FFFFFF" filter="url(#laser-glow)" />

              {/* 십자선 (+) 레이저 라인 */}
              <line x1={cx - 48} y1={cy} x2={cx - 16} y2={cy} stroke={color} strokeWidth={2} opacity={drawProgress} />
              <line x1={cx + 16} y1={cy} x2={cx + 48} y2={cy} stroke={color} strokeWidth={2} opacity={drawProgress} />
              <line x1={cx} y1={cy - 48} x2={cx} y2={cy - 16} stroke={color} strokeWidth={2} opacity={drawProgress} />
              <line x1={cx} y1={cy + 16} x2={cx} y2={cy + 48} stroke={color} strokeWidth={2} opacity={drawProgress} />

              {/* 4방향 코너 락온 브래킷 [ ] */}
              <g stroke={color} strokeWidth={2.5} fill="none">
                <path d={`M ${cx - 28} ${cy - 18} L ${cx - 28} ${cy - 28} L ${cx - 18} ${cy - 28}`} />
                <path d={`M ${cx + 18} ${cy - 28} L ${cx + 28} ${cy - 28} L ${cx + 28} ${cy - 18}`} />
                <path d={`M ${cx - 28} ${cy + 18} L ${cx - 28} ${cy + 28} L ${cx - 18} ${cy + 28}`} />
                <path d={`M ${cx + 18} ${cy + 28} L ${cx + 28} ${cy + 28} L ${cx + 28} ${cy + 18}`} />
              </g>

              {/* 락온 타깃 태그 (HUD 좌표) */}
              {drawProgress >= 0.5 && (
                <g opacity={Math.min(1, (drawProgress - 0.5) * 3)}>
                  <rect
                    x={cx - 52}
                    y={cy - 46}
                    width={104}
                    height={20}
                    rx={4}
                    fill="rgba(11, 18, 32, 0.9)"
                    stroke={color}
                    strokeWidth={1.2}
                  />
                  <text
                    x={cx}
                    y={cy - 32}
                    fill={color}
                    fontSize={11}
                    fontWeight={900}
                    textAnchor="middle"
                    fontFamily="SF Mono, Menlo, monospace"
                  >
                    🎯 TARGET LOCK
                  </text>
                </g>
              )}

              {/* 콜아웃 지시선 */}
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
        // 9. 반등 포물선 궤적 레이저 화살표 (curved_arrow)
        //    — 베지어 곡선 포물선 궤적으로 주가의 기술적 반등 타깃을 시각화
        // ─────────────────────────────────────────────────────
        if (ann.kind === 'curved_arrow') {
          const startIndex = ann.index ?? Math.max(0, n - 15);
          const endIndex = ann.endIndex ?? n - 1;
          const x1 = scaleX(startIndex, n, rect);
          const x2 = scaleX(endIndex, n, rect);

          let y1 = rect.y + rect.h * 0.75;
          let y2 = rect.y + rect.h * 0.35;
          if (py) {
            y1 = py(ann.price ?? (series.l[startIndex] || series.c[startIndex] || 0));
            y2 = py(ann.endPrice ?? (series.h[endIndex] || series.c[endIndex] || 0));
          }

          const xc = (x1 + x2) / 2;
          const yc = py && ann.controlPrice ? py(ann.controlPrice) : Math.max(y1, y2) + 40;

          // 베지어 곡선 근사 길이
          const chord = Math.hypot(x2 - x1, y2 - y1);
          const poly = Math.hypot(xc - x1, yc - y1) + Math.hypot(x2 - xc, y2 - yc);
          const totalL = Math.max(60, (2 * chord + poly) / 3);
          const strokeOffset = totalL * (1 - drawProgress);

          // 현재 진행 팁 (t = drawProgress)
          const u = drawProgress;
          const tipX = (1 - u) * (1 - u) * x1 + 2 * (1 - u) * u * xc + u * u * x2;
          const tipY = (1 - u) * (1 - u) * y1 + 2 * (1 - u) * u * yc + u * u * y2;

          const shelf = getShelfPlacement(x2, Math.min(y1, y2), Math.max(y1, y2, yc), rect, targetPanel === 'volume');
          const cardAlpha = alpha * interpolate(drawProgress, [0.45, 0.85], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });

          return (
            <g key={ann.id} opacity={alpha}>
              {/* 시작점 반등 앵커 */}
              <circle cx={x1} cy={y1} r={6} fill={color} filter="url(#laser-glow)" />
              <circle cx={x1} cy={y1} r={13 * pulse} fill="none" stroke={color} strokeWidth={2} />

              {/* 포물선 곡선 외곽 네온 글로우 */}
              <path
                d={`M ${x1} ${y1} Q ${xc} ${yc} ${x2} ${y2}`}
                fill="none"
                stroke={color}
                strokeWidth={7}
                strokeLinecap="round"
                strokeDasharray={`${totalL}`}
                strokeDashoffset={`${strokeOffset}`}
                opacity={0.35}
                filter="url(#laser-glow)"
              />
              {/* 포물선 곡선 메인 스트로크 */}
              <path
                d={`M ${x1} ${y1} Q ${xc} ${yc} ${x2} ${y2}`}
                fill="none"
                stroke={color}
                strokeWidth={3.8}
                strokeLinecap="round"
                strokeDasharray={`${totalL}`}
                strokeDashoffset={`${strokeOffset}`}
                filter="url(#laser-glow)"
              />
              {/* 초고온 화이트 코어 라인 */}
              <path
                d={`M ${x1} ${y1} Q ${xc} ${yc} ${x2} ${y2}`}
                fill="none"
                stroke="#FFFFFF"
                strokeWidth={1.6}
                strokeLinecap="round"
                strokeDasharray={`${totalL}`}
                strokeDashoffset={`${strokeOffset}`}
                opacity={0.95}
              />

              {/* 곡선 위를 달리는 레이저 팁 헤드 */}
              {drawProgress > 0 && drawProgress < 0.98 && (
                <g filter="url(#laser-spark-glow)">
                  <circle cx={tipX} cy={tipY} r={14} fill={color} opacity={0.4} />
                  <circle cx={tipX} cy={tipY} r={6.5} fill={color} />
                  <circle cx={tipX} cy={tipY} r={3.5} fill="#FFFFFF" />
                  <line x1={tipX - 16} y1={tipY} x2={tipX + 16} y2={tipY} stroke="#FFFFFF" strokeWidth={2} />
                  <line x1={tipX} y1={tipY - 16} x2={tipX + 16} y2={tipY} stroke="#FFFFFF" strokeWidth={2} />
                </g>
              )}

              {/* 곡선 종착 지점 도달 시 대형 네온 화살촉 및 목표 링 */}
              {drawProgress >= 0.95 && (
                <g filter="url(#laser-glow)">
                  <circle cx={x2} cy={y2} r={8} fill={color} />
                  <circle cx={x2} cy={y2} r={17 * pulse} fill="none" stroke={color} strokeWidth={2.5} />
                  {/* 화살촉 헤드 */}
                  <polygon
                    points={`${x2} ${y2 - 12}, ${x2 + 14} ${y2}, ${x2} ${y2 + 12}, ${x2 + 4} ${y2}`}
                    fill="#FFFFFF"
                  />
                </g>
              )}

              {/* 콜아웃 지시선 */}
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
        // 10. N자형 엘리어트 파동 레이저 패스 드로잉 (zigzag_wave)
        //     — 저점-고점-눌림목-돌파를 잇는 4단계 연속 레이저 드로잉 & 번호 배지
        // ─────────────────────────────────────────────────────
        if (ann.kind === 'zigzag_wave') {
          // 4단계 파동 정점 좌표 계산
          const pIdxs = ann.points?.map((p) => p.index) ?? [
            Math.max(0, (ann.index ?? 0) - 20),
            Math.max(0, (ann.index ?? 0) - 10),
            ann.index ?? Math.max(0, n - 6),
            ann.endIndex ?? (n - 1),
          ];

          const wavePts = pIdxs.map((idx, step) => {
            const x = scaleX(idx, n, rect);
            let y = rect.y + rect.h * 0.5;
            if (py) {
              const explicitP = ann.points?.[step]?.price;
              if (explicitP !== undefined) {
                y = py(explicitP);
              } else if (step % 2 === 0) {
                y = py(series.l[idx] || series.c[idx] || 0); // 짝수는 저점
              } else {
                y = py(series.h[idx] || series.c[idx] || 0); // 홀수는 고점
              }
            }
            const label = ann.points?.[step]?.label ?? (step === 0 ? '① 바닥' : step === 1 ? '② 넥라인' : step === 2 ? '③ 눌림목' : '④ 2차돌파');
            return { x, y, label, idx };
          });

          // 각 세그먼트 길이 및 누적 길이
          const segLengths: number[] = [];
          let totalWaveL = 0;
          for (let s = 0; s < wavePts.length - 1; s++) {
            const l = Math.hypot(wavePts[s + 1].x - wavePts[s].x, wavePts[s + 1].y - wavePts[s].y);
            segLengths.push(l);
            totalWaveL += l;
          }

          // 현재 드로잉 거리
          const curDist = totalWaveL * drawProgress;
          let accum = 0;
          let activeSeg = 0;
          let segU = 0;
          for (let s = 0; s < segLengths.length; s++) {
            if (curDist <= accum + segLengths[s] || s === segLengths.length - 1) {
              activeSeg = s;
              segU = segLengths[s] > 0 ? (curDist - accum) / segLengths[s] : 1;
              break;
            }
            accum += segLengths[s];
          }

          const curTipX = wavePts[activeSeg].x + (wavePts[activeSeg + 1].x - wavePts[activeSeg].x) * segU;
          const curTipY = wavePts[activeSeg].y + (wavePts[activeSeg + 1].y - wavePts[activeSeg].y) * segU;

          const lastPt = wavePts[wavePts.length - 1];
          const shelf = getShelfPlacement(lastPt.x, Math.min(...wavePts.map((p) => p.y)), Math.max(...wavePts.map((p) => p.y)), rect, targetPanel === 'volume');
          const cardAlpha = alpha * interpolate(drawProgress, [0.5, 0.9], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });

          return (
            <g key={ann.id} opacity={alpha}>
              {/* 이미 지나간 완성 세그먼트들 */}
              {wavePts.slice(0, activeSeg).map((p, s) => {
                const nextP = wavePts[s + 1];
                return (
                  <g key={`w-seg-${s}`}>
                    <line
                      x1={p.x}
                      y1={p.y}
                      x2={nextP.x}
                      y2={nextP.y}
                      stroke={color}
                      strokeWidth={4.5}
                      strokeLinecap="round"
                      filter="url(#laser-glow)"
                    />
                    <line
                      x1={p.x}
                      y1={p.y}
                      x2={nextP.x}
                      y2={nextP.y}
                      stroke="#FFFFFF"
                      strokeWidth={1.8}
                      strokeLinecap="round"
                    />
                  </g>
                );
              })}

              {/* 현재 활성 진행 중인 세그먼트 */}
              <line
                x1={wavePts[activeSeg].x}
                y1={wavePts[activeSeg].y}
                x2={curTipX}
                y2={curTipY}
                stroke={color}
                strokeWidth={5}
                strokeLinecap="round"
                filter="url(#laser-glow)"
              />
              <line
                x1={wavePts[activeSeg].x}
                y1={wavePts[activeSeg].y}
                x2={curTipX}
                y2={curTipY}
                stroke="#FFFFFF"
                strokeWidth={2}
                strokeLinecap="round"
              />

              {/* 레이저 드로잉 팁 헤드 */}
              {drawProgress > 0 && drawProgress < 0.99 && (
                <g filter="url(#laser-spark-glow)">
                  <circle cx={curTipX} cy={curTipY} r={14} fill={color} opacity={0.4} />
                  <circle cx={curTipX} cy={curTipY} r={6.5} fill={color} />
                  <circle cx={curTipX} cy={curTipY} r={3.5} fill="#FFFFFF" />
                  <line x1={curTipX - 14} y1={curTipY} x2={curTipX + 14} y2={curTipY} stroke="#FFFFFF" strokeWidth={2} />
                  <line x1={curTipX} y1={curTipY - 14} x2={curTipX} y2={curTipY + 14} stroke="#FFFFFF" strokeWidth={2} />
                </g>
              )}

              {/* 도달한 파동 정점마다 마일스톤 번호 배지 팝업 */}
              {wavePts.map((p, s) => {
                let reachedDist = 0;
                for (let k = 0; k < s; k++) reachedDist += segLengths[k];
                const isReached = curDist >= reachedDist || (s === 0 && drawProgress > 0.05);
                if (!isReached) return null;

                const badgeY = s % 2 === 0 ? p.y + 24 : p.y - 24;

                return (
                  <g key={`w-badge-${s}`} filter="url(#laser-glow)">
                    <circle cx={p.x} cy={p.y} r={6} fill={color} />
                    <circle cx={p.x} cy={p.y} r={12 * pulse} fill="none" stroke={color} strokeWidth={2} />
                    {/* 정점 라벨 배지 */}
                    <rect
                      x={p.x - 34}
                      y={badgeY - 10}
                      width={68}
                      height={20}
                      rx={4}
                      fill="rgba(11, 18, 32, 0.92)"
                      stroke={color}
                      strokeWidth={1.4}
                    />
                    <text
                      x={p.x}
                      y={badgeY + 4}
                      fill={color}
                      fontSize={11}
                      fontWeight={900}
                      textAnchor="middle"
                      fontFamily="Apple SD Gothic Neo, sans-serif"
                    >
                      {p.label}
                    </text>
                  </g>
                );
              })}

              {/* 콜아웃 지시선 */}
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
        // 11. 다이나믹 채널 밴드 & 레인지 브래킷 (range_bracket)
        //     — 박스권/채널 상하단 레이저 경계선 & 홀로그램 스캔 필
        // ─────────────────────────────────────────────────────
        if (ann.kind === 'range_bracket') {
          const startIndex = ann.index ?? Math.max(0, n - 22);
          const endIndex = ann.endIndex ?? n - 1;
          const x1 = scaleX(startIndex, n, rect);
          const x2 = scaleX(endIndex, n, rect);

          let yTop = rect.y + rect.h * 0.28;
          let yBottom = rect.y + rect.h * 0.72;
          if (py) {
            yTop = py(ann.endPrice ?? (series.h[endIndex] || 0));
            yBottom = py(ann.price ?? (series.l[startIndex] || 0));
          }

          const bandW = (x2 - x1) * drawProgress;
          const curX2 = x1 + bandW;
          const bandH = Math.max(28, yBottom - yTop);

          const shelf = getShelfPlacement(x2, yTop, yBottom, rect, targetPanel === 'volume');
          const cardAlpha = alpha * interpolate(drawProgress, [0.4, 0.85], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          });

          return (
            <g key={ann.id} opacity={alpha}>
              {/* 박스권 홀로그램 스캔 배경 */}
              <rect
                x={x1}
                y={yTop}
                width={bandW}
                height={bandH}
                fill={`${color}12`}
                stroke="none"
              />

              {/* 상단 레이저 저항 경계선 */}
              <line
                x1={x1}
                y1={yTop}
                x2={curX2}
                y2={yTop}
                stroke={color}
                strokeWidth={3.5}
                strokeDasharray="12 6"
                filter="url(#laser-glow)"
              />
              {/* 하단 레이저 지지 경계선 */}
              <line
                x1={x1}
                y1={yBottom}
                x2={curX2}
                y2={yBottom}
                stroke={color}
                strokeWidth={3.5}
                strokeDasharray="12 6"
                filter="url(#laser-glow)"
              />

              {/* 좌측 브래킷 꺽쇠 [ */}
              <path
                d={`M ${x1 + 14} ${yTop} L ${x1} ${yTop} L ${x1} ${yBottom} L ${x1 + 14} ${yBottom}`}
                fill="none"
                stroke={color}
                strokeWidth={3.5}
                filter="url(#laser-glow)"
              />

              {/* 우측 브래킷 꺽쇠 ] (드로잉 진행률에 따라 이동) */}
              <path
                d={`M ${curX2 - 14} ${yTop} L ${curX2} ${yTop} L ${curX2} ${yBottom} L ${curX2 - 14} ${yBottom}`}
                fill="none"
                stroke={color}
                strokeWidth={3.5}
                filter="url(#laser-glow)"
              />

              {/* 상하단 팁 레이저 불꽃 */}
              {drawProgress > 0 && drawProgress < 0.99 && (
                <g filter="url(#laser-spark-glow)">
                  <circle cx={curX2} cy={yTop} r={5.5} fill="#FFFFFF" />
                  <circle cx={curX2} cy={yBottom} r={5.5} fill="#FFFFFF" />
                </g>
              )}

              {/* 채널 밴드 중앙 식별 태그 */}
              {drawProgress >= 0.5 && (
                <g opacity={Math.min(1, (drawProgress - 0.5) * 3)}>
                  <rect
                    x={(x1 + curX2) / 2 - 80}
                    y={(yTop + yBottom) / 2 - 14}
                    width={160}
                    height={28}
                    rx={6}
                    fill="rgba(11, 18, 32, 0.92)"
                    stroke={color}
                    strokeWidth={1.5}
                    filter="url(#card-shadow)"
                  />
                  <text
                    x={(x1 + curX2) / 2}
                    y={(yTop + yBottom) / 2 + 5}
                    fill={color}
                    fontSize={12}
                    fontWeight={900}
                    textAnchor="middle"
                    fontFamily="Apple SD Gothic Neo, sans-serif"
                  >
                    📊 박스권 수렴 채널
                  </text>
                </g>
              )}

              {/* 콜아웃 지시선 */}
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
