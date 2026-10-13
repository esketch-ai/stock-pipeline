/**
 * 마무리 카드 — 요약 + 문의 안내.
 *
 * 참고 영상이 "유튜브에 없습니다, 상세히 적어 보내드리겠습니다"로 끝내는 것과
 * 같은 결로 문의 창구를 마지막에 둔다.
 *
 * 연락처는 나중에 바뀔 수 있으므로 props 로만 받는다(하드코딩 금지).
 */

import React from 'react';
import { interpolate, staticFile } from 'remotion';
import { ScaleLayer } from '../components/Vfx';

const FONT = "'Apple SD Gothic Neo', Pretendard, sans-serif";
const MONO = "'SF Mono', ui-monospace, Menlo, monospace";

export type Contact = {
  enabled?: boolean;
  offer?: string;
  displayUrl?: string;
  /** 예: '채널 메시지' */
  channel?: string;
  /** 예: 'https://.../inquiry' */
  url?: string;
  /** 예: '자료 요청 · 종목 문의' */
  note?: string;
  provider?: string;
  rows?: { label: string; value: string }[];
  business?: string;
  /** public/ 기준 상대경로 (qr_asset 가 생성) */
  qrSrc?: string | null;
};

export const ClosingCard: React.FC<{
  local: number;
  name: string;
  ticker: string;
  contact: Contact;
}> = ({ local, name, ticker, contact }) => {
  const rise = interpolate(local, [0, 26], [22, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const fade = interpolate(local, [0, 18], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });

  return (
    <ScaleLayer>
      <div
        style={{
          position: 'absolute',
          left: 160,
          right: 200,
          top: 300,
          fontFamily: FONT,
          opacity: fade,
          transform: `translateY(${rise}px)`,
        }}
      >
      <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
        <div style={{ width: 64, height: 3, background: '#FFD60A', borderRadius: 2 }} />
        <div style={{ color: '#8FA3C8', fontSize: 26, fontWeight: 700, letterSpacing: 1.2 }}>
          오늘의 정리
        </div>
      </div>

      <div
        style={{
          marginTop: 26,
          color: '#FFFFFF',
          fontSize: 76,
          fontWeight: 800,
          letterSpacing: -2.4,
          lineHeight: 1.14,
        }}
      >
        {name}
        <span style={{ color: '#8FA3C8', fontSize: 44, marginLeft: 20, fontFamily: MONO }}>
          {ticker}
        </span>
      </div>

      <div style={{ marginTop: 18, color: '#A9BAD6', fontSize: 30, fontWeight: 600 }}>
        가격 · 거래량 · 추세 조건을 함께 확인하세요.
      </div>

      {/* 안내 — 자료 신청이 설정되지 않았어도 연락처는 밝힌다 */}
      {contact.enabled || contact.provider || contact.rows?.length ? (
        <div style={{ marginTop: 54, display: 'flex', gap: 40, alignItems: 'flex-start' }}>
          <div style={{ flex: 1, paddingLeft: 28, borderLeft: '3px solid #FFD60A' }}>
            {contact.enabled ? (
              <div style={{ color: '#FFD60A', fontSize: 26, fontWeight: 800, letterSpacing: 0.6 }}>
                {contact.offer}
              </div>
            ) : null}
            {contact.channel || contact.provider ? (
              <div style={{ marginTop: contact.enabled ? 14 : 0, color: '#FFFFFF', fontSize: 40, fontWeight: 700, letterSpacing: -1 }}>
                {contact.channel || `${contact.provider} 문의`}
              </div>
            ) : null}
            {contact.displayUrl ? (
              <div style={{ marginTop: 10, color: '#64D2FF', fontSize: 28, fontFamily: MONO, overflowWrap: 'anywhere' }}>
                {contact.displayUrl}
              </div>
            ) : null}
            {contact.rows?.length ? (
              <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
                {contact.rows.map((row) => (
                  <div key={row.value} style={{ display: 'flex', gap: 14, alignItems: 'baseline' }}>
                    <span style={{ color: '#7D8DA8', fontSize: 22 }}>{row.label}</span>
                    <span style={{ color: '#D8E2F0', fontSize: 28, fontFamily: MONO }}>{row.value}</span>
                  </div>
                ))}
              </div>
            ) : null}
            {contact.note ? (
              <div style={{ marginTop: 12, color: '#8FA3C8', fontSize: 26 }}>{contact.note}</div>
            ) : null}
            {/* 안내는 분석과 구분해 화면 하단에 별도로 표기한다. */}
            {contact.business ? (
              <div style={{ marginTop: 12, color: '#5C6B8A', fontSize: 20 }}>{contact.business}</div>
            ) : null}
          </div>
          {contact.qrSrc ? (
            <div style={{ textAlign: 'center' }}>
              <img
                src={staticFile(contact.qrSrc)}
                style={{
                  width: 230,
                  height: 230,
                  background: '#FFFFFF',
                  padding: 10,
                  borderRadius: 8,
                  opacity: interpolate(local, [26, 44], [0, 1], {
                    extrapolateLeft: 'clamp',
                    extrapolateRight: 'clamp',
                  }),
                }}
              />
              <div
                style={{
                  marginTop: 12,
                  color: '#8FA3C8',
                  fontSize: 22,
                  opacity: interpolate(local, [34, 52], [0, 1], {
                    extrapolateLeft: 'clamp',
                    extrapolateRight: 'clamp',
                  }),
                }}
              >
                {contact.provider ? `${contact.provider} 문의` : '자료 신청'}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      <div style={{ marginTop: 66, color: '#5C6B8A', fontSize: 22, letterSpacing: 0.2 }}>
        본 영상은 투자 권유가 아닙니다. 투자 판단과 그 결과에 대한 책임은 본인에게 있습니다.
      </div>
      </div>
    </ScaleLayer>
  );
};
