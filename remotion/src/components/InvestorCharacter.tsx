import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {investorProfiles, type InvestorInsight} from './investorProfiles';

/** 로컬 SVG로 그린 편집용 캐릭터. 외부 이미지 다운로드 없이 렌더 가능. */
export const InvestorCharacter: React.FC<{id: string; size?: number}> = ({id, size = 280}) => {
  const p = investorProfiles.find((profile) => profile.id === id);
  if (!p) return null;
  return <svg width={size} height={size} viewBox="0 0 240 240" aria-label={`${p.name} 해설용 캐릭터`}>
    <circle cx="120" cy="120" r="112" fill={p.color} opacity="0.12"/>
    <circle cx="120" cy="120" r="100" fill="none" stroke={p.color} opacity="0.3" strokeDasharray="3 9"/>
    {p.style === 'long' && <path d="M62 176 Q42 54 92 42 Q161 16 180 90 L188 192Z" fill={p.hair}/>}
    <path d="M30 230 Q32 172 89 166 L151 166 Q207 176 211 230Z" fill="#293A50"/>
    <path d="M87 169 L120 222 L153 169 L135 159 L105 159Z" fill="#E7E8DF"/>
    <path d="M110 185 L130 185 L126 198 L134 227 L106 227 L115 198Z" fill={p.tie}/>
    <path d="M103 140 L103 170 Q120 184 138 169 L138 140Z" fill="#D5A483"/>
    <ellipse cx="76" cy="112" rx="11" ry="18" fill="#E4BA98"/>
    <ellipse cx="166" cy="112" rx="11" ry="18" fill="#E4BA98"/>
    <path d="M76 85 Q72 41 123 42 Q173 45 166 91 L163 127 Q159 161 123 170 Q86 160 79 130Z" fill="#EDC4A2"/>
    {p.style === 'side' ? <path d="M76 102 Q52 45 99 40 L97 66 Q77 76 76 102 M149 51 Q182 57 167 105 L158 77Z" fill={p.hair}/>
      : p.style === 'cap' ? <path d="M72 85 L79 49 Q118 18 160 52 L170 80 L184 90 L68 90Z" fill="#3C6451"/>
      : <path d="M73 96 Q53 47 101 35 Q159 26 173 75 L161 101 L153 68 Q118 80 92 64Z" fill={p.hair}/>}
    {p.style === 'beard' && <path d="M79 117 Q88 144 109 144 L125 150 L141 141 L163 116 Q163 167 124 178 Q86 164 79 117Z" fill={p.hair}/>}
    <path d="M91 96 Q100 92 110 96 M134 96 Q146 91 153 96" stroke="#766151" strokeWidth="3" fill="none" strokeLinecap="round"/>
    <ellipse cx="102" cy="108" rx="3.5" ry="4" fill="#263242"/>
    <ellipse cx="145" cy="108" rx="3.5" ry="4" fill="#263242"/>
    <path d="M124 109 L119 129 L127 130" stroke="#BC896B" strokeWidth="2.5" fill="none" strokeLinecap="round"/>
    <path d="M110 143 Q124 150 138 141" stroke="#9B6251" strokeWidth="2.5" fill="none" strokeLinecap="round"/>
    {p.glasses && <g fill="none" stroke="#344455" strokeWidth="4">
      <rect x="82" y="98" width="34" height="24" rx="8"/><rect x="130" y="98" width="34" height="24" rx="8"/>
      <path d="M116 106 L130 106 M74 101 L82 103 M164 103 L171 100"/>
    </g>}
  </svg>;
};

export const InvestorInsightScene: React.FC<{insight: InvestorInsight; local: number}> = ({insight, local}) => {
  const {fps, width, height} = useVideoConfig();
  const p = investorProfiles.find((profile) => profile.id === insight.id);
  if (!p) return null;
  const enter = spring({frame: Math.max(0, local), fps, config: {damping: 22}});
  return <AbsoluteFill style={{padding: `${height * .32}px ${width * .08}px`, display: 'flex', flexDirection: 'row', gap: width * .06,
    opacity: interpolate(local, [0, 16], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}),
    transform: `translateY(${(1 - enter) * 35}px)`, fontFamily: 'Apple SD Gothic Neo, sans-serif'}}>
    <InvestorCharacter id={p.id} size={height * .42}/>
    <div style={{flex: 1, paddingTop: height * .035}}>
      <div style={{color: p.color, fontSize: height * .024, letterSpacing: 5}}>INVESTMENT LENS · {p.role}</div>
      <div style={{color: '#F6F1E7', fontSize: height * .057, fontWeight: 800, marginTop: 16}}>{p.name}</div>
      <div style={{color: '#CDD6E4', fontSize: height * .032, marginTop: 22, lineHeight: 1.5}}>{insight.principle}</div>
      {insight.question && <div style={{color: p.color, fontSize: height * .025, marginTop: 24, lineHeight: 1.5}}>{insight.question}</div>}
      <div style={{color: '#8493A7', fontSize: height * .017, marginTop: 22}}>투자 원칙 해설 · 편집용 일러스트</div>
    </div>
  </AbsoluteFill>;
};

export const InvestorGallery: React.FC = () => {
  const frame = useCurrentFrame();
  return <AbsoluteFill style={{background: '#0B1220', color: '#F6F1E7', fontFamily: 'Apple SD Gothic Neo, sans-serif', padding: '44px 64px'}}>
    <div style={{fontSize: 18, color: '#E9BD69', letterSpacing: 6}}>STOCK PIPELINE / CHARACTER STUDY 01</div>
    <h1 style={{fontSize: 48, margin: '16px 0 8px'}}>열 가지 얼굴, 서로 다른 투자 질문</h1>
    <div style={{color: '#8493A7', fontSize: 20}}>로컬 벡터 캐릭터 · 투자 원칙 해설용</div>
    <div style={{display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '24px 36px', marginTop: 32}}>
      {investorProfiles.map((p, i) => <div key={p.id} style={{opacity: interpolate(frame, [i * 3, i * 3 + 15], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}}>
        <InvestorCharacter id={p.id} size={210}/>
        <div style={{fontSize: 28, fontWeight: 700}}>{p.name}</div>
        <div style={{color: p.color, fontSize: 19, marginTop: 6}}>{p.role}</div>
        <div style={{fontSize: 17, lineHeight: 1.45, color: '#ADB9CB', marginTop: 10, maxWidth: 280}}>{p.principle}</div>
      </div>)}
    </div>
  </AbsoluteFill>;
};
