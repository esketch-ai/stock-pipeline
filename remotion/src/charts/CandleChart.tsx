/**
 * 네이버 증권 캔들 + 매물대(Volume Profile) + 거래량 + 4대 이동평균선(5/20/60/120) 차트.
 *
 * 특징:
 *   - 네이버 증권 4대 이동평균선 (5일선 빨강, 20일선 황금, 60일선 파랑, 120일선 보라)
 *   - 네이버 증권 매물대 분석도 (Horizontal Volume Profile) 및 POC(최대 매물대) 하이라이트
 *   - 거래량 패널 20일 거래량 이동평균선 (v_ma20)
 *   - 네이버 증권 상단 범례 및 실시간 호가/가격 태그
 */

import React from 'react';
import { C, FONT, MONO, isBrightColor, type Panel } from './theme';
import {
  buildLinePath,
  easeOutBack,
  easeOutCubic,
  extentOf,
  fmtPrice,
  fmtVolume,
  num,
  revealedCount,
  scaleX,
  scaleY,
  segment,
  stagger,
  type Series,
} from './scale';
import { ChartFrame, usePanels } from './ChartFrame';

const PANELS: Panel[] = ['price', 'volume'];
const REVEAL_TAIL = 0.7;
const TAG_W = 140;

export const CandleChart: React.FC<{
  series: Series;
  name: string;
  ticker: string;
  progress: number;
}> = ({ series, name, ticker, progress }) => {
  const n = series.c.length;
  const rects = usePanels(PANELS);
  const count = revealedCount(n, progress, REVEAL_TAIL);

  const priceRect = rects.price;
  const volRect = rects.volume;

  // Y축은 '지금까지 공개된 봉'만 보고 매 프레임 다시 계산된다. 상단 0.18 여백으로 캔들 상단 공간 확보
  const priceDomain = extentOf([series.h, series.l], count, 0.18);
  const volRaw = extentOf([series.v], count, 0.1);
  const volDomain: [number, number] = [0, Math.max(volRaw[1], 1)];

  const py = scaleY(priceDomain, [priceRect.y + priceRect.h, priceRect.y]);
  const vy = scaleY(volDomain, [volRect.y + volRect.h, volRect.y]);

  const band = priceRect.w / n;
  const cw = Math.max(2, band * 0.62);

  const last = Math.min(count, n) - 1;
  const firstClose = num(series.c[0]) ? (series.c[0] as number) : null;
  const lastClose = num(series.c[last]) ? (series.c[last] as number) : null;
  const tagIn = segment(progress, 0.74, 0.24);
  const shownPrice =
    firstClose !== null && lastClose !== null
      ? firstClose + (lastClose - firstClose) * easeOutCubic(tagIn)
      : lastClose;

  // 네이버 증권 4대 이동평균선
  const maLines = [
    { key: 'ma120', label: '120일', values: series.ma120 ?? [], color: '#BF5AF2', width: 2.0, start: 0.25, dur: 0.35 },
    { key: 'ma60', label: '60일', values: series.ma60 ?? [], color: '#0A84FF', width: 2.0, start: 0.35, dur: 0.35 },
    { key: 'ma20', label: '20일', values: series.ma20 ?? [], color: '#FF9500', width: 2.5, start: 0.45, dur: 0.35 },
    { key: 'ma5', label: '5일', values: series.ma5 ?? [], color: '#FF3B30', width: 2.5, start: 0.55, dur: 0.35 },
  ];

  const lastMa5 = series.ma5?.[last];
  const lastMa20 = series.ma20?.[last];
  const lastMa60 = series.ma60?.[last];
  const lastMa120 = series.ma120?.[last];

  // 매물대 분석도 (Volume Profile)
  const vp = series.volume_profile;
  const vpZones = vp?.zones ?? [];
  const maxVpPct = Math.max(...vpZones.map((z) => z.pct), 1);
  const pocPrice = vp?.poc_price;
  const pocZone = pocPrice
    ? vpZones.find((z) => Math.abs(z.price_mid - pocPrice) <= (z.price_max - z.price_min) * 0.55)
    : null;
  const vpIn = easeOutCubic(segment(progress, 0.2, 0.4));

  // 거래량 20일선
  const lastVMa20 = series.v_ma20?.[last];

  // VFX 효과: 은은한 파티클
  const particles = Array.from({ length: Math.floor(count / 3) }, (_, i) => {
    const idx = i * 3;
    const x = scaleX(idx, n, priceRect);
    const y = py(series.c[idx] ?? 0);
    const particleOpacity = easeOutCubic(segment(progress, i * 0.15, 0.4));
    return (
      <circle
        key={`particle${i}`}
        cx={x}
        cy={y}
        r={1.5 + particleOpacity * 2.5}
        fill={C.up}
        opacity={particleOpacity * 0.5}
      />
    );
  });

  return (
    <ChartFrame
      series={series}
      panels={PANELS}
      domains={{ price: priceDomain, volume: volDomain }}
      formatters={{ price: fmtPrice, volume: fmtVolume }}
      count={count}
      progress={progress}
      title="일봉 매물대 차트"
    >
      {/* 네이버 증권 4대 이동평균선 상단 범례 카드 — 차트 내부 우상단 클린 헤드룸(x=priceRect.x + priceRect.w - 560, y=priceRect.y + 20) 배치 */}
      <g opacity={segment(progress, 0.3, 0.3)}>
        <g transform={`translate(${priceRect.x + priceRect.w - 560}, ${priceRect.y + 20})`}>
          <rect
            x={-10}
            y={-14}
            width={560}
            height={30}
            rx={6}
            fill="rgba(11, 18, 32, 0.75)"
            stroke="rgba(255, 255, 255, 0.15)"
            strokeWidth={1}
          />
          {num(lastMa5) && (
            <g transform="translate(0, 2)">
              <rect x={-4} y={-12} width={38} height={18} rx={4} fill="#FF3B30" />
              <text x={15} y={1} textAnchor="middle" fill="#FFFFFF" fontSize={11} fontWeight={900} fontFamily={FONT}>5일</text>
              <text x={42} y={1} fill="#FF3B30" fontSize={13} fontWeight={800} fontFamily={MONO}>
                {fmtPrice(lastMa5)}원
              </text>
            </g>
          )}
          {num(lastMa20) && (
            <g transform="translate(145, 2)">
              <rect x={-4} y={-12} width={42} height={18} rx={4} fill="#FF9500" />
              <text x={17} y={1} textAnchor="middle" fill="#0D1117" fontSize={11} fontWeight={900} fontFamily={FONT}>20일</text>
              <text x={46} y={1} fill="#FF9500" fontSize={13} fontWeight={800} fontFamily={MONO}>
                {fmtPrice(lastMa20)}원
              </text>
            </g>
          )}
          {num(lastMa60) && (
            <g transform="translate(295, 2)">
              <rect x={-4} y={-12} width={42} height={18} rx={4} fill="#0A84FF" />
              <text x={17} y={1} textAnchor="middle" fill="#FFFFFF" fontSize={11} fontWeight={900} fontFamily={FONT}>60일</text>
              <text x={46} y={1} fill="#0A84FF" fontSize={13} fontWeight={800} fontFamily={MONO}>
                {fmtPrice(lastMa60)}원
              </text>
            </g>
          )}
          {num(lastMa120) && (
            <g transform="translate(445, 2)">
              <rect x={-4} y={-12} width={48} height={18} rx={4} fill="#BF5AF2" />
              <text x={20} y={1} textAnchor="middle" fill="#FFFFFF" fontSize={11} fontWeight={900} fontFamily={FONT}>120일</text>
              <text x={52} y={1} fill="#BF5AF2" fontSize={13} fontWeight={800} fontFamily={MONO}>
                {fmtPrice(lastMa120)}원
              </text>
            </g>
          )}
        </g>
      </g>

      {/* 네이버 증권 매물대 분석도 (Horizontal Volume Profile) — 배경 레이어 */}
      {vpZones.length > 0 && (
        <g opacity={vpIn}>
          {vpZones.map((z, idx) => {
            if (z.pct <= 0) return null;
            const yTop = py(z.price_max);
            const yBottom = py(z.price_min);
            const barY = Math.min(yTop, yBottom);
            const barH = Math.max(3, Math.abs(yBottom - yTop) - 2);
            const isPoc = pocZone && Math.abs(z.price_mid - pocZone.price_mid) < 1;
            const barW = (z.pct / maxVpPct) * (priceRect.w * 0.32) * vpIn;

            return (
              <g key={`vp-${idx}`}>
                {/* 수평 매물대 막대 */}
                <rect
                  x={priceRect.x}
                  y={barY}
                  width={barW}
                  height={barH}
                  fill={isPoc ? 'rgba(255, 184, 0, 0.32)' : 'rgba(10, 132, 255, 0.14)'}
                  stroke={isPoc ? '#FFB800' : 'rgba(10, 132, 255, 0.28)'}
                  strokeWidth={isPoc ? 1.5 : 1}
                  rx={2}
                />
                {/* 일반 매물대 퍼센트 라벨 (비중 5% 이상인 경우, POC 제외) */}
                {!isPoc && z.pct >= 5.0 && (
                  <text
                    x={priceRect.x + barW + 6}
                    y={barY + barH / 2 + 4}
                    fill="#8FA3C8"
                    fontSize={12}
                    fontWeight={700}
                    fontFamily={MONO}
                  >
                    {z.pct.toFixed(1)}%
                  </text>
                )}
              </g>
            );
          })}
        </g>
      )}

      {/* 거래량 막대 */}
      {Array.from({ length: count }, (_, i) => {
        const v = series.v[i];
        if (!num(v)) return null;
        const g = easeOutBack(stagger(progress, i, n, REVEAL_TAIL, 0.05));
        const x = scaleX(i, n, volRect);
        const h = Math.max(1, (volRect.y + volRect.h - vy(v)) * g);
        const up = (series.c[i] ?? 0) >= (series.o[i] ?? 0);
        return (
          <rect
            key={`v${i}`}
            x={x - cw / 2}
            y={volRect.y + volRect.h - h}
            width={cw}
            height={h}
            fill={up ? C.up : C.down}
            opacity={0.65}
            rx={1}
          />
        );
      })}

      {/* 거래량 20일 이동평균선 (v_ma20) */}
      {series.v_ma20 && (
        <>
          <path
            d={buildLinePath(series.v_ma20, count, volRect, vy)}
            fill="none"
            stroke="#FFD60A"
            strokeWidth={2}
            strokeDasharray="4 4"
            opacity={0.85}
          />
          {num(lastVMa20) && (
            <g opacity={segment(progress, 0.5, 0.3)}>
              <circle cx={volRect.x + 130} cy={volRect.y + 20} r={4} fill="#FFD60A" />
              <text
                x={volRect.x + 142}
                y={volRect.y + 24}
                fill="#FFD60A"
                fontSize={14}
                fontWeight={700}
                fontFamily={FONT}
              >
                거래량 20일 이평선: {fmtVolume(lastVMa20 as number)}주
              </text>
            </g>
          )}
        </>
      )}

      {/* 캔들 — 몸통이 가운데에서 세로로 자란다 */}
      {Array.from({ length: count }, (_, i) => {
        const o = series.o[i];
        const h = series.h[i];
        const l = series.l[i];
        const c = series.c[i];
        if (!num(o) || !num(h) || !num(l) || !num(c) || o <= 0 || h <= 0 || l <= 0 || c <= 0) return null;

        const g = easeOutBack(stagger(progress, i, n, REVEAL_TAIL, 0.05));
        const x = scaleX(i, n, priceRect);
        const up = c >= o;
        const color = up ? C.up : C.down;

        const yH = py(h);
        const yL = py(l);
        const mid = (yH + yL) / 2;
        const half = Math.abs(py(c) - py(o)) / 2;

        const bodyH = Math.max(2, half * 2 * g);
        return (
          <g key={`c${i}`} opacity={Math.min(1, g * 1.6)}>
            <line
              x1={x}
              y1={yH}
              x2={x}
              y2={yL}
              stroke={color}
              strokeWidth={Math.max(1.5, cw * 0.14)}
            />
            <rect
              x={x - cw / 2}
              y={mid - bodyH / 2}
              width={cw}
              height={bodyH}
              fill={up ? C.up : C.down}
              stroke={color}
              strokeWidth={1.5}
              rx={1}
            />
          </g>
        );
      })}

      {/* 네이버 증권 4대 이동평균선 (캔들 위에 선명하게 렌더링) */}
      {maLines.map((line) => {
        const t = segment(progress, line.start, line.dur);
        if (t <= 0) return null;
        const upto = Math.max(2, Math.round(count * t));
        const d = buildLinePath(line.values, upto, priceRect, py);
        if (!d) return null;
        return (
          <path
            key={line.key}
            d={d}
            fill="none"
            stroke={line.color}
            strokeWidth={line.width}
            strokeLinejoin="round"
            strokeLinecap="round"
            opacity={0.92}
          />
        );
      })}

      {/* 4대 이동평균선 라인 우측 끝 인라인 꼬리표 (선 색상과 명칭 즉각 식별) */}
      {maLines.map((line) => {
        const lastVal = line.values[line.values.length - 1];
        if (!num(lastVal)) return null;
        const lastY = py(lastVal);
        const lastX = scaleX(line.values.length - 1, n, priceRect);
        return (
          <g key={`inline-tag-${line.key}`} opacity={0.95}>
            <rect
              x={lastX - 26}
              y={lastY - 11}
              width={52}
              height={22}
              rx={5}
              fill={line.color}
              stroke="#0D1117"
              strokeWidth={1.5}
            />
            <text
              x={lastX}
              y={lastY + 4}
              textAnchor="middle"
              fill={isBrightColor(line.color) ? '#0D1117' : '#FFFFFF'}
              fontSize={11}
              fontWeight={900}
              fontFamily={FONT}
            >
              {line.label}
            </text>
          </g>
        );
      })}

      {/* POC 최대 매물대 하이라이트 (캔들 및 이평선보다 상위 레이어에 렌더링되어 가림 100% 방지) */}
      {pocZone && vpIn > 0 && (
        <g opacity={vpIn}>
          {/* 전폭 가로 황금 점선 안내선 */}
          <line
            x1={priceRect.x}
            y1={py(pocZone.price_mid)}
            x2={priceRect.x + priceRect.w}
            y2={py(pocZone.price_mid)}
            stroke="#FFD60A"
            strokeWidth={1.5}
            strokeDasharray="4 4"
            opacity={0.75}
          />
          {/* POC 최대 매물대 고대비 배지: 좌측 볼륨 프로파일 영역에 배치 (캔들과 미충돌, 선명한 고대비) */}
          <g transform={`translate(${priceRect.x + 14}, ${py(pocZone.price_mid) - 14})`}>
            <rect
              x={0}
              y={0}
              width={248}
              height={28}
              rx={6}
              fill="#FFD60A"
              stroke="#0D1117"
              strokeWidth={1.5}
            />
            <text
              x={12}
              y={19}
              fill="#0D1117"
              fontSize={13}
              fontWeight={900}
              fontFamily={FONT}
            >
              ★ 최대 매물대 {fmtPrice(pocZone.price_mid)}원 ({pocZone.pct.toFixed(1)}%)
            </text>
          </g>
        </g>
      )}

      {/* VFX 파티클 효과 */}
      {particles}

      {/* 마지막 가격 태그 (우측 Y축 네이버 증권 스타일) */}
      {shownPrice !== null && tagIn > 0 && (
        <g opacity={tagIn}>
          <rect
            x={priceRect.x + priceRect.w + 8}
            y={py(shownPrice) - 16}
            width={TAG_W}
            height={32}
            fill={C.up}
            rx={6}
          />
          <text
            x={priceRect.x + priceRect.w + 8 + TAG_W / 2}
            y={py(shownPrice) + 6}
            textAnchor="middle"
            fill="#FFFFFF"
            fontSize={18}
            fontWeight={900}
            fontFamily={MONO}
          >
            {fmtPrice(shownPrice)}원
          </text>
        </g>
      )}
    </ChartFrame>
  );
};
