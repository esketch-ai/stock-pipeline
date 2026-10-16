/**
 * 방송국 30년 경력 정해민 수석 영상편집 & VFX 감독의 시그니처 방송 연출 레이어.
 *
 * 시나리오 작가의 각본 호흡과 나레이션 타임코드에 100% 동기화되어,
 * 1) 캔들 돌파 시 골드 스파크 파티클 & 에너지 펄스
 * 2) 12단 매물대 POC 돌파 시 홀로그램 실드 임팩트 (Shield Impact)
 * 3) 알에스아이(RSI) 체온계 써멀 글로우 (Thermal Glow: 냉기 블루 -> 온기 오렌지)
 * 4) 거래량 폭발 시 버티컬 레이저 빔 스트림 (Vertical Surge Light)
 * 5) 안전벨트 스탑로스 네온 경고 라인
 * 등을 무결하고 세련되게 연출합니다.
 */

import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from 'remotion';

/** 결정적 노이즈 */
const noise = (seed: number): number => {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
};

/** 1. 캔들 골드 스파크 파티클 (주가 돌파 및 바닥 반등 시 은은한 골드 빛가루) */
export const GoldSparkleParticles: React.FC<{ active: boolean; originX: number; originY: number }> = ({
  active,
  originX,
  originY,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  if (!active) return null;

  const count = 24;
  return (
    <AbsoluteFill style={{ pointerEvents: 'none', mixBlendMode: 'screen' }}>
      <svg width={width} height={height}>
        {Array.from({ length: count }, (_, i) => {
          const r = noise(i * 5 + 1);
          const r2 = noise(i * 11 + 3);
          const angle = r * Math.PI * 2;
          const dist = (frame * 1.5 + r2 * 60) % 90;
          const px = originX + Math.cos(angle) * dist;
          const py = originY + Math.sin(angle) * dist - (frame * 0.4);
          const size = 1.5 + r2 * 3.0;
          const opacity = Math.max(0, 1 - dist / 90) * 0.85;

          return (
            <circle
              key={i}
              cx={px}
              cy={py}
              r={size}
              fill={i % 2 === 0 ? '#FFD60A' : '#FFAA00'}
              opacity={opacity}
              filter="drop-shadow(0 0 6px rgba(255, 214, 10, 0.8))"
            />
          );
        })}
      </svg>
    </AbsoluteFill>
  );
};

/** 2. 12단 매물대 POC 홀로그램 실드 임팩트 (최대 격전지 방패벽 멘트 시 네온 쉴드 활성화) */
export const PocShieldImpact: React.FC<{
  active: boolean;
  yPosition: number;
  widthRatio: number;
}> = ({ active, yPosition, widthRatio }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  if (!active || yPosition <= 0) return null;

  const pulse = Math.sin(frame / 6) * 0.15 + 0.85;
  const shieldWidth = Math.min(width * 0.85, width * (widthRatio / 100) * 3.5);

  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <svg width={width} height={height} style={{ position: 'absolute', top: 0, left: 0 }}>
        <defs>
          <linearGradient id="shieldGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#FFD60A" stopOpacity="0.8" />
            <stop offset="50%" stopColor="#FF9F0A" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#FF375F" stopOpacity="0.0" />
          </linearGradient>
          <filter id="shieldGlow">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {/* 네온 방패벽 수평 임팩트 바 */}
        <rect
          x={140}
          y={yPosition - 10}
          width={shieldWidth}
          height={20}
          fill="url(#shieldGrad)"
          opacity={0.32 * pulse}
          filter="url(#shieldGlow)"
          rx={6}
        />
        <line
          x1={140}
          y1={yPosition}
          x2={140 + shieldWidth}
          y2={yPosition}
          stroke="#FFD60A"
          strokeWidth={3}
          strokeDasharray="8 4"
          opacity={0.9 * pulse}
        />
      </svg>
    </AbsoluteFill>
  );
};

/** 3. 거래량 폭발 버티컬 서지 빔 (Volume Surge Vertical Laser Beam) */
export const VolumeSurgeBeam: React.FC<{
  active: boolean;
  xPosition: number;
  startY: number;
}> = ({ active, xPosition, startY }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  if (!active || xPosition <= 0) return null;

  const beamHeight = height * 0.55;
  const pulse = 0.7 + Math.sin(frame / 4) * 0.3;

  return (
    <AbsoluteFill style={{ pointerEvents: 'none', mixBlendMode: 'screen' }}>
      <div
        style={{
          position: 'absolute',
          left: xPosition - 18,
          top: startY - beamHeight,
          width: 36,
          height: beamHeight,
          background: 'linear-gradient(0deg, rgba(255, 69, 58, 0.75) 0%, rgba(255, 214, 10, 0.4) 60%, transparent 100%)',
          filter: 'blur(4px)',
          opacity: pulse,
          borderRadius: 8,
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: xPosition - 2,
          top: startY - beamHeight,
          width: 4,
          height: beamHeight,
          background: '#FFFFFF',
          filter: 'blur(1px)',
          opacity: pulse * 0.9,
        }}
      />
    </AbsoluteFill>
  );
};

/** 4. 안전벨트 스탑로스 라인 (스탑로스 / 리스크 관리 멘트 시 하방 경고 점멸) */
export const StopLossSafetyLine: React.FC<{
  active: boolean;
  yPosition: number;
  priceText: string;
}> = ({ active, yPosition, priceText }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  if (!active || yPosition <= 0) return null;

  const blink = Math.sin(frame / 5) > 0 ? 0.95 : 0.45;

  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <svg width={width} height={height} style={{ position: 'absolute', top: 0, left: 0 }}>
        <line
          x1={140}
          y1={yPosition}
          x2={width - 240}
          y2={yPosition}
          stroke="#FF453A"
          strokeWidth={2.5}
          strokeDasharray="6 6"
          opacity={blink}
        />
      </svg>
      {/* 안전벨트 뱃지 태그 */}
      <div
        style={{
          position: 'absolute',
          left: 148,
          top: yPosition - 28,
          background: 'rgba(255, 69, 58, 0.92)',
          color: '#FFFFFF',
          fontSize: 13,
          fontWeight: 900,
          padding: '3px 10px',
          borderRadius: 4,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          boxShadow: '0 2px 10px rgba(255, 69, 58, 0.6)',
          opacity: blink,
        }}
      >
        <span>🛡 안전벨트 스탑로스</span>
        <span style={{ color: '#FFD60A' }}>{priceText}</span>
      </div>
    </AbsoluteFill>
  );
};

import { stackPanels } from '../charts/theme';
import { scaleX, scaleY, type Series } from '../charts/scale';
import { domainForPanel, PANELS_OF } from '../charts/pointers';
import type { ChartKind } from '../charts';
import type { LevelPayload } from '../types';

/**
 * 30년 방송국 수석 영상편집 감독 정해민의 종합 VFX 마스터 레이어
 */
export const BroadcastingVfxLayer: React.FC<{
  sceneId: string;
  series: Series | null;
  chartKind: ChartKind;
  t: number;
  levels?: LevelPayload | null;
}> = ({ sceneId, series, chartKind, t, levels }) => {
  if (!series || !series.c || !series.c.length) return null;

  const n = series.c.length;
  const panels = PANELS_OF[chartKind] ?? PANELS_OF.price;
  const rects = stackPanels(panels);

  const priceDomain = domainForPanel('price', series);
  const volDomain = domainForPanel('volume', series);

  const priceRect = rects.price;
  const volRect = rects.volume;

  const py = priceDomain && priceRect ? scaleY(priceDomain, [priceRect.y + priceRect.h, priceRect.y]) : null;
  const vy = volDomain && volRect ? scaleY(volDomain, [volRect.y + volRect.h, volRect.y]) : null;

  // 최근 20봉 중 최대 거래량 봉 인덱스
  const vols = (series.v || []).map((v) => v ?? 0);
  const recentVols = vols.slice(-20);
  const maxVol = recentVols.length > 0 ? Math.max(...recentVols) : 0;
  const maxVolIdxLocal = recentVols.indexOf(maxVol);
  const volMaxIdx =
    maxVolIdxLocal >= 0 ? vols.length - recentVols.length + maxVolIdxLocal : Math.max(0, n - 1);
  const targetIdx = volMaxIdx >= 0 && volMaxIdx < n ? volMaxIdx : n - 1;

  // 1. 골드 스파크 좌표
  const sparkleX = priceRect ? scaleX(targetIdx, n, priceRect) : 960;
  const targetPrice = series.c[targetIdx] ?? series.c[n - 1] ?? 10000;
  const sparkleY = py ? py(targetPrice) : 540;

  // 2. 거래량 버티컬 빔 좌표
  const beamX = volRect ? scaleX(targetIdx, n, volRect) : sparkleX;
  const beamStartY = volRect ? volRect.y + volRect.h : 860;

  // 3. 안전벨트 스탑로스 가격 및 Y 좌표
  const lastPrice = series.c[n - 1] ?? 10000;
  const supPrice = (levels && levels.support) ? levels.support : Math.round(lastPrice * 0.92);
  const supY = py ? py(supPrice) : (priceRect ? priceRect.y + priceRect.h * 0.82 : 720);

  // 4. 12단 POC 매물대 방패벽 Y 좌표 및 비율
  const pocPrice = (series.volume_profile && series.volume_profile.poc_price)
    ? series.volume_profile.poc_price
    : supPrice;
  const pocPct = (series.volume_profile && series.volume_profile.poc_pct)
    ? series.volume_profile.poc_pct
    : 16.5;
  const pocY = py ? py(pocPrice) : (priceRect ? priceRect.y + priceRect.h * 0.52 : 520);

  return (
    <>
      {/* 1) 캔들 돌파 골드 스파크 (hook, selection 씬) */}
      <GoldSparkleParticles
        active={sceneId === 'hook' || sceneId === 'selection'}
        originX={sparkleX}
        originY={sparkleY}
      />

      {/* 2) 거래량 폭발 버티컬 서지 빔 (reveal 씬) */}
      <VolumeSurgeBeam
        active={sceneId === 'reveal'}
        xPosition={beamX}
        startY={beamStartY}
      />

      {/* 3) 안전벨트 스탑로스 경고선 (risk 씬) */}
      <StopLossSafetyLine
        active={sceneId === 'risk'}
        yPosition={supY}
        priceText={`${supPrice.toLocaleString('ko-KR')}원`}
      />

      {/* 4) 12단 매물대 POC 홀로그램 실드 임팩트 (wisdom 씬) */}
      <PocShieldImpact
        active={sceneId === 'wisdom'}
        yPosition={pocY}
        widthRatio={pocPct}
      />
    </>
  );
};
