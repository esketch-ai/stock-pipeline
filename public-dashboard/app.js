/**
 * STOCK ANALYSIS · FOLLOW UP DASHBOARD
 * Modern Dark Fintech UI/UX Application Engine
 */

(function () {
  'use strict';

  // DOM Elements
  const $ = selector => document.querySelector(selector);
  const $$ = selector => document.querySelectorAll(selector);

  // App State
  let rawData = null;
  let activeArchetype = 'all';
  let activeView = 'card'; // 'card' | 'table'

  // Format Helpers
  const money = n => {
    if (n == null || isNaN(n)) return '시세 대기';
    return `${Math.round(n).toLocaleString('ko-KR')}원`;
  };

  const percent = (n, showSign = true) => {
    if (n == null || isNaN(n)) return '대기';
    const sign = showSign && n > 0 ? '+' : '';
    return `${sign}${Number(n).toFixed(2)}%`;
  };

  const tone = n => {
    if (n == null || isNaN(n)) return 'neutral';
    if (n > 0.001) return 'up';
    if (n < -0.001) return 'down';
    return 'neutral';
  };

  const escapeHtml = str => {
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  };

  const formatDate = (isoString) => {
    if (!isoString) return '';
    try {
      const d = new Date(isoString);
      if (isNaN(d.getTime())) return isoString.slice(0, 10);
      const m = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      return `${d.getFullYear()}.${m}.${day}`;
    } catch {
      return isoString.slice(0, 10);
    }
  };

  // Sparkline SVG Generator with Tooltip Interactivity
  function generateSparkline(item) {
    const history = item.history || [];
    if (!history.length) {
      return `
        <div class="chart-container" style="display:flex;align-items:center;justify-content:center;color:var(--text-dim);font-size:12px;">
          <span>${item.latest ? '최신 거래일 종가 수신됨 · D+1 이후 추이 누적 대기' : '추천 후 첫 거래일 도래 대기 중'}</span>
        </div>
      `;
    }

    const baseline = item.baseline;
    const points = [{ date: item.baselineDate, close: baseline, pct: 0 }];
    history.forEach(h => {
      points.push({
        date: h.date,
        close: h.close,
        pct: h.changePct
      });
    });

    const pcts = points.map(p => p.pct);
    let minPct = Math.min(...pcts, -2);
    let maxPct = Math.max(...pcts, 2);
    if (minPct === maxPct) {
      minPct -= 1;
      maxPct += 1;
    }

    const width = 400;
    const height = 110;
    const padTop = 15;
    const padBottom = 20;
    const padLeft = 10;
    const padRight = 10;
    const plotWidth = width - padLeft - padRight;
    const plotHeight = height - padTop - padBottom;

    const getY = pct => padTop + plotHeight - ((pct - minPct) / (maxPct - minPct)) * plotHeight;
    const getX = index => padLeft + (index / (points.length - 1)) * plotWidth;

    const zeroY = getY(0);
    const pathCoords = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${getX(i).toFixed(1)} ${getY(p.pct).toFixed(1)}`).join(' ');

    const lastPct = points[points.length - 1].pct;
    const strokeColor = lastPct >= 0 ? '#f43f5e' : '#3b82f6';
    const gradientId = `grad-${item.ticker}-${Math.abs(Math.round(lastPct * 10))}`;

    // Area fill path
    const areaCoords = `${pathCoords} L ${getX(points.length - 1).toFixed(1)} ${getY(minPct).toFixed(1)} L ${getX(0).toFixed(1)} ${getY(minPct).toFixed(1)} Z`;

    const pointCircles = points.map((p, i) => `
      <circle cx="${getX(i).toFixed(1)}" cy="${getY(p.pct).toFixed(1)}" r="3.5"
              fill="${strokeColor}" stroke="#070b14" stroke-width="1.5"
              class="chart-dot"
              data-date="${escapeHtml(p.date)}"
              data-close="${money(p.close)}"
              data-pct="${percent(p.pct)}" />
    `).join('');

    return `
      <div class="chart-container">
        <svg class="chart-svg" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
          <defs>
            <linearGradient id="${gradientId}" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="${strokeColor}" stop-opacity="0.35"/>
              <stop offset="100%" stop-color="${strokeColor}" stop-opacity="0.0"/>
            </linearGradient>
          </defs>
          <!-- Zero reference line -->
          <line x1="${padLeft}" y1="${zeroY.toFixed(1)}" x2="${width - padRight}" y2="${zeroY.toFixed(1)}"
                stroke="rgba(255,255,255,0.12)" stroke-dasharray="3 3" stroke-width="1" />
          <!-- Area fill -->
          <path d="${areaCoords}" fill="url(#${gradientId})" />
          <!-- Main trend line -->
          <path d="${pathCoords}" fill="none" stroke="${strokeColor}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
          <!-- Data points -->
          ${pointCircles}
          <!-- Date labels -->
          <text x="${padLeft}" y="${height - 4}" fill="#64748b" font-size="9" font-family="Pretendard">${escapeHtml(points[0].date)}</text>
          <text x="${width - padRight}" y="${height - 4}" fill="#64748b" font-size="9" text-anchor="end" font-family="Pretendard">${escapeHtml(points[points.length - 1].date)}</text>
        </svg>
      </div>
    `;
  }

  // Render KPI Summary
  function renderSummary(summary) {
    if (!summary) return;

    $('#kpi-total').textContent = `${summary.totalTracked || 0}편`;
    $('#kpi-total-sub').textContent = `추적 영상 전수`;

    const avgReturn = summary.avgReturnPct ?? 0;
    const avgEl = $('#kpi-return');
    avgEl.textContent = percent(avgReturn);
    avgEl.className = `kpi-value ${tone(avgReturn)}`;

    $('#kpi-winrate').textContent = `${(summary.winRatePct ?? 0).toFixed(1)}%`;
    $('#kpi-active').textContent = `${summary.activeQuotes ?? 0}종목`;
    $('#kpi-active-sub').textContent = `시세 반영 중`;

    if (summary.targetHitsCount != null) {
      $('#kpi-target-hits').textContent = `목표주가 달성: ${summary.targetHitsCount}건`;
    }

    if (summary.generatedAt) {
      $('#updated-text').textContent = `최근 갱신: ${summary.generatedAt.replace('T', ' ').slice(0, 19)}`;
    }
    if (summary.marketThrough) {
      $('#market-date').textContent = `거래일 종가 기준: ${summary.marketThrough}`;
    }
  }

  // Filter and Sort Pipeline
  function getFilteredItems() {
    if (!rawData || !rawData.items) return [];

    const searchQuery = ($('#search-input').value || '').trim().toLowerCase();
    const statusFilter = $('#status-filter').value;
    const sortVal = $('#sort-select').value;

    let items = rawData.items.filter(item => {
      // 1. Text Search
      if (searchQuery) {
        const matchesName = item.name && item.name.toLowerCase().includes(searchQuery);
        const matchesTicker = item.ticker && item.ticker.toLowerCase().includes(searchQuery);
        if (!matchesName && !matchesTicker) return false;
      }

      // 2. Archetype Filter
      if (activeArchetype !== 'all') {
        const arch = item.archetype || '';
        if (!arch.includes(activeArchetype)) return false;
      }

      // 3. Status / Performance Filter
      const latestPct = item.latest?.changePct;
      if (statusFilter === 'profit') {
        if (latestPct == null || latestPct <= 0) return false;
      } else if (statusFilter === 'loss') {
        if (latestPct == null || latestPct >= 0) return false;
      } else if (statusFilter === 'waiting') {
        if (item.latest != null) return false;
      }

      return true;
    });

    // 4. Sort
    items.sort((a, b) => {
      const aPct = a.latest?.changePct ?? -999;
      const bPct = b.latest?.changePct ?? -999;

      if (sortVal === 'recent') {
        return (b.createdAt || '').localeCompare(a.createdAt || '');
      } else if (sortVal === 'return_desc') {
        return bPct - aPct;
      } else if (sortVal === 'return_asc') {
        return aPct - bPct;
      } else if (sortVal === 'name') {
        return (a.name || '').localeCompare(b.name || '', 'ko-KR');
      }
      return 0;
    });

    return items;
  }

  // Render Cards Grid
  function renderCards(items) {
    const container = $('#cards-container');
    if (!items.length) {
      container.innerHTML = `
        <div class="empty-state">
          <p>조건에 일치하는 사후 추적 영상이 없습니다.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = items.map(item => {
      const latest = item.latest;
      const currentPct = latest?.changePct;
      const currentClose = latest?.close;
      const baseline = item.baseline;
      const pnlTone = tone(currentPct);

      // Milestones
      const milestones = item.milestones || {};
      const milestoneChips = [1, 3, 5, 10, 20].map(day => {
        const val = milestones[day];
        const dayTone = tone(val);
        return `
          <div class="milestone-item">
            <span class="milestone-day">D+${day}</span>
            <span class="milestone-val ${dayTone}">${percent(val)}</span>
          </div>
        `;
      }).join('');

      // Target Price & Stop Loss Progress
      let progressHtml = '';
      if (item.targetPrice && baseline) {
        const targetPct = ((item.targetPrice - baseline) / baseline) * 100;
        const currentGain = currentPct ?? 0;
        const progressRate = Math.min(Math.max((currentGain / (targetPct || 1)) * 100, 0), 100);
        const statusClass = item.targetStatusClass || 'ongoing';
        const statusLabel = item.targetStatus || '진행중';

        progressHtml = `
          <div class="target-progress-box">
            <div class="target-meta-row">
              <span class="target-label">목표가 <strong>${money(item.targetPrice)}</strong> (+${targetPct.toFixed(1)}%)</span>
              <span class="target-status-pill ${statusClass}">${escapeHtml(statusLabel)}</span>
            </div>
            <div class="progress-track" title="목표가 도달 진척률 ${progressRate.toFixed(1)}%">
              <div class="progress-fill" style="width: ${progressRate}%;"></div>
            </div>
          </div>
        `;
      } else {
        progressHtml = `
          <div class="target-progress-box">
            <div class="target-meta-row">
              <span class="target-label">스윙 추세 추종 전략</span>
              <span class="target-status-pill none">목표가 미설정</span>
            </div>
          </div>
        `;
      }

      // Thumbnail URL
      const ytUrl = item.youtubeUrl || (item.youtubeId ? `https://youtu.be/${item.youtubeId}` : '#');
      const thumbUrl = item.thumbUrl || (item.youtubeId ? `https://i.ytimg.com/vi/${item.youtubeId}/hqdefault.jpg` : '');

      return `
        <article class="stock-card" data-ticker="${escapeHtml(item.ticker)}">
          <!-- 상단 썸네일 & 메타 정보 -->
          <div class="card-header-row">
            ${thumbUrl ? `
              <a href="${escapeHtml(ytUrl)}" target="_blank" rel="noopener noreferrer" class="card-thumb-wrap" title="유튜브 영상 시청하기">
                <img src="${escapeHtml(thumbUrl)}" alt="${escapeHtml(item.name)}" class="card-thumb-img" loading="lazy" />
                <div class="card-play-overlay">
                  <div class="play-triangle">▶</div>
                </div>
              </a>
            ` : ''}

            <div class="card-title-meta">
              <div class="stock-badges">
                <span class="badge-mkt">${escapeHtml(item.market || 'KRX')}</span>
                <span class="badge-archetype">${escapeHtml(item.archetype || '가치 반등')}</span>
              </div>
              <div class="stock-name-row">
                <h3 class="stock-name" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</h3>
                <span class="stock-ticker">${escapeHtml(item.ticker)}</span>
              </div>
              <div class="stock-created-at">
                추천일: ${escapeHtml(item.baselineDate || formatDate(item.createdAt))}
              </div>
            </div>
          </div>

          <!-- 가격 및 P&L 누적 증감률 -->
          <div class="price-hero-box">
            <div class="price-col">
              <span class="price-sublabel">추천 기준가 (${escapeHtml(item.baselineDate || '')})</span>
              <span class="price-num">${money(baseline)}</span>
            </div>
            <div class="price-arrow">→</div>
            <div class="price-col">
              <span class="price-sublabel">최신 종가 (${escapeHtml(latest?.date || '대기')})</span>
              <span class="price-num">${money(currentClose)}</span>
            </div>
            <div class="pnl-badge ${pnlTone}">
              <span class="pnl-rate">${percent(currentPct)}</span>
              <span class="pnl-sub">P&amp;L</span>
            </div>
          </div>

          <!-- 목표가 진척도 게이지 -->
          ${progressHtml}

          <!-- D+N 마일스톤 -->
          <div class="milestones-row">
            ${milestoneChips}
          </div>

          <!-- 스파크라인 차트 -->
          ${generateSparkline(item)}

          <!-- 카드 하단 바로가기 & 상세 아코디언 -->
          <div class="card-bottom-actions">
            <a href="${escapeHtml(ytUrl)}" target="_blank" rel="noopener noreferrer" class="yt-link-btn">
              <span class="yt-icon">▶</span> YouTube 시청
            </a>
            <details class="history-accordion">
              <summary class="history-toggle">일별 기록 (${item.history?.length || 0}일) ▾</summary>
              <div class="card-history-details">
                <table class="history-mini-table">
                  <thead>
                    <tr>
                      <th>거래일</th>
                      <th>종가</th>
                      <th>기준대비</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${(item.history || []).slice().reverse().map(h => `
                      <tr>
                        <td>${escapeHtml(h.date)}</td>
                        <td>${money(h.close)}</td>
                        <td class="${tone(h.changePct)}">${percent(h.changePct)}</td>
                      </tr>
                    `).join('')}
                  </tbody>
                </table>
              </div>
            </details>
          </div>
        </article>
      `;
    }).join('');

    attachTooltipEvents();
  }

  // Render Table View
  function renderTable(items) {
    const tbody = $('#table-body');
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="12" style="text-align:center;padding:40px;color:var(--text-muted);">조건에 맞는 종목이 없습니다.</td></tr>`;
      return;
    }

    tbody.innerHTML = items.map(item => {
      const latest = item.latest;
      const currentPct = latest?.changePct;
      const pnlTone = tone(currentPct);
      const m = item.milestones || {};
      const ytUrl = item.youtubeUrl || (item.youtubeId ? `https://youtu.be/${item.youtubeId}` : '#');

      return `
        <tr>
          <td>
            <strong>${escapeHtml(item.name)}</strong>
            <span style="font-size:11px;color:var(--text-sub);margin-left:4px;">${escapeHtml(item.ticker)}</span>
          </td>
          <td><span class="badge-archetype">${escapeHtml(item.archetype || '-')}</span></td>
          <td>${escapeHtml(item.baselineDate || '')} (${money(item.baseline)})</td>
          <td>${money(latest?.close)}</td>
          <td class="${pnlTone}" style="font-weight:700;">${percent(currentPct)}</td>
          <td class="up">${percent(item.maxReturnPct)}</td>
          <td class="${tone(m[1])}">${percent(m[1])}</td>
          <td class="${tone(m[3])}">${percent(m[3])}</td>
          <td class="${tone(m[5])}">${percent(m[5])}</td>
          <td class="${tone(m[20])}">${percent(m[20])}</td>
          <td><span class="target-status-pill ${item.targetStatusClass || 'none'}">${escapeHtml(item.targetStatus || '미설정')}</span></td>
          <td>
            <a href="${escapeHtml(ytUrl)}" target="_blank" rel="noopener noreferrer" style="color:var(--color-up);text-decoration:none;font-weight:600;">▶ 시청</a>
          </td>
        </tr>
      `;
    }).join('');
  }

  // Tooltip Interaction for Chart Dots
  function attachTooltipEvents() {
    const tooltip = $('#chart-tooltip');
    $$('.chart-dot').forEach(dot => {
      dot.addEventListener('mouseenter', e => {
        const date = dot.getAttribute('data-date');
        const close = dot.getAttribute('data-close');
        const pct = dot.getAttribute('data-pct');

        tooltip.innerHTML = `<strong>${date}</strong> · ${close} (<span class="${pct.startsWith('+') ? 'up' : 'down'}">${pct}</span>)`;
        tooltip.hidden = false;

        const rect = dot.getBoundingClientRect();
        tooltip.style.left = `${rect.left + window.scrollX}px`;
        tooltip.style.top = `${rect.top + window.scrollY - 10}px`;
      });

      dot.addEventListener('mouseleave', () => {
        tooltip.hidden = true;
      });
    });
  }

  // Master Render
  function render() {
    const items = getFilteredItems();
    if (activeView === 'card') {
      $('#cards-container').hidden = false;
      $('#table-container').hidden = true;
      renderCards(items);
    } else {
      $('#cards-container').hidden = true;
      $('#table-container').hidden = false;
      renderTable(items);
    }
  }

  // Data Loading
  async function loadData() {
    const refreshBtn = $('#btn-refresh');
    refreshBtn.disabled = true;
    try {
      const res = await fetch(`data.json?t=${Date.now()}`, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      rawData = await res.json();

      renderSummary(rawData.summary);
      if (rawData.pricePolicy) {
        $('#policy-text').textContent = rawData.pricePolicy;
      }
      render();
    } catch (err) {
      console.error('Failed to load follow-up data:', err);
      $('#updated-text').textContent = '데이터 로딩 실패 (재시도 대기)';
    } finally {
      refreshBtn.disabled = false;
    }
  }

  // Event Listeners Setup
  function setupEvents() {
    // Search
    $('#search-input').addEventListener('input', render);

    // Archetype filter buttons
    $$('.filter-chip').forEach(btn => {
      btn.addEventListener('click', () => {
        $$('.filter-chip').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        activeArchetype = btn.getAttribute('data-archetype');
        render();
      });
    });

    // Select filters
    $('#status-filter').addEventListener('change', render);
    $('#sort-select').addEventListener('change', render);

    // View toggle
    $('#view-card').addEventListener('click', () => {
      activeView = 'card';
      $('#view-card').classList.add('active');
      $('#view-table').classList.remove('active');
      render();
    });

    $('#view-table').addEventListener('click', () => {
      activeView = 'table';
      $('#view-table').classList.add('active');
      $('#view-card').classList.remove('active');
      render();
    });

    // Refresh button
    $('#btn-refresh').addEventListener('click', loadData);
  }

  // Initialize
  setupEvents();
  loadData();

  // Background Auto-Refresh every 5 minutes
  setInterval(loadData, 300000);
})();
