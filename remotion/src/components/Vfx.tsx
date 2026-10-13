/**
 * 영상 전역 효과 레이어.
 *
 * 설계: 해상도와 무관하게 보이도록 모든 값은 useVideoConfig 기준 비율로 만든다.
 * 렌더 프레임이 고정 시드라 매번 같은 결과가 나오는 결정적 효과만 사용한다.
 */

import React from 'react';
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from 'remotion';

/** 결정적 난수 — 프레임만으로 값을 만들어 랜덤 시드로 인한 재현성 문제를 피한다. */
const noise = (seed: number): number => {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
};

/** 필름 그레인 — 노이즈 텍스처를 타일로 반복해 프레임마다 위상이 흐르게 한다. */
export const FilmGrain: React.FC<{ opacity?: number }> = ({ opacity = 0.05 }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const tile = 220;
  const blobs = Array.from({ length: 26 }, (_, i) => {
    const r = noise(i + 1);
    const r2 = noise(i + 90);
    const r3 = noise(i + 180);
    return (
      <rect
        key={i}
        x={r * width}
        y={(r2 + ((frame * (0.06 + r3 * 0.12)) % 1)) * height}
        width={tile * (0.25 + r3 * 0.5)}
        height={1.4}
        fill={r3 > 0.5 ? '#FFFFFF' : '#8FA3C8'}
        opacity={0.35 + r * 0.5}
      />
    );
  });
  return (
    <AbsoluteFill style={{ mixBlendMode: 'overlay', pointerEvents: 'none' }}>
      <svg width={width} height={height} style={{ opacity }}>{blobs}</svg>
    </AbsoluteFill>
  );
};

/** 비네트 — 가장자리로 시선을 중앙 수치에 고정한다. */
export const Vignette: React.FC = () => {
  const { width, height } = useVideoConfig();
  return (
    <AbsoluteFill
      style={{
        pointerEvents: 'none',
        background:
          'radial-gradient(120% 88% at 50% 42%, transparent 42%, rgba(3,7,15,0.34) 78%, rgba(3,7,15,0.72) 100%)',
      }}
    />
  );
};

/** 떠다니는 먼지 입자 — 느린 상승과 좌우 흔들림으로 깊이를 만든다. */
export const DustMotes: React.FC<{ count?: number }> = ({ count = 34 }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <svg width={width} height={height}>
        {Array.from({ length: count }, (_, i) => {
          const r = noise(i * 3 + 1);
          const r2 = noise(i * 7 + 2);
          const speed = 0.08 + r * 0.22;
          const size = 1.4 + r2 * 3.2;
          const x = r * width + Math.sin(frame / (90 + i * 6)) * 26 * (0.4 + r2);
          const y = height - ((frame * speed + r2 * height) % (height * 1.15));
          return (
            <circle
              key={i}
              cx={x}
              cy={y}
              r={size}
              fill="#CFE0FF"
              opacity={0.05 + r2 * 0.16}
            />
          );
        })}
      </svg>
    </AbsoluteFill>
  );
};

/**
 * 키워드 스윕 — 헤드라인·수치에 빛이 한 번 지나간다.
 * 텍스트 위를 흐리는 얇은 하이라이트라 읽기를 방해하지 않는다.
 */
export const LightSweep: React.FC<{
  width: number;
  height: number;
  delay?: number;
  duration?: number;
}> = ({ width, height, delay = 0, duration = 46 }) => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [delay, delay + duration], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  if (progress >= 1 || progress <= 0) return null;
  const x = -width * 0.4 + progress * width * 1.8;
  return (
    <div
      style={{
        position: 'absolute',
        left: x,
        top: -height * 0.1,
        width: width * 0.22,
        height: height * 1.2,
        transform: 'skewX(-18deg)',
        background:
          'linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.16) 45%, rgba(255,255,255,0) 100%)',
        pointerEvents: 'none',
      }}
    />
  );
};

/**
 * 숫자 카운트업 — 수치가 0 에서 최종값으로 올라온다.
 * '%' '원' 등 단위 문자와 부호는 분리해 숫자 부분만 보간한다.
 */
export const CountUp: React.FC<{
  value: string;
  local: number;
  duration?: number;
}> = ({ value, local, duration = 30 }) => {
  const match = value.match(/^([+-]?)([\d.,]+)(.*)$/);
  if (!match) return <>{value}</>;
  const [, sign, digits, suffix] = match;
  const target = Number(digits.replace(/,/g, ''));
  if (!Number.isFinite(target)) return <>{value}</>;
  const progress = interpolate(local, [6, duration], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  // 지수 이동으로 자리수가 다른 값도 같은 자리수로 자연스럽게 오르게 한다.
  const eased = 1 - Math.pow(1 - progress, 3);
  const current = target * eased;
  const text = Math.abs(current) >= 100 ? Math.round(current).toLocaleString('en-US') : current.toFixed(1);
  return (
    <>
      {sign}
      {text}
      {suffix}
    </>
  );
};

/** 값이 오를 때의 강조 맥동 — 숫자 주변에만 약하게 적용한다. */
export const PulseGlow: React.FC<{ local: number; tone?: 'up' | 'down' | 'flat' }> = ({ local, tone = 'flat' }) => {
  const { width } = useVideoConfig();
  const color = tone === 'up' ? '#FF453A' : tone === 'down' ? '#0A84FF' : '#8FA3C8';
  const strength = interpolate(local, [8, 26, 46], [0.9, 0.28, 0.12], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        background: `radial-gradient(46% 22% at 22% 88%, ${color}22, transparent 70%)`,
        opacity: strength,
      }}
    />
  );
};

/**
 * 1080 기준으로 설계한 레이아웃을 어떤 해상도에서도 같은 비율로 배치한다.
 *
 * 필요성: SceneFrame/ClosingCard/TitleCard 는 1920x1080 기준 고정 픽셀을 쓴다.
 * 4K(3840x2160) 로 렌더하면 수치 행이 화면 중앙(42%) 으로 올라와 차트 축 라벨과 겹친다.
 */
export const ScaleLayer: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { width, height } = useVideoConfig();
  const scale = height / 1080;
  return (
    <AbsoluteFill style={{ transformOrigin: 'top left', transform: `scale(${scale})` }}>
      <AbsoluteFill style={{ width: width / scale, height: height / scale }}>{children}</AbsoluteFill>
    </AbsoluteFill>
  );
};

/** 장면 전환 와이프 — 이전 장면이 밀려나며 다음 장면이 드러난다. */
export const SceneWipe: React.FC<{ local: number }> = ({ local }) => {
  const { width, height } = useVideoConfig();
  const p = interpolate(local, [0, 12], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  if (p <= 0 || p >= 1) return null;
  return (
    <AbsoluteFill
      style={{
        pointerEvents: 'none',
        transform: `translateX(${(p - 1) * width}px)`,
        background:
          'linear-gradient(90deg, rgba(11,18,32,0) 0%, rgba(11,18,32,0.75) 45%, rgba(255,214,10,0.16) 100%)',
      }}
    >
      <div style={{ position: 'absolute', right: 0, top: 0, width: 3, height: '100%', background: '#FFD60A', opacity: 0.5 }} />
    </AbsoluteFill>
  );
};