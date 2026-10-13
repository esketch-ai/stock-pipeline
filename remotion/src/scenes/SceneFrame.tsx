/**
 * 장면 프레임 — 화면마다 "포인트 한 줄"을 말하는 구조.
 *
 * 디자인 원칙 (요청사항):
 *   · 박스(border/background/rounded container) 를 쓰지 않는다
 *   · 밑줄로 텍스트를 가리지 않는다
 *   · 대신 여백 · 크기 · 굵기 · 색상으로 위계를 만든다
 *   · 구분선은 세로 하이라이트(accent rule) 하나뿐 — 밑줄이 아니라 레이아웃 앵커
 *
 * 세로 배치 (1080)
 *   142  accent rule + POINT 02 · 수급
 *   196  헤드라인 (한 줄, 최대 2줄)
 *   268  부제 (dim)
 *   330  차트
 *   936  핵심 수치 (숫자만, 박스 없이)
 */

import React from 'react';
import { interpolate, useCurrentFrame } from 'remotion';
import { CountUp, LightSweep, ScaleLayer } from '../components/Vfx';

const FONT = "'Apple SD Gothic Neo', Pretendard, sans-serif";
const MONO = "'SF Mono', ui-monospace, Menlo, monospace";

export type SceneStat = { label: string; value: string; tone?: 'up' | 'down' | 'flat' };

export type Scene = {
  id: string;
  index: number;
  point: string;
  eyebrow: string;
  headline: string;
  sub?: string;
  stats?: SceneStat[];
  chart: string;
  from: number;
  to: number;
};

const TONE = { up: '#FF453A', down: '#0A84FF', flat: '#8FA3C8' };

/** 장면 진입 시 살짝 올라오며 나타난다 (씬마다 한 번). */
export const SceneHeadline: React.FC<{
  scene: Scene;
  /** 이 씬이 시작된 지점으로부터 지난 프레임 */
  local: number;
}> = ({ scene, local }) => {
  const rise = interpolate(local, [0, 22], [18, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const fade = interpolate(local, [0, 14], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <ScaleLayer>
      <div
        style={{
          position: 'absolute',
          left: 128,
          right: 156,
          top: 142,
          fontFamily: FONT,
          opacity: fade,
          transform: `translateY(${rise}px)`,
        }}
      >
      {/* eyebrow — accent rule 하나가 앵커 역할 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
        <div style={{ width: 64, height: 3, background: '#FFD60A', borderRadius: 2 }} />
        <div
          style={{
            color: '#8FA3C8',
            fontSize: 26,
            fontWeight: 700,
            letterSpacing: 1.2,
          }}
        >
          POINT {scene.point}
          <span style={{ color: '#3A4C74', margin: '0 14px' }}>|</span>
          <span style={{ color: '#C7D3EA' }}>{scene.eyebrow}</span>
        </div>
      </div>

      {/* 헤드라인 — 화면이 말할 한 문장 */}
      <div
        style={{
          position: 'relative',
          marginTop: 22,
          color: '#FFFFFF',
          fontSize: 74,
          fontWeight: 800,
          lineHeight: 1.16,
          letterSpacing: -2.2,
          textShadow: '0 6px 32px rgba(0,0,0,0.55)',
          maxWidth: '86%',
          overflow: 'hidden',
        }}
      >
        {scene.headline}
        <LightSweep width={1500} height={200} delay={6} duration={54} />
      </div>

      {scene.sub ? (
        <div style={{ marginTop: 16, color: '#8FA3C8', fontSize: 28, fontWeight: 600, letterSpacing: -0.4 }}>
          {scene.sub}
        </div>
      ) : null}
      </div>
    </ScaleLayer>
  );
};

/** 핵심 수치 — 박스 없이 나열만 한다. 라벨은 위, 값은 아래. */
export const SceneStats: React.FC<{ stats?: SceneStat[]; local: number }> = ({
  stats,
  local,
}) => {
  if (!stats?.length) return null;
  const fade = interpolate(local, [10, 26], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <ScaleLayer>
      <div
        style={{
          position: 'absolute',
          left: 128,
          right: 156,
          top: 906,
          display: 'flex',
          gap: 92,
          fontFamily: FONT,
          opacity: fade,
        }}
      >
        {stats.map((s) => (
          <div key={s.label} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ color: '#6B7FA3', fontSize: 22, fontWeight: 700, letterSpacing: 0.4 }}>
              {s.label}
            </div>
            <div
              style={{
                position: 'relative',
                color: TONE[s.tone ?? 'flat'],
                fontSize: 46,
                fontWeight: 800,
                fontFamily: MONO,
                letterSpacing: -1.4,
                textShadow: `0 0 26px ${TONE[s.tone ?? 'flat']}38`,
              }}
            >
              <CountUp value={s.value} local={local} />
              <LightSweep width={420} height={70} delay={10} />
            </div>
          </div>
        ))}
      </div>
    </ScaleLayer>
  );
};

/** 현재 시각에 해당하는 씬 */
export const sceneAt = (scenes: Scene[], t: number): Scene | null => {
  if (!scenes?.length) return null;
  const hit = scenes.find((s) => t >= s.from - 0.05 && t < s.to);
  if (hit) return hit;
  return t < scenes[0].from ? scenes[0] : scenes[scenes.length - 1];
};
