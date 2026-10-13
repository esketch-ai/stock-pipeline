import type { Panel } from './charts/theme';

export type WordTimestamp = {
  word: string;
  start: number;
  end: number;
};

export type ScriptPayload = {
  ticker: string;
  name: string;
  hook: string;
  body: string[];
  closing: string;
  chart_paths: string[];
};

export type MetricPayload = {
  label: string;
  value: string;
  delta?: string;
  tone?: 'up' | 'down' | 'flat';
};

export type PointerPayload = {
  /** 레거시 정규화 좌표 — PNG 폴백 화면에서만 사용 */
  x?: number; // normalised 0~1
  y?: number;
  /** 신규: 어느 봉·패널을 가리킬지. 좌표는 Remotion 이 자기 스케일로 계산한다 */
  index?: number;
  panel?: Panel;
  label: string;
  sublabel?: string;
  from: number; // 초
  to: number;
};

/** 대본 문장이 언급되는 시각 + 그때 강조할 지표/포인터 */
export type Cue = {
  at: number; // 초
  metric?: MetricPayload;
  pointer?: PointerPayload;
};

/**
 * Remotion 이 그릴 원본 OHLCV + 파생 지표.
 * chart_data.py 가 생성한다. 없으면 PNG 차트로 폴백한다.
 */
export type SeriesPayload = {
  d: string[];
  o: (number | null)[];
  h: (number | null)[];
  l: (number | null)[];
  c: (number | null)[];
  v: (number | null)[];
  ma5?: (number | null)[];
  ma20?: (number | null)[];
  ma60?: (number | null)[];
  rsi?: (number | null)[];
  ret?: (number | null)[];
  pts?: Record<string, number>;
};

/** 장면 헤드라인 — scene_data.py 가 계산한다 (LLM 이 만들지 않는다) */
export type SceneItem = {
  id: string;
  index: number;
  point: string;
  eyebrow: string;
  headline: string;
  sub?: string;
  stats?: { label: string; value: string; tone?: 'up' | 'down' | 'flat' }[];
  chart: string;
  from: number;
  to: number;
};

/** 투자자별 순매수 (억 단위) */
export type SupplyPayload = {
  d: string[];
  institution: number[];
  retail: number[];
  foreign: number[];
  other?: number[];
};

/** 지지 · 저항 가격대 */
export type LevelPayload = {
  support: number;
  resistance: number | null;
  recent_high: number;
  recent_low: number;
  last: number;
  room_to_support: number | null;
  room_to_resistance: number | null;
  at_high: boolean;
};

export type ContactRow = { label: string; value: string };
export type ContactPayload = {
  enabled?: boolean;
  offer?: string;
  displayUrl?: string;
  channel?: string;
  url?: string;
  note?: string;
  provider?: string;
  rows?: ContactRow[];
  business?: string;
  qrSrc?: string | null;
};

export type VideoItem = {
  ticker: string;
  name: string;
  audioSrc: string;
  timestamps: WordTimestamp[];
  script: ScriptPayload;
  charts: string[];
  /** 원본 데이터가 있으면 SVG 차트를 직접 그린다 */
  series?: SeriesPayload | null;
  /** 장면 모드 — 있으면 구도 없이 포인트 단위로 화면이 전환된다 */
  scenes?: SceneItem[];
  supply?: SupplyPayload | null;
  levels?: LevelPayload | null;
  contact?: ContactPayload;
  investorInsight?: import('./components/investorProfiles').InvestorInsight;
  changeRate?: string;
  metrics?: MetricPayload[];
  cues?: Cue[];
};

export type VideoProps = {
  items: VideoItem[];
};
