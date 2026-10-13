import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  staticFile,
} from 'remotion';
import type { WordTimestamp, VideoItem } from './types';
import { ChartPointer } from './AnalystOverlay';
import type { Pointer } from './AnalystOverlay';
import { CHART_COMPONENTS, CHART_ORDER, type ChartKind } from './charts';
import { specToXY } from './charts/pointers';
import type { Series } from './charts/scale';
import type { ContactPayload } from './types';
import { SceneHeadline, SceneStats, sceneAt, type Scene } from './scenes/SceneFrame';
import { SupplyChart, type Supply } from './scenes/SupplyChart';
import { ClosingCard } from './scenes/ClosingCard';
import { InvestorInsightScene } from './components/InvestorCharacter';
import { DustMotes, FilmGrain, PulseGlow, ScaleLayer, SceneWipe, Vignette } from './components/Vfx';
import { investorProfiles, type InvestorInsight } from './components/investorProfiles';

const BACKPAD_SAFE = '#0B1220';

/** 차트 그리기에 쓸 시간(초). 이 시간이 지나면 완성된 그래프를 그대로 든다. */
const CHART_DRAW_SECONDS = 5;

/** 파티클/그라디언트 배경 — 느린 시네마틱 드리프트 */
const AnimatedBackdrop: React.FC<{ sectionProgress: number }> = ({ sectionProgress }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  // 아주 느린 광원 이동
  const drift = frame / 240;
  const x1 = 50 + Math.sin(drift) * 22;
  const y1 = 30 + Math.cos(drift * 0.7) * 18;
  const x2 = 70 + Math.sin(drift * 0.9 + 2) * 24;
  const y2 = 72 + Math.cos(drift * 0.6 + 1) * 16;

  // 그리드 스캔 라인 (시네마틱 테크)
  const scanY = ((frame * 2.4) % (height + 400)) - 200;

  return (
    <AbsoluteFill style={{ background: BACKPAD_SAFE, overflow: 'hidden' }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at ${x1}% ${y1}%, rgba(255,59,48,0.16), transparent 55%),
                       radial-gradient(circle at ${x2}% ${y2}%, rgba(10,132,255,0.16), transparent 55%)`,
        }}
      />
      {/* 그리드 라인 */}
      <AbsoluteFill
        style={{
          opacity: 0.045,
          backgroundImage: `linear-gradient(rgba(143,163,200,0.9) 1px, transparent 1px),
                            linear-gradient(90deg, rgba(143,163,200,0.9) 1px, transparent 1px)`,
          backgroundSize: `${width / 24}px ${height / 24}px`,
        }}
      />
      {/* 스캔 라인 */}
      <AbsoluteFill
        style={{
          background: `linear-gradient(180deg, transparent ${scanY}px, rgba(255,214,10,0.05) ${scanY}px, transparent ${scanY + 3}px)`,
        }}
      />
    </AbsoluteFill>
  );
};

/** 시네마틱 타이틀 카드 — 첫 N초 */
const TitleCard: React.FC<{
  name: string;
  ticker: string;
  durationFrames: number;
}> = ({ name, ticker, durationFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const fade = interpolate(frame, [0, fps * 0.5, durationFrames - fps * 0.5, durationFrames], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const scale = interpolate(frame, [0, durationFrames], [1.15, 0.92], {
    extrapolateRight: 'clamp',
  });

  // 문자열 글자별 등장
  const chars = name.split('');
  return (
    <ScaleLayer>
      <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', opacity: fade }}>
      <div
        style={{
          transform: `scale(${scale})`,
          textAlign: 'center',
          fontFamily: 'Apple SD Gothic Neo, Pretendard, sans-serif',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 18 }}>
          {chars.map((ch, i) => {
            const charFrame = i * 2;
            const charOpacity = interpolate(frame, [charFrame, charFrame + 10], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            });
            const charY = interpolate(frame, [charFrame, charFrame + 10], [40, 0], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            });
            return (
              <span
                key={i}
                style={{
                  color: '#FFFFFF',
                  fontSize: 140,
                  fontWeight: 900,
                  opacity: charOpacity,
                  transform: `translateY(${charY}px)`,
                  letterSpacing: -2,
                }}
              >
                {ch}
              </span>
            );
          })}
        </div>
        <div
          style={{
            color: '#FFD60A',
            fontSize: 48,
            fontWeight: 800,
            letterSpacing: 12,
            opacity: interpolate(frame, [fps, fps + 20], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            }),
          }}
        >
          {ticker}
        </div>
        <div
          style={{
            width: 320,
            height: 3,
            background: 'linear-gradient(90deg, transparent, #FFD60A, transparent)',
            margin: '28px auto 0',
            opacity: interpolate(frame, [fps * 1.2, fps * 1.8], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            }),
          }}
        />
      </div>
    </AbsoluteFill>
    </ScaleLayer>
  );
};

/**
 * 차트 세그먼트 — 원본 데이터가 있으면 SVG 를 직접 그리고,
 * 없으면 기존 PNG 로 폴백한다.
 *
 * 두 경로 모두 같은 프레임 구간에서 같은 크로스페이드로 교체된다.
 */
const ChartSegment: React.FC<{
  kind: ChartKind | null;
  src: string | null;
  series: Series | null;
  name: string;
  ticker: string;
  startFrame: number;
  endFrame: number;
}> = ({ kind, src, series, name, ticker, startFrame, endFrame }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();

  if ((!kind || !series) && !src) return null;
  if (frame < startFrame || frame > endFrame) return null;

  const local = frame - startFrame;
  const span = Math.max(1, endFrame - startFrame);

  const inFade = interpolate(frame, [startFrame, startFrame + fps * 1.2], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const outFade = interpolate(frame, [endFrame - fps, endFrame], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const opacity = Math.min(inFade, outFade);

  // ── SVG 네이티브 경로: 데이터가 실제로 그려진다 ──
  if (kind && series) {
    const Comp = CHART_COMPONENTS[kind];
    /**
     * 그리기는 세그먼트 길이가 아니라 '고정 시간' 안에 끝낸다.
     * 세그먼트는 90초 넘게 이어지므로, 길이에 비례시키면 축이 45초간
     * 없는 빈 화면이 유지된다. 빠르게 그리고(5초) 이후에는 그대로 든다.
     */
    const drawFrames = fps * CHART_DRAW_SECONDS;
    const progress = Math.min(1, local / drawFrames);
    return (
      <AbsoluteFill style={{ opacity, overflow: 'hidden' }}>
        <Comp series={series} name={name} ticker={ticker} progress={progress} />
      </AbsoluteFill>
    );
  }

  // ── PNG 폴백 경로 ──
  // 차트 PNG 는 영상과 같은 16:9 로 생성되므로 `contain` 이면 정확히 맞고
  // Ken Burns 로 다시 자르지 않도록 줌 범위를 좁게 유지한다.
  const zoom = interpolate(local, [0, span], [1.0, 1.04], { extrapolateRight: 'clamp' });
  const panX = interpolate(local, [0, span], [0, -1.2], { extrapolateRight: 'clamp' });
  const panY = interpolate(local, [0, span], [0, 0.8], { extrapolateRight: 'clamp' });

  return (
    <AbsoluteFill style={{ opacity, overflow: 'hidden' }}>
      <Img
        src={src as string}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'contain',
          transform: `scale(${zoom}) translateX(${panX}%) translateY(${panY}%)`,
        }}
      />
    </AbsoluteFill>
  );
};

/** 자막 구간: 최대 단어 수 / 최대 시간(초) 중 작은 값까지만 묶는다. */
const CAPTION_MAX_WORDS = 14;
const CAPTION_MAX_SECONDS = 5.2;
const CAPTION_GAP = 0.45; // 문장 사이 쉬는 시간

type Phrase = { words: WordTimestamp[]; start: number; end: number };

const buildPhrases = (words: WordTimestamp[]): Phrase[] => {
  const phrases: Phrase[] = [];
  let current: WordTimestamp[] = [];

  const flush = () => {
    if (current.length === 0) return;
    phrases.push({
      words: current,
      start: current[0].start,
      end: current[current.length - 1].end,
    });
    current = [];
  };

  for (const w of words) {
    if (current.length > 0) {
      const gap = w.start - current[current.length - 1].end;
      const span = w.end - current[0].start;
      // 문장 끝(긴 쉼) 또는 길이 초과 시 새 구간
      if (gap > CAPTION_GAP || current.length >= CAPTION_MAX_WORDS || span > CAPTION_MAX_SECONDS) {
        flush();
      }
    }
    current.push(w);
  }
  flush();
  return phrases;
};

/** 하단 시네마틱 자막 — 문장 구간 단위 */
const CinematicCaption: React.FC<{
  words: WordTimestamp[];
  highlight: string;
  fps: number;
}> = ({ words, highlight, fps }) => {
  const frame = useCurrentFrame();
  const { width } = useVideoConfig();
  const t = frame / fps;

  const phrases = React.useMemo(() => buildPhrases(words), [words]);
  const active = phrases.find((p) => t >= p.start - 0.05 && t <= p.end + 0.25);
  if (!active) return null;

  const fontSize = Math.round(width * 0.0158);

  return (
    <div
      style={{
        position: 'absolute',
        bottom: Math.round(width * 0.028),
        left: 0,
        right: 0,
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'center',
        gap: '0 0.24em',
        padding: `0 ${Math.round(width * 0.06)}px`,
        fontFamily: 'Apple SD Gothic Neo, Pretendard, sans-serif',
        fontSize,
        fontWeight: 800,
        lineHeight: 1.5,
        textAlign: 'center',
        textShadow: '0 4px 20px rgba(0,0,0,0.85)',
      }}
    >
      {active.words.map((w, i) => {
        const isActive = w.word === highlight;
        return (
          <span
            key={`${w.start}-${i}`}
            style={{
              color: isActive ? '#FFD60A' : 'rgba(245,247,250,0.94)',
              textShadow: isActive
                ? '0 0 24px rgba(255,214,10,0.6), 0 4px 20px rgba(0,0,0,0.85)'
                : '0 4px 20px rgba(0,0,0,0.85)',
            }}
          >
            {w.word}
          </span>
        );
      })}
    </div>
  );
};

/** 하단 시네마틱 정보 바 + 진행 바 (상단 지표 스트립과 중복되지 않게 축약) */
const InfoBar: React.FC<{
  name: string;
  ticker: string;
  changeRate?: string;
  progress: number;
  contact?: ContactPayload;
  persistentQr?: boolean;
}> = ({ name, ticker, changeRate, progress, contact = {}, persistentQr }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();

  const slideIn = interpolate(frame, [0, fps * 0.8], [-200, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <>
      {/* 진행 바 */}
      <div
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          width: `${progress * 100}%`,
          height: Math.max(3, Math.round(width * 0.0009)),
          background: 'linear-gradient(90deg, #FF3B30, #FFD60A)',
          boxShadow: '0 0 18px rgba(255,214,10,0.6)',
        }}
      />
      {/* 좌하단 종목 라벨 (지표 스트립이 상단을 차지하므로 아래로 이동) */}
      <div
        style={{
          position: 'absolute',
          bottom: Math.round(width * 0.012),
          left: Math.round(width * 0.018),
          display: 'flex',
          alignItems: 'baseline',
          gap: Math.round(width * 0.006),
          transform: `translateY(${-slideIn}px)`,
          fontFamily: 'Apple SD Gothic Neo, Pretendard, sans-serif',
        }}
      >
        <span style={{ color: '#8FA3C8', fontSize: Math.round(width * 0.0092), fontWeight: 700 }}>
          {name}
        </span>
        <span style={{ color: '#FFFFFF', fontSize: Math.round(width * 0.012), fontWeight: 900 }}>
          {ticker}
        </span>
        {changeRate && (
          <span
            style={{
              color: changeRate.startsWith('-') ? '#0A84FF' : '#FF453A',
              fontSize: Math.round(width * 0.0102),
              fontWeight: 800,
            }}
          >
            {changeRate}
          </span>
        )}
      </div>
      {/* 우하단 안내 — 제공자 정보가 등록된 경우에만 나타난다 */}
      <div
        style={{
          position: 'absolute',
          bottom: Math.round(width * 0.014),
          right: Math.round(width * 0.018),
          display: 'flex',
          alignItems: 'center',
          gap: Math.round(width * 0.005),
          fontFamily: 'Apple SD Gothic Neo, Pretendard, sans-serif',
          opacity: interpolate(frame, [fps, fps * 3], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          }),
        }}
      >
        <span style={{ color: '#5C6B8A', fontSize: Math.round(width * 0.0068), fontWeight: 600 }}>
          투자 정보 · 권유 아님
        </span>
        {contact.provider || contact.rows?.length ? (
          <>
            <span style={{ color: '#39445A', fontSize: Math.round(width * 0.0068) }}>|</span>
            <span style={{ color: '#7D8DA8', fontSize: Math.round(width * 0.0068), fontWeight: 600 }}>
              {[contact.provider, ...(contact.rows ?? []).map((r) => r.value)].filter(Boolean).join(' · ')}
            </span>
          </>
        ) : null}
      </div>
      {contact.qrSrc && persistentQr ? (
        <img
          src={staticFile(contact.qrSrc)}
          style={{
            position: 'absolute',
            top: Math.round(width * 0.012),
            right: Math.round(width * 0.016),
            width: Math.round(width * 0.052),
            height: Math.round(width * 0.052),
            background: '#FFFFFF',
            padding: Math.round(width * 0.0025),
            borderRadius: 6,
            opacity: interpolate(frame, [fps * 2, fps * 4], [0, 0.92], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            }),
          }}
        />
      ) : null}
    </>
  );
};

/** 메인 컴포넌트 */
const StockVideo: React.FC<{ items: VideoItem[] }> = ({ items }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width, height } = useVideoConfig();
  const item = items?.[0];

  if (!item) {
    return <AbsoluteFill style={{ background: BACKPAD_SAFE }} />;
  }

  const total = durationInFrames / fps;
  const progress = frame / durationInFrames;

  const words = item.timestamps ?? [];
  const current = words.filter((w) => frame / fps >= w.start && frame / fps <= w.end).pop()?.word ?? '';

  // ── 방송용 지표 스트립 + 포인터 ──
  // 어느 구간에서 어떤 지표를 말하는지 계산해 시각적으로 매칭시킨다.
  const cues = item.cues ?? [];

  // 다중 지표 차트 로테이션 — 같은 이미지를 반복하지 않는다.
  const chartList = (item.charts ?? []).map((c) => resolveAssetImpl(c)).filter(Boolean) as string[];
  const titleFrames = Math.floor(fps * 3.5);
  const bodyStart = titleFrames;

  // ── 장면 모드 ──
  // scene_data.py 가 대본 섹션 + 팩트에서 계산해 준다.
  // 헤드라인과 실제 대본·데이터의 일치는 렌더 검증에서 확인한다.
  const scenes = (item.scenes ?? []) as Scene[];
  const supply = (item.supply ?? null) as Supply | null;
  const contact = item.contact ?? {};

  // 원본 데이터가 있으면 SVG 차트를 직접 그린다.
  // series 는 배열 길이만 확인한다 — 값이 전부 null 이면 그릴 게 없다.
  const series: Series | null =
    item.series && item.series.c?.some((v) => v !== null && v !== undefined)
      ? (item.series as unknown as Series)
      : null;

  const slots: { kind: ChartKind | null; src: string | null }[] = series
    ? CHART_ORDER.map((k) => ({ kind: k, src: null }))
    : chartList.map((src) => ({ kind: null, src }));

  // 차트가 N장일 때 영상 길이를 균등 분할 (고정 슬롯이 아니라 비율 배분)
  const bodyLength = Math.max(1, durationInFrames - titleFrames);
  const nSeg = Math.max(1, slots.length);
  const segments = slots.map((slot, i) => ({
    ...slot,
    start: Math.floor(titleFrames + (bodyLength * i) / nSeg),
    end: Math.floor(titleFrames + (bodyLength * (i + 1)) / nSeg),
  }));
  if (segments.length > 0) {
    segments[segments.length - 1].end = durationInFrames;
  }

  /**
   * 포인터 좌표 — 신규 스펙(index/panel)이면 차트가 그릴 때 쓴 스케일로
   * 좌표를 계산하고, 레거시 x/y 면 그대로 쓴다.
   * 좌표는 '지금 보이는 세그먼트의 차트 종류' 에 맞아야 하므로 프레임마다 결정한다.
   */
  const activeKind = React.useMemo(() => {
    const f = Math.max(0, frame - (titleFrames - fps));
    const hit = segments.find((s) => f >= s.start && f < s.end);
    return hit?.kind ?? null;
  }, [frame, segments.length]);

  const pointers: Pointer[] = React.useMemo(() => {
    return cues
      .filter((c) => c.pointer)
      .map((c) => {
        const p = c.pointer!;
        if (series && activeKind && p.index !== undefined && p.panel) {
          const xy = specToXY({ index: p.index, panel: p.panel }, series, activeKind);
          if (xy) return { ...p, ...xy } as Pointer;
          return null; // 이 차트에 없는 패널이면 그리지 않는다
        }
        return (p.x !== undefined && p.y !== undefined ? p : null) as Pointer | null;
      })
      .filter((p): p is Pointer => p !== null);
  }, [cues, series, activeKind]);

  // 전역 페이드 (시작/끝)
  const globalFade = interpolate(
    frame,
    [0, fps * 0.5, durationInFrames - fps * 1.5, durationInFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );

  return (
    <AbsoluteFill style={{ background: BACKPAD_SAFE }}>
      <Audio src={resolveAssetImpl(item.audioSrc) ?? item.audioSrc} />

      <AnimatedBackdrop sectionProgress={progress} />
      {/* 전역 분위기 레이어 — 그레인/먼지/비네트는 위 레이어들 위, 텍스트 아래에 둔다 */}
      <DustMotes />
      <Vignette />

      <div style={{ opacity: globalFade }}>
        {scenes.length > 0 ? (
          frame < titleFrames ? (
            <TitleCard
              name={item.script?.name ?? item.name}
              ticker={item.ticker}
              durationFrames={titleFrames}
            />
          ) : (
          <SceneView
            scenes={scenes}
            supply={supply}
            series={series}
            name={item.script?.name ?? item.name}
            ticker={item.ticker}
            contact={contact}
            investorInsight={item.investorInsight}
          />
          )
        ) : (
          <>
        <TitleCard
          name={item.script?.name ?? item.name}
          ticker={item.ticker}
          durationFrames={titleFrames}
        />

        {segments.map((seg, i) => (
          <ChartSegment
            key={i}
            kind={seg.kind}
            src={seg.src}
            series={series}
            name={item.script?.name ?? item.name}
            ticker={item.ticker}
            startFrame={seg.start - fps}
            endFrame={seg.end}
          />
        ))}

        {/* 차트 포인터 — 현재 구간에 맞는 지점 강조 */}
        {pointers.map((p, i) => (
          <ChartPointer key={i} pointer={p} width={width} />
        ))}

          </>
        )}
        {/* 장면 모드에서도 내레이션 자막을 유지한다. */}
        <CinematicCaption words={words} highlight={current} fps={fps} />

        <InfoBar
          name={item.script?.name ?? item.name}
          ticker={item.ticker}
          changeRate={item.changeRate}
          progress={progress}
          contact={contact}
          persistentQr={process.env.CONTACT_QR_PERSISTENT === '1'}
        />
      </div>
      {/* 그레인은 텍스트 위에 얹어 필름 질감을 만든다 (읽기 해치지 않는 농도) */}
      <FilmGrain opacity={0.045} />
    </AbsoluteFill>
  );
};

/**
 * 파이프라인이 넘기는 값은 절대경로(/Users/.../stock-pipeline/cache/...) 이지만,
 * Remotion 은 public/ 기준 상대경로를 요구한다. public/cache, public/output 이
 * 심볼릭 링크로 연결되어 있으므로 프로젝트 상대 경로로 정규화한다.
 */
const resolveAssetImpl = (p?: string): string | null => {
  if (!p) return null;
  const cleaned = p.replace(/^file:\/\//, '');
  const idx = cleaned.lastIndexOf('/stock-pipeline/');
  if (idx !== -1) {
    const rel = cleaned.slice(idx + '/stock-pipeline/'.length);
    if (rel.startsWith('cache/') || rel.startsWith('output/') || rel.startsWith('data/')) {
      return staticFile(rel);
    }
  }
  return staticFile(cleaned.replace(/^\//, ''));
};

/**
 * 장면 뷰 — YouTube 분석 영상처럼 "포인트마다 화면이 바뀌는" 구조.
 *
 * 화면 구성 (박스·밑줄 없음):
 *   POINT 02 | 수급            ← accent rule 하나 + 라벨
 *   개인 매수 · 외국인 매도      ← 헤드라인 (화면이 말할 한 문장)
 *   최근 38거래일 누적 …        ← 부제
 *   [ 차트 ]                    ← 씬마다 다른 근거
 *   외국인 -11.8억  개인 +12.7억 ← 핵심 수치 (나열만)
 */
const SceneView: React.FC<{
  scenes: Scene[];
  supply: Supply | null;
  series: Series | null;
  name: string;
  ticker: string;
  contact: { channel?: string; url?: string; note?: string };
  investorInsight?: InvestorInsight;
}> = ({ scenes, supply, series, name, ticker, contact, investorInsight }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const t = frame / fps;

  const scene = sceneAt(scenes, t);
  if (!scene) return null;
  const local = frame - scene.from * fps;

  if (scene.id === 'wisdom' && investorInsight && investorProfiles.some(p => p.id === investorInsight.id)) {
    return <>
      <SceneWipe local={local} />
      <SceneHeadline scene={scene} local={local}/>
      <InvestorInsightScene insight={investorInsight} local={local}/>
    </>;
  }

  // 마지막 장면은 마무리 카드 (차트 없음)
  const isClosing = scene.id === 'outro';

  // 차트 종류 매핑 — supply 씬만 수급 차트, 나머지는 기존 SVG 차트
  const draw: React.FC<{ progress: number }> | null = (() => {
    if (isClosing) return null;
    if (scene.chart === 'supply' && supply) {
      return ({ progress }) => <SupplyChart supply={supply} progress={progress} />;
    }
    if (scene.chart === 'closing') return null;
    const kind: ChartKind =
      scene.chart === 'trend' ? 'trend' : scene.chart === 'momentum' ? 'momentum'
      : scene.chart === 'price' ? 'price' : 'return';
    if (!series) return null;
    const Comp = CHART_COMPONENTS[kind];
    return ({ progress }) => <Comp series={series} name={name} ticker={ticker} progress={progress} />;
  })();

  // 마지막 씬 진입 시 차트가 사라지고 카드로 자연스럽게 넘어가도록
  const fadeOut = interpolate(t, [scene.to - 0.8, scene.to], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <>
      <SceneWipe local={local} />
      {isClosing ? (
        <ClosingCard local={local} name={name} ticker={ticker} contact={contact} />
      ) : (
        <>
          <SceneHeadline scene={scene} local={local} />
          {draw ? (
            <div style={{ position: 'absolute', inset: 0, opacity: fadeOut }}>
              {React.createElement(draw, {
                progress: Math.min(1, Math.max(0, local / (fps * CHART_DRAW_SECONDS))),
              })}
            </div>
          ) : null}
          <SceneStats stats={scene.stats} local={local} />
          <PulseGlow local={local} tone={scene.stats?.[0]?.tone} />
        </>
      )}
    </>
  );
};

export { StockVideo };
