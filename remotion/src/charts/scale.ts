/**
 * 스케일 · 경로 빌더.
 *
 * 핵심 원칙: 좌표 계산은 오직 여기서만 한다.
 * 포인터도 같은 스케일 함수를 쓰므로 차트와 포인터가 어긋날 수 없다.
 */

import type { Rect } from './theme';

export type Series = {
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
  /** 주목할 봉의 인덱스 (cues.py 가 소비) */
  pts?: Record<string, number>;
};

export const num = (v: number | null | undefined): v is number =>
  v !== null && v !== undefined && Number.isFinite(v);

/** 값 → 픽셀 좌표 선형 변환 */
export const scaleY = (domain: [number, number], range: [number, number]) => {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const span = d1 - d0 || 1;
  return (v: number) => r0 + ((v - d0) / span) * (r1 - r0);
};

/** 봉 인덱스 → x 좌표 (band 중심) */
export const scaleX = (i: number, n: number, rect: Rect) =>
  n <= 1 ? rect.x + rect.w / 2 : rect.x + (rect.w * (i + 0.5)) / n;

export const bandWidth = (n: number, rect: Rect) => rect.w / Math.max(1, n);

/**
 * 사람이 읽기 좋은 눈금 값을 고른다 (1/2/2.5/5 × 10^k).
 */
export const niceTicks = (min: number, max: number, count = 5): number[] => {
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) return [min];
  const raw = (max - min) / Math.max(1, count);
  const mag = Math.pow(10, Math.floor(Math.log10(Math.abs(raw) || 1)));
  const norm = raw / mag;
  const step = (norm >= 5 ? 10 : norm >= 2.5 ? 5 : norm >= 2 ? 2.5 : norm >= 1 ? 2 : 1) * mag;
  const start = Math.ceil(min / step) * step;
  const out: number[] = [];
  for (let v = start; v <= max + step * 1e-6; v += step) {
    out.push(Math.round(v * 1e6) / 1e6);
  }
  return out;
};

/** 값 배열의 [min, max] — null 은 건너뛴다 */
export const extent = (values: (number | null)[], padRatio = 0.06): [number, number] => {
  let min = Infinity;
  let max = -Infinity;
  for (const v of values) {
    if (!num(v)) continue;
    if (v < min) min = v;
    if (v > max) max = v;
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
  if (min === max) {
    const pad = Math.abs(min) * 0.1 || 1;
    return [min - pad, max + pad];
  }
  const pad = (max - min) * padRatio;
  return [min - pad, max + pad];
};

/**
 * 공개된 구간(0..count)만 보고 스케일을 잡는다.
 * 봉이 하나씩 나타날 때 Y축이 같이 벌어지는 효과의 근원.
 * 여러 배열(고가·저가 등)을 한 번에 담는다.
 */
export const extentOf = (
  arrays: (number | null)[][],
  count: number,
  padRatio = 0.06
): [number, number] => {
  let min = Infinity;
  let max = -Infinity;
  for (const arr of arrays) {
    const n = Math.min(count, arr.length);
    for (let i = 0; i < n; i++) {
      const v = arr[i];
      if (!num(v)) continue;
      if (v < min) min = v;
      if (v > max) max = v;
    }
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
  if (min === max) {
    const pad = Math.abs(min) * 0.1 || 1;
    return [min - pad, max + pad];
  }
  const pad = (max - min) * padRatio;
  return [min - pad, max + pad];
};

/* ── 모션 헬퍼 ────────────────────────────────────────── */

export const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

export const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

/** 살짝 튀며 올라오는 등장 — 봉·막대가 솟을 때 */
export const easeOutBack = (t: number) => {
  const c1 = 1.9;
  const c3 = c1 + 1;
  const p = t - 1;
  return 1 + c3 * p * p * p + c1 * p * p;
};

/** 구간 시작·길이로 국소 진행률 계산 (선 드로잉 등) */
export const segment = (progress: number, start: number, dur: number) =>
  clamp01((progress - start) / Math.max(1e-6, dur));

/**
 * i 번째 요소의 등장 국소 진행률.
 * tail 동안 순차적으로 나타나며, 각 요소는 per 만큼의 진행률로 완성된다.
 */
export const stagger = (
  progress: number,
  i: number,
  n: number,
  tail: number,
  per: number
) => segment(progress, 0.08 + (tail * (i + 0.5)) / Math.max(1, n), per);

/**
 * 라인 경로 — null 이 나오면 경로를 끊는다 (이동평균 미형성 구간).
 */
export const buildLinePath = (
  values: (number | null)[],
  count: number,
  rect: Rect,
  y: (v: number) => number,
  x: (i: number) => number = (i) => scaleX(i, values.length, rect)
): string => {
  let d = '';
  let pen = false;
  const n = Math.min(count, values.length);
  for (let i = 0; i < n; i++) {
    const v = values[i];
    if (!num(v)) {
      pen = false;
      continue;
    }
    d += `${pen ? 'L' : 'M'}${x(i).toFixed(2)} ${y(v).toFixed(2)} `;
    pen = true;
  }
  return d.trim();
};

/** 면적 경로 — 라인 + 베이스라인으로 닫는다 */
export const buildAreaPath = (
  values: (number | null)[],
  count: number,
  rect: Rect,
  y: (v: number) => number,
  baseline: number
): string => {
  const line = buildLinePath(values, count, rect, y);
  if (!line) return '';
  const n = Math.min(count, values.length);
  let firstX: number | null = null;
  let lastX: number | null = null;
  for (let i = 0; i < n; i++) {
    if (!num(values[i])) continue;
    if (firstX === null) firstX = scaleX(i, values.length, rect);
    lastX = scaleX(i, values.length, rect);
  }
  if (firstX === null || lastX === null) return '';
  return `${line} L${lastX.toFixed(2)} ${baseline.toFixed(2)} L${firstX.toFixed(2)} ${baseline.toFixed(
    2
  )} Z`;
};

/**
 * 진행률로부터 '지금까지 몇 개가 공개됐는가'.
 * easeOutCubic 으로 뒤로 갈수록 촘촘해지는 리빌을 만든다.
 */
export const revealedCount = (n: number, progress: number, tail = 0.72): number => {
  const t = Math.min(1, Math.max(0, (progress - 0.08) / tail));
  const eased = 1 - Math.pow(1 - t, 3);
  return Math.max(1, Math.round(n * eased));
};

export const fmtPrice = (v: number): string =>
  Math.abs(v) >= 10000 ? `${Math.round(v).toLocaleString('en-US')}` : v.toFixed(v < 100 ? 1 : 0);

export const fmtVolume = (v: number): string => {
  if (Math.abs(v) >= 1e8) return `${(v / 1e8).toFixed(1)}억`;
  if (Math.abs(v) >= 1e4) return `${Math.round(v / 1e4).toLocaleString('en-US')}만`;
  return Math.round(v).toLocaleString('en-US');
};

export const fmtPct = (v: number): string => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;

/** 부제용 기간 표기 — "2026-01-14 ~ 2026-10-12" */
export const periodLabel = (series: Series): string => {
  const n = series.d.length;
  if (!n) return '';
  return `${series.d[0]} ~ ${series.d[n - 1]}`;
};
