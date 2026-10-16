import React from 'react';
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { ScaleLayer } from './Vfx';

export interface KeyPoint {
  icon?: string;
  title: string;
  desc: string;
  tag?: string;
}

interface HeroIntroOverlayProps {
  name: string;
  ticker: string;
  keyPoints?: KeyPoint[];
  stats?: { label: string; value: string; tone?: string }[];
  durationSeconds?: number;
}

/**
 * 유튜브 첫 화면(0초 정지화면/썸네일 및 오프닝 4초) 전용 시네마틱 인트로 오버레이.
 *
 * 챠트만 덩그러니 나오는 현상을 방지하고,
 * 시청자가 영상을 켜자마자 초대형 종목명, 종목코드, 3대 핵심 투자 포인트를
 * 1초 만에 직관적으로 인지할 수 있도록 화면 전체를 압도하는 프리미엄 카드를 렌더링합니다.
 */
export const HeroIntroOverlay: React.FC<HeroIntroOverlayProps> = ({
  name,
  ticker,
  keyPoints,
  stats,
  durationSeconds = 4.2,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const totalFrames = fps * durationSeconds;
  const fadeOutStart = totalFrames - fps * 0.8; // 3.4초부터 부드러운 페이드아웃

  // 0초부터 100% 표시되어 썸네일/첫 프레임에서 완벽하게 보임
  const opacity = interpolate(
    frame,
    [0, fadeOutStart, totalFrames],
    [1, 1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  const scale = interpolate(
    frame,
    [0, fadeOutStart, totalFrames],
    [1.0, 1.0, 1.04],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  // 3대 핵심 투자 포인트가 없으면 기본 stats 또는 fallback 구성
  const points: KeyPoint[] = (keyPoints && keyPoints.length > 0)
    ? keyPoints.slice(0, 3)
    : [
        {
          icon: '🎯',
          tag: '목표주가',
          title: stats?.[0] ? `${stats[0].label} ${stats[0].value}` : '증권사 목표가 괴리율',
          desc: '국내 주요 증권사 매수 일치 컨센서스',
        },
        {
          icon: '💎',
          tag: '가치분석',
          title: stats?.[1] ? `${stats[1].label} ${stats[1].value}` : 'PBR 밴드 최하단 저평가',
          desc: '순자산가치 대비 강력한 안전마진 확보',
        },
        {
          icon: '🛡️',
          tag: '스마트머니',
          title: stats?.[2] ? `${stats[2].label} ${stats[2].value}` : '기관·외인 메이저 수급 집중',
          desc: '경영진 책임경영 및 바닥권 순매집 확인',
        },
      ];

  if (frame >= totalFrames) {
    return null;
  }

  return (
    <ScaleLayer>
      <AbsoluteFill
        style={{
          zIndex: 900,
          opacity,
          pointerEvents: 'none',
          overflow: 'hidden',
        }}
      >
      {/* 1. 시네마틱 다크 네이비 배경 + 방사형 오로라 광원 */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: 'radial-gradient(circle at 50% 42%, rgba(14, 28, 54, 0.97) 0%, rgba(11, 18, 32, 0.98) 75%, #080D18 100%)',
          transform: `scale(${scale})`,
        }}
      />

      {/* 2. 네온 오로라 글로우 (블루 & 골드) */}
      <div
        style={{
          position: 'absolute',
          top: '20%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: 900,
          height: 500,
          background: 'radial-gradient(ellipse at center, rgba(10, 132, 255, 0.22) 0%, rgba(255, 214, 10, 0.12) 40%, transparent 70%)',
          filter: 'blur(50px)',
        }}
      />

      {/* 3. 시네마틱 테크 격자 그리드 */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          opacity: 0.05,
          backgroundImage:
            'linear-gradient(rgba(143,163,200,0.8) 1px, transparent 1px), linear-gradient(90deg, rgba(143,163,200,0.8) 1px, transparent 1px)',
          backgroundSize: '80px 80px',
        }}
      />

      {/* 4. 메인 컨테이너 (중앙 정렬) */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '0 80px',
          fontFamily: 'Apple SD Gothic Neo, Pretendard, sans-serif',
          transform: `scale(${scale})`,
        }}
      >
        {/* 상단 방송 브랜딩 뱃지 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 14,
            marginBottom: 20,
          }}
        >
          <div
            style={{
              padding: '6px 20px',
              borderRadius: 20,
              background: 'linear-gradient(90deg, #FF3B30 0%, #FF453A 100%)',
              boxShadow: '0 4px 16px rgba(255, 59, 48, 0.5)',
            }}
          >
            <span
              style={{
                color: '#FFFFFF',
                fontSize: 19,
                fontWeight: 900,
                letterSpacing: 1.2,
              }}
            >
              주챠뿌까 5대 지표 정밀 타격 분석
            </span>
          </div>

          <div
            style={{
              padding: '6px 18px',
              borderRadius: 20,
              background: 'rgba(255, 255, 255, 0.08)',
              border: '1px solid rgba(255, 255, 255, 0.18)',
            }}
          >
            <span
              style={{
                color: '#A0B2CE',
                fontSize: 17,
                fontWeight: 700,
                letterSpacing: 0.5,
              }}
            >
              NAVER 증권 실측 데이터 연동
            </span>
          </div>
        </div>

        {/* 메인 종목명 & 종목코드 (초대형 임팩트 타이포그래피) */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 24,
            marginBottom: 36,
          }}
        >
          <span
            style={{
              color: '#FFFFFF',
              fontSize: 88,
              fontWeight: 900,
              letterSpacing: -1.5,
              textShadow: '0 6px 36px rgba(0,0,0,0.9), 0 0 40px rgba(10, 132, 255, 0.35)',
            }}
          >
            {name}
          </span>

          <div
            style={{
              padding: '8px 22px',
              borderRadius: 14,
              background: 'rgba(255, 214, 10, 0.14)',
              border: '2px solid rgba(255, 214, 10, 0.75)',
              boxShadow: '0 6px 20px rgba(255, 214, 10, 0.25)',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <span
              style={{
                color: '#FFD60A',
                fontSize: 42,
                fontWeight: 900,
                fontFamily: 'SF Mono, Menlo, monospace',
                letterSpacing: 3,
              }}
            >
              {ticker}
            </span>
          </div>
        </div>

        {/* 3대 핵심 투자 포인트 그리드 (가로 3열 글래스 카드) */}
        <div
          style={{
            display: 'flex',
            gap: 24,
            width: '100%',
            maxWidth: 1680,
            justifyContent: 'center',
            marginBottom: 34,
          }}
        >
          {points.map((pt, idx) => (
            <div
              key={idx}
              style={{
                flex: 1,
                maxWidth: 520,
                padding: '24px 28px',
                borderRadius: 20,
                background: 'linear-gradient(145deg, rgba(23, 38, 68, 0.88) 0%, rgba(13, 21, 38, 0.94) 100%)',
                border: '1.5px solid rgba(255, 214, 10, 0.35)',
                boxShadow: '0 12px 32px rgba(0, 0, 0, 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.12)',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              {/* 상단 태그 및 아이콘 */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: 14,
                }}
              >
                <span style={{ fontSize: 32 }}>{pt.icon || '📌'}</span>
                <span
                  style={{
                    padding: '4px 12px',
                    borderRadius: 12,
                    background: 'rgba(10, 132, 255, 0.16)',
                    border: '1px solid rgba(10, 132, 255, 0.4)',
                    color: '#64D2FF',
                    fontSize: 15,
                    fontWeight: 800,
                    letterSpacing: 0.5,
                  }}
                >
                  {pt.tag || `KEY 0${idx + 1}`}
                </span>
              </div>

              {/* 핵심 제목 */}
              <div
                style={{
                  color: '#FFFFFF',
                  fontSize: 27,
                  fontWeight: 900,
                  lineHeight: 1.3,
                  marginBottom: 8,
                  letterSpacing: -0.5,
                }}
              >
                {pt.title}
              </div>

              {/* 세부 설명 */}
              <div
                style={{
                  color: '#A0B4D0',
                  fontSize: 17,
                  fontWeight: 500,
                  lineHeight: 1.4,
                }}
              >
                {pt.desc}
              </div>
            </div>
          ))}
        </div>

        {/* 하단 안내 가이드 문구 */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <div
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: '#30D158',
              boxShadow: '0 0 10px #30D158',
            }}
          />
          <span
            style={{
              color: '#8EA0BC',
              fontSize: 17,
              fontWeight: 600,
              letterSpacing: 0.8,
            }}
          >
            차트 캔들 · 수급 매집 · 거래량 폭발 · 4대 이평선 · 12단 매물대 POC 입체 분석
          </span>
        </div>
      </div>
    </AbsoluteFill>
    </ScaleLayer>
  );
};
