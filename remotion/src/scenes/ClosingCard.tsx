/**
 * 마무리 카드 (Outro Card) — 주차뿌까 라스트 이미지 + 요약 및 구독 안내.
 *
 * 개인 연락처(민동엽, 전화번호 등)를 완전히 제거하고
 * 주차뿌까 공식 브랜딩 라스트 이미지와 구독/좋아요 안내를 배치합니다.
 */

import React from 'react';
import { interpolate, spring, staticFile, useVideoConfig } from 'remotion';
import { ScaleLayer } from '../components/Vfx';

const FONT = "'Apple SD Gothic Neo', Pretendard, sans-serif";
const MONO = "'SF Mono', ui-monospace, Menlo, monospace";

export type Contact = {
  enabled?: boolean;
  offer?: string;
  displayUrl?: string;
  channel?: string;
  url?: string;
  note?: string;
  provider?: string;
  rows?: { label: string; value: string }[];
  business?: string;
  qrSrc?: string | null;
};

export const ClosingCard: React.FC<{
  local: number;
  name: string;
  ticker: string;
  contact?: Contact;
}> = ({ local, name, ticker }) => {
  const { fps } = useVideoConfig();

  const rise = interpolate(local, [0, 26], [28, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const fade = interpolate(local, [0, 18], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });

  // 우측 라스트 이미지 등장 스프링 애니메이션
  const imageSpring = spring({
    frame: Math.max(0, local - 8),
    fps,
    config: { damping: 14, stiffness: 110 },
  });

  const pulse = 1 + Math.sin(local / 6) * 0.04;

  return (
    <ScaleLayer>
      <div
        style={{
          position: 'absolute',
          left: 120,
          right: 120,
          top: 180,
          bottom: 140,
          fontFamily: FONT,
          opacity: fade,
          transform: `translateY(${rise}px)`,
          display: 'flex',
          gap: 60,
          alignItems: 'center',
        }}
      >
        {/* 좌측: 분석 요약 및 채널 메시지 */}
        <div style={{ flex: 1.1, display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div style={{ width: 56, height: 4, background: '#FF3B30', borderRadius: 2 }} />
            <div style={{ color: '#FF3B30', fontSize: 28, fontWeight: 900, letterSpacing: 2 }}>
              CHART SMASHERS
            </div>
            <span style={{ color: '#5C6B8A', fontSize: 24 }}>|</span>
            <div style={{ color: '#8FA3C8', fontSize: 24, fontWeight: 700 }}>
              오늘의 차트 분석 완료
            </div>
          </div>

          <div
            style={{
              marginTop: 22,
              color: '#FFFFFF',
              fontSize: 78,
              fontWeight: 900,
              letterSpacing: -2.5,
              lineHeight: 1.12,
            }}
          >
            {name}
            <span style={{ color: '#FFD60A', fontSize: 44, marginLeft: 22, fontFamily: MONO, fontWeight: 800 }}>
              {ticker}
            </span>
          </div>

          <div style={{ marginTop: 20, color: '#A9BAD6', fontSize: 28, fontWeight: 600, lineHeight: 1.5 }}>
            지지선·저항선과 거래량 추세를 바탕으로<br />
            원칙 있는 매매 전략을 세워보세요.
          </div>

          {/* 구독 & 좋아요 안내 배너 */}
          <div
            style={{
              marginTop: 40,
              padding: '24px 32px',
              borderRadius: 16,
              background: 'linear-gradient(135deg, rgba(26,38,64,0.60) 0%, rgba(15,23,42,0.60) 100%)',
              backdropFilter: 'blur(16px)',
              border: '1.5px solid rgba(255, 214, 10, 0.35)',
              boxShadow: '0 12px 32px rgba(0,0,0,0.5)',
              display: 'flex',
              alignItems: 'center',
              gap: 24,
            }}
          >
            <img
              src={staticFile('brand/jucha_watermark.png')}
              style={{ width: 68, height: 68, borderRadius: 12, filter: 'drop-shadow(0 4px 10px rgba(0,0,0,0.6))' }}
            />
            <div>
              <div style={{ color: '#FFD60A', fontSize: 26, fontWeight: 900, letterSpacing: -0.5 }}>
                주식 차트 뿌셔 보까! 주차뿌까
              </div>
              <div style={{ color: '#E2E8F0', fontSize: 20, fontWeight: 600, marginTop: 4 }}>
                구독과 좋아요, 알림 설정으로 매일 핵심 종목 분석을 놓치지 마세요!
              </div>
            </div>
          </div>

          <div style={{ marginTop: 44, color: '#5C6B8A', fontSize: 20, letterSpacing: 0.2 }}>
            본 영상은 투자 권유가 아닙니다. 투자 판단과 그 결과에 대한 책임은 본인에게 있습니다.
          </div>
        </div>

        {/* 우측: 주차뿌까 공식 라스트 이미지 (Last Image) */}
        <div
          style={{
            flex: 1.1,
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            alignItems: 'center',
            transform: `scale(${imageSpring * pulse})`,
            opacity: imageSpring,
          }}
        >
          <div
            style={{
              position: 'relative',
              width: '100%',
              borderRadius: 24,
              overflow: 'hidden',
              boxShadow: '0 24px 60px rgba(0, 0, 0, 0.85), 0 0 40px rgba(255, 59, 48, 0.3)',
              border: '3px solid rgba(255, 214, 10, 0.6)',
            }}
          >
            <img
              src={staticFile('brand/jucha_main.png')}
              style={{
                width: '100%',
                height: 'auto',
                display: 'block',
                objectFit: 'cover',
              }}
            />
          </div>

          {/* 하단 구독 배지 */}
          <div
            style={{
              marginTop: 20,
              display: 'flex',
              alignItems: 'center',
              gap: 16,
              background: 'rgba(11, 18, 32, 0.60)',
              backdropFilter: 'blur(12px)',
              padding: '10px 24px',
              borderRadius: 30,
              border: '1px solid rgba(255,255,255,0.12)',
            }}
          >
            <span style={{ color: '#FF3B30', fontSize: 22, fontWeight: 900 }}>● SUBSCRIBE</span>
            <span style={{ color: '#FFFFFF', fontSize: 20, fontWeight: 700 }}>주차뿌까 채널 구독하기</span>
          </div>
        </div>
      </div>
    </ScaleLayer>
  );
};
