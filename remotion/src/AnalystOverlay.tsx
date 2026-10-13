/**
 * 전문 투자 방송용 데이터 오버레이.
 *
 * 배경 차트 위에 겹쳐서 "어디를 보는지"를 알려주는图层.
 *  - 지표 패널 (현재가 / 등락률 / 거래량 배율 / 52주 위치)
 *  - 차트 위 포인터 (해당 시점 강조 + 라벨)
 *  - 데이터 하이라이트 박스
 *
 * 좌표계는 normalised(0~1) 기준이라 어떤 해상도에서도 같은 위치에 그려진다.
 */

import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';

const FONT = 'Apple SD Gothic Neo, Pretendard, sans-serif';
const MONO = 'SF Mono, Menlo, monospace';

/**
 * Remotion 은 프레임 단위 결정적 렌더링이라 CSS `transition` 이 동작하지 않는다.
 * (브라우저처럼 이전 프레임 상태를 기억하지 않는다)
 * 강조 세기 0~1 을 interpolate 로 계산해 색/테두리/그림자에 직접 적용한다.
 */
type RGB = readonly [number, number, number];

const IDLE_BG: RGB = [11, 18, 32];
const ACTIVE_BG: RGB = [86, 74, 18];
const IDLE_BORDER: RGB = [255, 255, 255];
const ACCENT: RGB = [255, 214, 10];
const TEXT_IDLE: RGB = [255, 255, 255];

const lerp = (from: number, to: number, t: number) => from + (to - from) * t;

const lerpRGB = (from: RGB, to: RGB, t: number): RGB =>
  [0, 1, 2].map((i) => Math.round(lerp(from[i], to[i], t))) as unknown as RGB;

const rgba = (c: RGB, a: number) => `rgba(${c[0]},${c[1]},${c[2]},${lerp(0, 1, a).toFixed(3)})`;

const rgb = (c: RGB) => `rgb(${c[0]},${c[1]},${c[2]})`;

export type Metric = {
  label: string;
  value: string;
  delta?: string;
  tone?: 'up' | 'down' | 'flat';
  /** 이 지표가 강조되는 시각 구간(초) */
  cueAt?: number;
};

export type Pointer = {
  /** 강조할 지점 (normalised x, y) — 0~1 */
  x: number;
  y: number;
  label: string;
  sublabel?: string;
  /** 표시 구간(초) */
  from: number;
  to: number;
};

/** 상단 지표 스트립 — 방송 그래픽 스타일 */
export const MetricStrip: React.FC<{
  metrics: Metric[];
  totalSeconds: number;
}> = ({ metrics }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const t = frame / fps;

  return (
    <div
      style={{
        position: 'absolute',
        top: Math.round(width * 0.012),
        left: Math.round(width * 0.018),
        right: Math.round(width * 0.018),
        display: 'flex',
        gap: Math.round(width * 0.006),
        fontFamily: FONT,
      }}
    >
      {metrics.map((m, i) => {
        // 강조 세기 0~1 — 진입/이탈 구간에서 부드럽게 올라갔다 내려온다.
        const focus =
          m.cueAt === undefined
            ? 0
            : interpolate(
                t,
                [m.cueAt - 2.2, m.cueAt - 1.6, m.cueAt + 1.6, m.cueAt + 2.2],
                [0, 1, 1, 0],
                { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
              );
        const enter = spring({
          frame: frame - i * 4,
          fps,
          config: { damping: 200, stiffness: 120 },
        });
        const color =
          m.tone === 'up' ? '#FF453A' : m.tone === 'down' ? '#0A84FF' : '#8FA3C8';

        return (
          <div
            key={m.label}
            style={{
              flex: 1,
              background: rgba(lerpRGB(IDLE_BG, ACTIVE_BG, focus), 0.66),
              backdropFilter: 'blur(16px)',
              border: `1px solid ${rgba(
                lerpRGB(IDLE_BORDER, ACCENT, focus),
                lerp(0.1, 0.5, focus)
              )}`,
              borderRadius: Math.round(width * 0.004),
              padding: `${Math.round(width * 0.005)}px ${Math.round(width * 0.009)}px`,
              transform: `translateY(${(1 - enter) * -30}px)`,
              opacity: enter,
              boxShadow:
                focus > 0.01
                  ? `0 0 ${Math.round(28 * focus)}px ${rgba(ACCENT, 0.22 * focus)}`
                  : 'none',
            }}
          >
            <div style={{ color: '#8FA3C8', fontSize: Math.round(width * 0.0072), fontWeight: 700 }}>
              {m.label}
            </div>
            <div
              style={{
                display: 'flex',
                alignItems: 'baseline',
                gap: Math.round(width * 0.004),
                marginTop: 2,
              }}
            >
              <span
                style={{
                  color: rgb(lerpRGB(TEXT_IDLE, ACCENT, focus)),
                  fontFamily: MONO,
                  fontSize: Math.round(width * 0.0145),
                  fontWeight: 700,
                  letterSpacing: -0.5,
                }}
              >
                {m.value}
              </span>
              {m.delta && (
                <span style={{ color, fontSize: Math.round(width * 0.009), fontWeight: 800 }}>
                  {m.delta}
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

/** 차트 위 포인터 — 원 + 라벨 + 리더선 */
export const ChartPointer: React.FC<{ pointer: Pointer; width: number }> = ({
  pointer,
  width,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  const visible = t >= pointer.from && t <= pointer.to;
  if (!visible) return null;

  const local = frame - pointer.from * fps;
  const appear = spring({ frame: local, fps, config: { damping: 200, stiffness: 150 } });
  const fadeOut = interpolate(t, [pointer.to - 0.6, pointer.to], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const alpha = appear * fadeOut;

  // 펄스 링
  const pulse = 1 + Math.sin(frame / 6) * 0.12;
  const r = Math.round(width * 0.011) * pulse;

  return (
    <div
      style={{
        position: 'absolute',
        left: `${pointer.x * 100}%`,
        top: `${pointer.y * 100}%`,
        transform: `translate(-50%, -50%) scale(${appear})`,
        opacity: alpha,
        pointerEvents: 'none',
      }}
    >
      {/* 펄스 링 */}
      <div
        style={{
          position: 'absolute',
          left: -r,
          top: -r,
          width: r * 2,
          height: r * 2,
          borderRadius: '50%',
          border: `3px solid rgba(255,214,10,${0.75 * alpha})`,
          boxShadow: `0 0 ${r}px rgba(255,214,10,0.55)`,
        }}
      />
      {/* 중심점 */}
      <div
        style={{
          position: 'absolute',
          left: -Math.round(width * 0.0022),
          top: -Math.round(width * 0.0022),
          width: Math.round(width * 0.0044),
          height: Math.round(width * 0.0044),
          borderRadius: '50%',
          background: '#FFD60A',
        }}
      />
      {/* 라벨 */}
      <div
        style={{
          position: 'absolute',
          left: r * 1.5,
          top: -Math.round(width * 0.014),
          background: 'rgba(11,18,32,0.92)',
          border: '1px solid rgba(255,214,10,0.55)',
          borderRadius: Math.round(width * 0.003),
          padding: `${Math.round(width * 0.0035)}px ${Math.round(width * 0.007)}px`,
          whiteSpace: 'nowrap',
          fontFamily: FONT,
          boxShadow: '0 6px 24px rgba(0,0,0,0.6)',
        }}
      >
        <div style={{ color: '#FFD60A', fontSize: Math.round(width * 0.0092), fontWeight: 800 }}>
          {pointer.label}
        </div>
        {pointer.sublabel && (
          <div style={{ color: '#C7D3EA', fontSize: Math.round(width * 0.0072), marginTop: 1 }}>
            {pointer.sublabel}
          </div>
        )}
      </div>
    </div>
  );
};

/** 하단 자막 위 근거 배너 (수치 강조) */
export const EvidenceBanner: React.FC<{
  text: string;
  from: number;
  to: number;
  width: number;
}> = ({ text, from, to, width }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  if (t < from || t > to) return null;

  const appear = spring({
    frame: frame - from * fps,
    fps,
    config: { damping: 200, stiffness: 160 },
  });

  return (
    <div
      style={{
        position: 'absolute',
        top: Math.round(width * 0.075),
        left: 0,
        right: 0,
        display: 'flex',
        justifyContent: 'center',
        opacity: appear,
      }}
    >
      <div
        style={{
          background: 'rgba(11,18,32,0.86)',
          backdropFilter: 'blur(14px)',
          border: '1px solid rgba(255,214,10,0.35)',
          borderLeft: `4px solid #FFD60A`,
          borderRadius: Math.round(width * 0.003),
          padding: `${Math.round(width * 0.0045)}px ${Math.round(width * 0.011)}px`,
          fontFamily: FONT,
          fontSize: Math.round(width * 0.0105),
          fontWeight: 700,
          color: '#F5F7FA',
          boxShadow: '0 8px 32px rgba(0,0,0,0.55)',
          maxWidth: '72%',
          textAlign: 'center',
        }}
      >
        {text}
      </div>
    </div>
  );
};