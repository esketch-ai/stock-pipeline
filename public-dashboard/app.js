/**
 * STOCK ANALYSIS · FOLLOW UP DASHBOARD
 * Modern Dark Fintech UI/UX Application Engine (Revamped)
 * - Date Timeline Navigator
 * - Naver Finance & Toss Direct Linkage
 * - Hangul Chosung Search Algorithm
 * - 3-Way Responsive Views (Grouped by Date, Card Grid, Compact Table)
 */

(function () {
  'use strict';

  // DOM Elements
  const $ = selector => document.querySelector(selector);
  const $$ = selector => document.querySelectorAll(selector);

  // App State
  let rawData = null;
  let activeDate = 'all';         // 'all' or 'YYYY-MM-DD'
  let activeArchetype = 'all';    // 'all' or archetype string
  let activeView = 'grouped';     // 'grouped' | 'card' | 'table'

  // Korean Chosung Constants & Utilities
  const CHOSUNG = [
    'ㄱ', 'ㄲ', 'ㄴ', 'ㄷ', 'ㄸ', 'ㄹ', 'ㅁ', 'ㅂ', 'ㅃ', 'ㅅ',
    'ㅆ', 'ㅇ', 'ㅈ', 'ㅉ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'
  ];

  function getChosung(str) {
    let result = '';
    for (let i = 0; i < str.length; i++) {
      const code = str.charCodeAt(i);
      if (code >= 0xac00 && code <= 0xd7a3) {
        const chosungIndex = Math.floor((code - 0xac00) / 28 / 21);
        result += CHOSUNG[chosungIndex];
      } else {
        result += str.charAt(i);
      }
    }
    return result;
  }

  function isChosungOnly(str) {
    return /^[\u3131-\u314e]+$/.test(str);
  }

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

  const getItemDate = item => {
    return item.baselineDate || (item.createdAt ? item.createdAt.slice(0, 10) : '');
  };

  const formatDisplayDate = dateStr => {
    if (!dateStr) return '';
    const parts = dateStr.split('-');
    if (parts.length === 3) {
      return `${parts[0]}.${parts[1]}.${parts[2]}`;
    }
    return dateStr;
  };

  // Sparkline SVG Generator with Tooltip
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
    const height = 100;
    const padTop = 12;
    const padBottom = 18;
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
    const gradientId = `grad-${item.ticker}-${Math.abs(Math.round(lastPct * 10))}-${Math.random().toString(36).slice(2, 6)}`;

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
              <stop offset="0%" stop-color="${strokeColor}" stop-opacity="0.3"/>
              <stop offset="100%" stop-color="${strokeColor}" stop-opacity="0.0"/>
            </linearGradient>
          </defs>
          <line x1="${padLeft}" y1="${zeroY.toFixed(1)}" x2="${width - padRight}" y2="${zeroY.toFixed(1)}"
                stroke="rgba(255,255,255,0.12)" stroke-dasharray="3 3" stroke-width="1" />
          <path d="${areaCoords}" fill="url(#${gradientId})" />
          <path d="${pathCoords}" fill="none" stroke="${strokeColor}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
          ${pointCircles}
          <text x="${padLeft}" y="${height - 3}" fill="#64748b" font-size="9" font-family="Pretendard">${escapeHtml(points[0].date)}</text>
          <text x="${width - padRight}" y="${height - 3}" fill="#64748b" font-size="9" text-anchor="end" font-family="Pretendard">${escapeHtml(points[points.length - 1].date)}</text>
        </svg>
      </div>
    `;
  }

  // Render KPI Header Summary
  function renderSummary(summary) {
    if (!summary) return;

    $('#kpi-total').textContent = `${summary.totalTracked || 0}편`;
    $('#kpi-total-sub').textContent = `YouTube 전수`;

    const avgReturn = summary.avgReturnPct ?? 0;
    const avgEl = $('#kpi-return');
    avgEl.textContent = percent(avgReturn);
    avgEl.className = `kpi-value ${tone(avgReturn)}`;

    $('#kpi-winrate').textContent = `${(summary.winRatePct ?? 0).toFixed(1)}%`;
    $('#kpi-active').textContent = `${summary.activeQuotes ?? 0}종목`;

    if (summary.targetHitsCount != null) {
      $('#kpi-target-hits').textContent = `목표주가 달성: ${summary.targetHitsCount}건`;
    }

    if (summary.generatedAt) {
      $('#updated-text').textContent = `최근 갱신: ${summary.generatedAt.replace('T', ' ').slice(0, 19)}`;
    }
    if (summary.marketSessionText) {
      $('#market-date').textContent = `${summary.marketSessionText} · 종가 기준: ${summary.marketThrough || ''}`;
    } else if (summary.marketThrough) {
      $('#market-date').textContent = `거래일 종가 기준: ${summary.marketThrough}`;
    }
  }

  // Render Date Timeline Chips
  function renderDateChips(items) {
    const container = $('#date-chips-container');
    if (!items || !items.length) {
      container.innerHTML = `<button class="date-chip active" data-date="all">전체 (0)</button>`;
      return;
    }

    // Count items per date
    const countsByDate = {};
    items.forEach(item => {
      const d = getItemDate(item);
      if (d) countsByDate[d] = (countsByDate[d] || 0) + 1;
    });

    const sortedDates = Object.keys(countsByDate).sort().reverse();
    const today = new Date().toISOString().slice(0, 10);
    const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);

    let html = `
      <button class="date-chip ${activeDate === 'all' ? 'active' : ''}" data-date="all">
        전체보기 <span class="date-chip-badge">${items.length}</span>
      </button>
    `;

    sortedDates.forEach(date => {
      let label = date.slice(5); // MM-DD
      if (date === today) label += ' 오늘';
      else if (date === yesterday) label += ' 어제';

      const isActive = activeDate === date ? 'active' : '';
      html += `
        <button class="date-chip ${isActive}" data-date="${date}">
          📅 ${label} <span class="date-chip-badge">${countsByDate[date]}</span>
        </button>
      `;
    });

    container.innerHTML = html;

    // Attach click events
    container.querySelectorAll('.date-chip').forEach(btn => {
      btn.addEventListener('click', () => {
        activeDate = btn.getAttribute('data-date');
        container.querySelectorAll('.date-chip').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        render();
      });
    });
  }

  // Filter Items Pipeline
  function getFilteredItems() {
    if (!rawData || !rawData.items) return [];

    const searchQuery = ($('#search-input').value || '').trim().toLowerCase();
    const statusFilter = $('#status-filter').value;
    const sortVal = $('#sort-select').value;
    const isChosung = isChosungOnly(searchQuery);

    let items = rawData.items.filter(item => {
      // 1. Date Filter
      if (activeDate !== 'all') {
        const itemDate = getItemDate(item);
        if (itemDate !== activeDate) return false;
      }

      // 2. Archetype Filter
      if (activeArchetype !== 'all') {
        const arch = item.archetype || '';
        if (!arch.includes(activeArchetype)) return false;
      }

      // 3. Status Filter
      const latestPct = item.latest?.changePct;
      if (statusFilter === 'profit') {
        if (latestPct == null || latestPct <= 0) return false;
      } else if (statusFilter === 'loss') {
        if (latestPct == null || latestPct >= 0) return false;
      } else if (statusFilter === 'waiting') {
        if (item.latest != null) return false;
      }

      // 4. Search Filter (Hangul chosung or text)
      if (searchQuery) {
        const name = (item.name || '').toLowerCase();
        const ticker = (item.ticker || '').toLowerCase();

        if (isChosung) {
          const nameChosung = getChosung(name);
          if (!nameChosung.includes(searchQuery)) return false;
        } else {
          if (!name.includes(searchQuery) && !ticker.includes(searchQuery)) return false;
        }
      }

      return true;
    });

    // 5. Sort
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

  // Generate Single Stock Card HTML
  function generateCardHtml(item) {
    const latest = item.latest;
    const currentPct = latest?.changePct;
    const currentClose = latest?.close;
    const baseline = item.baseline;
    const pnlTone = tone(currentPct);
    const itemDate = getItemDate(item);

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

    // Target Progress
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

    // Portal Links
    const naverUrl = item.naverFinanceUrl || `https://finance.naver.com/item/main.naver?code=${item.ticker}`;
    const tossUrl = item.tossUrl || `https://wts.tossinvest.com/stocks/${item.ticker}`;
    const ytUrl = item.youtubeUrl || (item.youtubeId ? `https://youtu.be/${item.youtubeId}` : '#');
    const thumbUrl = item.thumbUrl || (item.youtubeId ? `https://i.ytimg.com/vi/${item.youtubeId}/hqdefault.jpg` : '');

    return `
      <article class="stock-card" data-ticker="${escapeHtml(item.ticker)}">
        <!-- 상단 썸네일 & 메타 정보 -->
        <div class="card-header-row">
          ${thumbUrl ? `
            <a href="${escapeHtml(ytUrl)}" target="_blank" rel="noopener noreferrer" class="card-thumb-wrap" title="YouTube 영상 재생하기">
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
              <span class="stock-date-badge">📅 ${formatDisplayDate(itemDate)}</span>
            </div>
            <div class="stock-name-row">
              <h3 class="stock-name" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</h3>
              <span class="stock-ticker">${escapeHtml(item.ticker)}</span>
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
            <span class="price-sublabel">최근 종가 (${escapeHtml(latest?.date || '대기')})</span>
            <span class="price-num">${money(currentClose)}</span>
          </div>
          <div class="pnl-badge ${pnlTone}">
            <span class="pnl-rate">${percent(currentPct)}</span>
            <span class="pnl-sub">P&amp;L</span>
          </div>
        </div>

        <!-- 🌟 외부 포털 & 유튜브 원클릭 연계 바 (핵심) -->
        <div class="portal-actions-row">
          <a href="${escapeHtml(naverUrl)}" target="_blank" rel="noopener noreferrer" class="naver-btn" title="네이버 증권 실시간 호가/차트/종목토론실 확인">
            <span class="naver-icon">N</span> 네이버 증권
          </a>
          <a href="${escapeHtml(ytUrl)}" target="_blank" rel="noopener noreferrer" class="yt-link-btn" title="유튜브 실제 방송 시청">
            <span>▶</span> YouTube 시청
          </a>
          <a href="${escapeHtml(tossUrl)}" target="_blank" rel="noopener noreferrer" class="toss-btn" title="토스증권 실시간 확인">
            <span>T</span> 토스
          </a>
        </div>

        <!-- 목표가 진척도 게이지 -->
        ${progressHtml}

        <!-- D+N 마일스톤 -->
        <div class="milestones-row">
          ${milestoneChips}
        </div>

        <!-- 스파크라인 차트 -->
        ${generateSparkline(item)}

        <!-- 카드 하단 일별 기록 아코디언 -->
        <div class="card-bottom-actions">
          <details class="history-accordion">
            <summary class="history-toggle">일별 거래 기록 (${item.history?.length || 0}일) ▾</summary>
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
  }

  // 1. Render Grouped View (Date-centric Accordion Groups)
  function renderGroupedView(items) {
    const container = $('#grouped-container');
    if (!items.length) {
      container.innerHTML = `
        <div class="empty-state">
          <p>선택하신 조건에 일치하는 추천 영상이 없습니다.</p>
        </div>
      `;
      return;
    }

    // Group items by date
    const groups = {};
    items.forEach(item => {
      const d = getItemDate(item);
      if (!groups[d]) groups[d] = [];
      groups[d].push(item);
    });

    const sortedDates = Object.keys(groups).sort().reverse();
    const today = new Date().toISOString().slice(0, 10);
    const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);

    let html = '';
    sortedDates.forEach(date => {
      const dateItems = groups[date];
      let dateTitle = `📅 ${formatDisplayDate(date)}`;
      if (date === today) dateTitle += ' (오늘 추천)';
      else if (date === yesterday) dateTitle += ' (어제 추천)';

      // Calculate avg return for this date group
      const pcts = dateItems.map(i => i.latest?.changePct).filter(p => p != null);
      const avgPct = pcts.length ? pcts.reduce((a, b) => a + b, 0) / pcts.length : 0;
      const avgTone = tone(avgPct);

      html += `
        <section class="date-group-section" data-date="${escapeHtml(date)}">
          <div class="date-group-header">
            <div class="date-group-title-wrap">
              <h2 class="date-group-title">${dateTitle}</h2>
              <span class="date-group-badge-count">영상 ${dateItems.length}편</span>
            </div>
            <div class="date-group-stats">
              <span class="date-group-avg ${avgTone}">평균 수익률: ${percent(avgPct)}</span>
              <span class="date-group-toggle-icon">▼</span>
            </div>
          </div>
          <div class="date-group-grid">
            ${dateItems.map(generateCardHtml).join('')}
          </div>
        </section>
      `;
    });

    container.innerHTML = html;

    // Attach group header toggle collapse
    container.querySelectorAll('.date-group-header').forEach(header => {
      header.addEventListener('click', () => {
        header.closest('.date-group-section').classList.toggle('collapsed');
      });
    });

    attachTooltipEvents();
  }

  // 2. Render Cards Grid View
  function renderCardView(items) {
    const container = $('#cards-container');
    if (!items.length) {
      container.innerHTML = `<div class="empty-state"><p>조건에 맞는 종목이 없습니다.</p></div>`;
      return;
    }
    container.innerHTML = items.map(generateCardHtml).join('');
    attachTooltipEvents();
  }

  // 3. Render Table View
  function renderTableView(items) {
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
      const itemDate = getItemDate(item);
      const naverUrl = item.naverFinanceUrl || `https://finance.naver.com/item/main.naver?code=${item.ticker}`;
      const ytUrl = item.youtubeUrl || (item.youtubeId ? `https://youtu.be/${item.youtubeId}` : '#');

      return `
        <tr>
          <td>
            <strong>${escapeHtml(item.name)}</strong>
            <span style="font-size:11px;color:var(--text-sub);margin-left:4px;">${escapeHtml(item.ticker)}</span>
          </td>
          <td>${escapeHtml(formatDisplayDate(itemDate))} (${money(item.baseline)})</td>
          <td>${money(latest?.close)}</td>
          <td class="${pnlTone}" style="font-weight:750;">${percent(currentPct)}</td>
          <td class="up">${percent(item.maxReturnPct)}</td>
          <td class="${tone(m[1])}">${percent(m[1])}</td>
          <td class="${tone(m[3])}">${percent(m[3])}</td>
          <td class="${tone(m[5])}">${percent(m[5])}</td>
          <td class="${tone(m[20])}">${percent(m[20])}</td>
          <td><span class="badge-archetype">${escapeHtml(item.archetype || '-')}</span></td>
          <td>
            <a href="${escapeHtml(naverUrl)}" target="_blank" rel="noopener noreferrer" class="table-naver-btn" title="네이버 증권 바로가기">
              <span>N</span> 네이버
            </a>
          </td>
          <td>
            <a href="${escapeHtml(ytUrl)}" target="_blank" rel="noopener noreferrer" class="table-yt-btn" title="유튜브 시청">
              <span>▶</span> 시청
            </a>
          </td>
        </tr>
      `;
    }).join('');
  }

  // Tooltip Interaction for Chart Dots
  function attachTooltipEvents() {
    const tooltip = $('#chart-tooltip');
    $$('.chart-dot').forEach(dot => {
      dot.addEventListener('mouseenter', () => {
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

    // Update filtered count badge
    const countBadge = $('#filtered-count-badge');
    if (countBadge) {
      countBadge.textContent = `${items.length}개 영상 표시 (전체 ${rawData?.items?.length || 0}개 중)`;
    }

    // Toggle batch controls visibility in grouped view
    const batchControls = $('#batch-controls');
    if (batchControls) {
      batchControls.hidden = (activeView !== 'grouped');
    }

    if (activeView === 'grouped') {
      $('#grouped-container').hidden = false;
      $('#cards-container').hidden = true;
      $('#table-container').hidden = true;
      renderGroupedView(items);
    } else if (activeView === 'card') {
      $('#grouped-container').hidden = true;
      $('#cards-container').hidden = false;
      $('#table-container').hidden = true;
      renderCardView(items);
    } else {
      $('#grouped-container').hidden = true;
      $('#cards-container').hidden = true;
      $('#table-container').hidden = false;
      renderTableView(items);
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
      renderDateChips(rawData.items);

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
    // Search input & clear button
    const searchInput = $('#search-input');
    const searchClear = $('#search-clear');

    searchInput.addEventListener('input', () => {
      searchClear.hidden = !searchInput.value;
      render();
    });

    searchClear.addEventListener('click', () => {
      searchInput.value = '';
      searchClear.hidden = true;
      searchInput.focus();
      render();
    });

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

    // 3-way view toggle
    $('#view-grouped').addEventListener('click', () => {
      activeView = 'grouped';
      $$('.view-btn').forEach(b => b.classList.remove('active'));
      $('#view-grouped').classList.add('active');
      render();
    });

    $('#view-card').addEventListener('click', () => {
      activeView = 'card';
      $$('.view-btn').forEach(b => b.classList.remove('active'));
      $('#view-card').classList.add('active');
      render();
    });

    $('#view-table').addEventListener('click', () => {
      activeView = 'table';
      $$('.view-btn').forEach(b => b.classList.remove('active'));
      $('#view-table').classList.add('active');
      render();
    });

    // Refresh button
    $('#btn-refresh').addEventListener('click', loadData);

    // 일자별 섹션 일괄 펼침 / 모두 접기
    const btnExpandAll = $('#btn-expand-all');
    if (btnExpandAll) {
      btnExpandAll.addEventListener('click', () => {
        $$('.date-group-section').forEach(sec => sec.classList.remove('collapsed'));
      });
    }

    const btnCollapseAll = $('#btn-collapse-all');
    if (btnCollapseAll) {
      btnCollapseAll.addEventListener('click', () => {
        $$('.date-group-section').forEach(sec => sec.classList.add('collapsed'));
      });
    }
  }

  // Initialize
  setupEvents();
  loadData();

  // Background Auto-Refresh every 5 minutes
  setInterval(loadData, 300000);
})();
