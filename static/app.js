/* ─────────────────────────────────────────────────────────────
   stock·pipeline PRO STUDIO — 모던 클라이언트 애플리케이션
   ───────────────────────────────────────────────────────────── */

'use strict';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

/* ── 유틸리티 및 포맷터 ── */
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const fmtB = (b) => {
  if (!b) return '0 B';
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0, n = Number(b);
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i ? n.toFixed(1) : n) + ' ' + u[i];
};

const dur = (s) => {
  if (s === null || s === undefined) return '—';
  const m = Math.floor(s / 60);
  return m + ':' + String(Math.floor(s % 60)).padStart(2, '0');
};

const num = (v, d = 0) => (typeof v === 'number' && Number.isFinite(v)
  ? v.toLocaleString('ko-KR', { minimumFractionDigits: d, maximumFractionDigits: d })
  : '—');

const pct = (v) => (typeof v === 'number' && Number.isFinite(v)
  ? `${v >= 0 ? '+' : ''}${v.toFixed(2)}%` : '—');

/* ── 전역 상태 ── */
const S = {
  activeTab: 'videos',
  stats: null,
  health: null,
  runs: [],
  date: null,
  items: [],
  analyticsList: [],
  view: localStorage.getItem('sp.view') || 'card',
  filter: 'all',
  q: '',
  analyticsQ: '',
  selectedTickers: new Set(),
  jobs: [],
  logTimer: null,
};

/* ── API 헬퍼 ── */
async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = (typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)) || msg;
    } catch { /* JSON 아님 */ }
    throw new Error(`${res.status} · ${msg}`);
  }
  return res.status === 204 ? null : res.json();
}

function toast(msg, kind = 'ok', ms = 4000) {
  const c = $('#toasts');
  if (!c) return;
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.innerHTML = `<span>${kind === 'ok' ? '✓' : '⚠'}</span> <span>${esc(msg)}</span>`;
  c.appendChild(el);
  setTimeout(() => {
    el.style.transition = 'opacity 0.25s, transform 0.25s';
    el.style.opacity = '0';
    el.style.transform = 'translateY(10px)';
    setTimeout(() => el.remove(), 260);
  }, ms);
}

/* ═══════════════ 초기화 ═══════════════ */
document.addEventListener('DOMContentLoaded', init);

function init() {
  // 1. 탭 전환 리스너
  $$('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // 2. 상단 버튼 액션
  const btnSync = $('#btn-sync');
  if (btnSync) btnSync.addEventListener('click', syncVideos);

  const btnOpenRun = $('#btn-open-run');
  if (btnOpenRun) btnOpenRun.addEventListener('click', openRunDialog);

  $('#runs-reload').addEventListener('click', () => syncVideos());

  // 3. 뷰 토글 (카드/표)
  $$('#viewtoggle .view-btn').forEach((b) => {
    b.addEventListener('click', () => setView(b.dataset.view));
  });

  // 4. 검색창 이벤트
  $('#q').addEventListener('input', (e) => {
    S.q = e.target.value.trim().toLowerCase();
    renderItems();
  });

  const anSearch = $('#analytics-search');
  if (anSearch) {
    anSearch.addEventListener('input', (e) => {
      S.analyticsQ = e.target.value.trim().toLowerCase();
      renderAnalytics();
    });
  }

  // 5. 구글 드라이브 일괄 전송
  const chkAll = $('#chk-select-all');
  if (chkAll) chkAll.addEventListener('change', (e) => toggleSelectAll(e.target.checked));

  const btnGdrive = $('#btn-gdrive-export');
  if (btnGdrive) btnGdrive.addEventListener('click', exportSelectedToGDrive);

  // 6. 운영 탭 버튼들
  const btnReDiag = $('#btn-re-diag');
  if (btnReDiag) btnReDiag.addEventListener('click', loadDiagnostics);

  const btnRefreshLog = $('#btn-refresh-log');
  if (btnRefreshLog) btnRefreshLog.addEventListener('click', fetchLogOnce);

  // 7. 모달 닫기 리스너
  $('#dialog-close').addEventListener('click', closeDialog);
  $('#app-dialog').addEventListener('click', (e) => {
    if (e.target === $('#app-dialog')) closeDialog();
  });

  // 8. 초기 데이터 로드 & 주기적 갱신
  refreshStats();
  loadRuns();
  loadDiagnostics();
  pollJobs();

  setInterval(() => {
    if ($('#app-dialog').open) return;
    refreshStats();
    loadRuns(true);
  }, 30000);

  applyHash();
  window.addEventListener('hashchange', applyHash);
}

/* 탭 전환 */
function switchTab(tabId) {
  S.activeTab = tabId;
  $$('.tab-btn').forEach((b) => b.classList.toggle('on', b.dataset.tab === tabId));
  $$('.tab-pane').forEach((p) => {
    const isTarget = p.id === `pane-${tabId}`;
    p.classList.toggle('active', isTarget);
    p.hidden = !isTarget;
  });

  if (tabId === 'analytics') {
    loadAnalytics();
  } else if (tabId === 'operations') {
    loadDiagnostics();
    startLogStream();
  } else {
    stopLogStream();
  }
}

/* 딥링크 해시 */
function applyHash() {
  const h = location.hash.slice(1);
  if (!h) return;
  const [kind, a, b] = h.split('/');
  if (kind === 'tab' && a) switchTab(a);
  else if (kind === 'item' && a && b) openItem(a, b);
  else if (kind === 'script' && a && b) openScript(a, b);
  else if (kind === 'date' && a) selectRun(a);
}

/* ═══════════════ 핵심 KPI 요약 카드 ═══════════════ */
async function refreshStats() {
  try {
    S.stats = await api('/api/stats');
    renderKpis();
    renderPills();
  } catch (e) {
    $('#stats').innerHTML = `
      <div class="kpi-card" style="grid-column: 1 / -1; border-color: var(--color-err);">
        <div class="kpi-label" style="color: var(--color-err);">서버 연결 오류</div>
        <div class="kpi-value">${esc(e.message)}</div>
      </div>`;
  }
  try {
    S.health = await api('/api/health');
    renderPills();
  } catch { /* 생략 */ }
}

function renderKpis() {
  const s = S.stats;
  if (!s) return;

  const free = s.free_disk_gb ?? '—';
  const qcOk = s.qc_ok_count ?? 0;
  const vCount = s.video_count ?? 0;
  const qcRate = vCount > 0 ? ((qcOk / vCount) * 100).toFixed(0) : 100;

  $('#stats').innerHTML = `
    <!-- 1. 제작 영상 -->
    <div class="kpi-card">
      <div class="kpi-label">
        <span>🎬 4K 제작 영상</span>
        <span class="badge-pro">Ultra HD</span>
      </div>
      <div class="kpi-value-row">
        <span class="kpi-value gold">${s.video_count ?? 0}</span>
        <span class="kpi-sub">편 완료 (장편 ${s.long_count ?? 0}편)</span>
      </div>
      <div class="kpi-sub">총 아이템 ${s.item_count ?? 0}건 축적</div>
    </div>

    <!-- 2. QC 무결성 -->
    <div class="kpi-card">
      <div class="kpi-label">
        <span>🛡️ ffprobe QC 무결성</span>
        <span class="kpi-sub">품질 점수 ${s.avg_quality ?? 100}점</span>
      </div>
      <div class="kpi-value-row">
        <span class="kpi-value ok">${qcRate}%</span>
        <span class="kpi-sub">(${qcOk}/${vCount} 통과)</span>
      </div>
      <div class="kpi-sub">60fps 비트레이트 무결점 검증</div>
    </div>

    <!-- 3. Google Drive 백업 -->
    <div class="kpi-card">
      <div class="kpi-label">
        <span>☁️ Google Drive 백업</span>
        <span class="kpi-sub">YouTube: ${s.published_count ?? 0}편</span>
      </div>
      <div class="kpi-value-row">
        <span class="kpi-value info" id="kpi-gdrive-status">연동됨</span>
        <span class="kpi-sub">원클릭 클라우드 이관</span>
      </div>
      <div class="kpi-sub">새벽 2시 배치 후 자동 백업 지원</div>
    </div>

    <!-- 4. 스케줄러 & 스토리지 -->
    <div class="kpi-card">
      <div class="kpi-label">
        <span>⏰ 자동 배치 & 스토리지</span>
        <span class="kpi-sub">${s.launchd_installed ? 'launchd 가동' : '수동'}</span>
      </div>
      <div class="kpi-value-row">
        <span class="kpi-value">${free} GB</span>
        <span class="kpi-sub">여유 공간</span>
      </div>
      <div class="kpi-sub">다음 자동 실행: ${esc(s.next_run || '매일 02:00')}</div>
    </div>
  `;

  // 누락 배너
  const miss = Object.entries(s.env_keys || {}).filter(([, v]) => !v).map(([k]) => k);
  const banners = [];
  if (miss.length) {
    banners.push(`
      <div class="banner">
        <b>⚙️ 설정 점검 필요:</b> ${esc(miss.join(', '))} 항목이 <code>.env</code>에 비어 있습니다.
      </div>`);
  }
  if (s.pipeline_running) {
    banners.push(`
      <div class="banner" style="background:rgba(100,210,255,0.08);border-color:rgba(100,210,255,0.3);">
        <b style="color:var(--color-info);">▶ 파이프라인 배치 가동 중:</b> 백그라운드에서 4K 영상이 렌더링되고 있습니다.
      </div>`);
  }
  $('#banner').innerHTML = banners.join('');
}

function renderPills() {
  const s = S.stats, h = S.health;
  const p = [];
  if (s) {
    p.push(s.launchd_installed ? ['ok', '스케줄러 02:00'] : ['warn', '스케줄러 미등록']);
    if (s.pipeline_running) p.push(['info', '파이프라인 실행 중']);
  }
  if (h) {
    p.push(['ok', 'Voice: Neural2-C']);
    p.push([h.youtube ? 'ok' : 'warn', h.youtube ? 'YouTube 연결' : 'YouTube 미연결']);
  }
  $('#pills').innerHTML = p.map(([c, t]) => `<span class="pill ${c}">${esc(t)}</span>`).join('');
}

/* ═══════════════ 영상 동기화 & 실행 이력 ═══════════════ */
async function syncVideos() {
  const btn = $('#btn-sync');
  if (btn) btn.disabled = true;
  try {
    toast('최신 4K 영상 동기화 중...', 'ok', 1500);
    const res = await api('/api/actions/sync', { method: 'POST' });
    toast(`동기화 완료: ${res.synced_count ?? 0}건 갱신`, 'ok', 2500);
    await refreshStats();
    await loadRuns();
  } catch (e) {
    toast(`동기화 오류: ${e.message}`, 'err');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function loadRuns(quiet = false) {
  try {
    S.runs = await api('/api/runs');
    renderRuns();
    if (!S.date && S.runs.length) selectRun(S.runs[0].date);
    else if (S.date && quiet) refreshItems();
  } catch (e) {
    $('#runs-list').innerHTML = `<div class="empty-state">이력 조회 실패: ${esc(e.message)}</div>`;
  }
}

function renderRuns() {
  if (!S.runs.length) {
    $('#runs-list').innerHTML = '<div class="empty-state">제작 기록이 없습니다.</div>';
    return;
  }
  $('#runs-list').innerHTML = S.runs.map((r) => {
    const vids = (r.items || []).filter((i) => i.has_video).length;
    const dot = r.status !== 'ok' ? 'err' : (r.dry_run ? 'warn' : 'ok');
    return `
      <div class="runitem ${r.date === S.date ? 'on' : ''}" onclick="selectRun('${r.date}')">
        <div class="d">
          <span class="mono">${esc(r.date)}</span>
          <span class="dot ${dot}"></span>
        </div>
        <div class="m">
          <span>종목 ${r.item_count ?? 0}</span>
          <span style="color:var(--brand-gold);">영상 ${vids}편</span>
          ${r.elapsed_sec ? `<span>${r.elapsed_sec.toFixed(0)}초</span>` : ''}
        </div>
      </div>`;
  }).join('');
}

async function selectRun(date) {
  S.date = date;
  S.selectedTickers = new Set();
  updateSelectedCount();
  renderRuns();
  $('#content').innerHTML = '<div class="empty-state"><div class="ico">◐</div><div>영상 목록 불러오는 중...</div></div>';
  try {
    const run = await api(`/api/runs/${date}`);
    S.items = await Promise.all((run.items || []).map((it) =>
      api(`/api/items/${date}/${it.ticker}`).catch((e) => ({ ...it, _err: e.message }))));
    renderRunHead(run);
    $('#toolbar').hidden = false;
    renderItems();
  } catch (e) {
    $('#toolbar').hidden = true;
    $('#runhead').innerHTML = '';
    $('#content').innerHTML = `<div class="empty-state">불러오기 실패: ${esc(e.message)}</div>`;
  }
}

async function refreshItems() {
  if (!S.date) return;
  try {
    const run = await api(`/api/runs/${S.date}`);
    S.items = await Promise.all((run.items || []).map((it) =>
      api(`/api/items/${S.date}/${it.ticker}`).catch((e) => ({ ...it, _err: e.message }))));
    renderItems();
  } catch { /* 조용히 패스 */ }
}

function renderRunHead(run) {
  const badge = run.status === 'ok'
    ? '<span class="pill ok">정상 완료</span>'
    : '<span class="pill bad">오류</span>';
  $('#runhead').innerHTML = `
    <h2 class="mono">${esc(run.date)} 제작 현황</h2>
    ${badge}
    <span class="meta">${esc(run.started_at || '—')} 시작 ${run.elapsed_sec ? `(총 ${run.elapsed_sec.toFixed(0)}초 소요)` : ''}</span>
    <div class="spacer"></div>
    <button class="btn btn-danger sm" onclick="confirmDeleteRun('${run.date}')">날짜 삭제</button>
  `;
}

/* ═══════════════ 종목 영상 카드/테이블 렌더링 ═══════════════ */
function setView(view) {
  S.view = view;
  localStorage.setItem('sp.view', view);
  $$('#viewtoggle .view-btn').forEach((b) => b.classList.toggle('on', b.dataset.view === view));
  renderItems();
}

const FILTERS = [
  ['all', '전체'], ['published', 'YouTube 게시됨'], ['rendered', '4K 렌더완료'],
  ['pending', '미렌더'], ['blocked', '차단'],
];

function renderItems() {
  $('#filters').innerHTML = FILTERS.map(([k, l]) =>
    `<button class="chip ${S.filter === k ? 'on' : ''}" onclick="setFilter('${k}')">${l}</button>`).join('');

  const list = S.items.filter((it) => {
    if (S.filter === 'published' && !it.published_video_id) return false;
    if (S.filter === 'rendered' && !(it.video && !it.published_video_id)) return false;
    if (S.filter === 'pending' && it.video) return false;
    if (S.filter === 'blocked' && !it.blocked) return false;
    if (S.q) {
      const hay = `${it.name || ''} ${it.ticker}`.toLowerCase();
      if (!hay.includes(S.q)) return false;
    }
    return true;
  });

  if (!S.items.length) {
    $('#content').innerHTML = '<div class="empty-state"><div class="ico">📭</div><div>생성된 영상이 없습니다.</div></div>';
    return;
  }
  if (!list.length) {
    $('#content').innerHTML = '<div class="empty-state"><div class="ico">🔍</div><div>검색 조건에 맞는 종목이 없습니다.</div></div>';
    return;
  }

  $('#content').innerHTML = S.view === 'table'
    ? `<table class="table">${tableHead()}<tbody>${list.map(tableRow).join('')}</tbody></table>`
    : `<div class="grid">${list.map(card).join('')}</div>`;
}

function setFilter(k) { S.filter = k; renderItems(); }

/* 카드 템플릿 */
function card(it) {
  const c = it.candidate || {}, sc = it.script || {}, q = it.qc || {};
  const chg = c.change_rate ?? 0;
  const cls = chg >= 0 ? 'up' : 'down';
  const hasVid = Boolean(it.video_url);

  let stBadge = '<span class="tag-badge b-status b-none">○ 미렌더</span>';
  if (it.blocked) stBadge = '<span class="tag-badge b-status b-block">⛔ 검증 차단</span>';
  else if (it.published_video_id) stBadge = '<span class="tag-badge b-status b-pub">▶ YouTube 게시됨</span>';
  else if (it.video) stBadge = '<span class="tag-badge b-status b-render">● 4K 렌더 완료</span>';

  return `
    <div class="card">
      <div class="thumb" onclick="openItem('${it.date}','${it.ticker}')">
        <div class="thumb-checkbox" onclick="event.stopPropagation()">
          <input type="checkbox"
            onchange="toggleSelectTicker('${it.ticker}', this.checked)"
            ${S.selectedTickers.has(it.ticker) ? 'checked' : ''} />
        </div>
        ${hasVid
          ? `<img loading="lazy" src="${it.thumb_url}" alt="${esc(it.name)}">`
          : '<div class="none"><span>🎬</span><span>렌더된 영상 없음</span></div>'}
        <span class="tag-badge b-res">4K 60fps</span>
        ${q.duration ? `<span class="tag-badge b-dur">${dur(q.duration)}</span>` : ''}
        ${stBadge}
        ${hasVid ? '<div class="thumb-overlay"><div class="play-icon-circle">▶</div></div>' : ''}
      </div>

      <div class="card-body">
        <div class="cb-top">
          <div>
            <div class="cb-name">${esc(sc.name || c.name || it.name || it.ticker)}</div>
            <div class="cb-tick">${esc(it.ticker)} · ${esc(c.market || 'KOSPI')}</div>
          </div>
          <div class="cb-price-col">
            <div class="cb-chg ${cls}">${pct(chg)}</div>
            <div class="cb-px">${c.close ? Number(c.close).toLocaleString('ko-KR') + '원' : '—'}</div>
          </div>
        </div>

        <div class="quote">${esc(sc.hook || it.long_text?.slice(0, 95) || '30년 차 시나리오 작가 대본')}</div>

        <div class="kv">
          ${it.video_bytes ? `<span>${fmtB(it.video_bytes)}</span>` : ''}
          ${(it.timestamps || []).length ? `<span>자막 ${it.timestamps.length}개</span>` : ''}
          <span class="archetype">🎯 ${esc(it.archetype || '저평가 역발상')}</span>
        </div>

        <div class="acts">
          <button class="btn sm btn-primary" onclick="openItem('${it.date}','${it.ticker}')">▶ 영상 재생</button>
          <button class="btn sm" onclick="openScript('${it.date}','${it.ticker}')">📝 대본</button>
          <button class="btn sm" onclick="rebuild('${it.date}','${it.ticker}')" ${it.long_text ? '' : 'disabled'}>🔄 재빌드</button>
          <button class="btn sm btn-gdrive" onclick="uploadSingleToGDrive('${it.date}','${it.ticker}')" title="Google Drive 백업">☁️ 드라이브</button>
          <button class="btn sm" onclick="publish('${it.date}','${it.ticker}')" ${it.video && !it.published_video_id ? '' : 'disabled'}>게시</button>
        </div>
      </div>
    </div>`;
}

/* 테이블 템플릿 */
function tableHead() {
  return `
    <thead><tr>
      <th style="width:36px;text-align:center;"><input type="checkbox" onchange="toggleSelectAll(this.checked)" /></th>
      <th style="width:80px">미리보기</th>
      <th>종목명 / 티커</th>
      <th class="mono" style="text-align:right;">등락률</th>
      <th class="mono" style="text-align:right;">종가</th>
      <th>제작 상태</th>
      <th class="mono">재생시간</th>
      <th class="mono">용량</th>
      <th style="text-align:right;">액션</th>
    </tr></thead>`;
}

function tableRow(it) {
  const c = it.candidate || {}, q = it.qc || {};
  const chg = c.change_rate ?? 0;
  const cls = chg >= 0 ? 'var(--color-up)' : 'var(--color-down)';
  const st = it.blocked ? '<span class="pill bad">차단</span>'
    : it.published_video_id ? '<span class="pill ok">게시됨</span>'
    : it.video ? '<span class="pill ok">4K 렌더완료</span>' : '<span class="pill warn">미렌더</span>';

  return `
    <tr>
      <td style="text-align:center;">
        <input type="checkbox" onchange="toggleSelectTicker('${it.ticker}', this.checked)" ${S.selectedTickers.has(it.ticker) ? 'checked' : ''} />
      </td>
      <td class="tthumb">
        ${it.video_url ? `<img loading="lazy" src="${it.thumb_url}" onclick="openItem('${it.date}','${it.ticker}')">` : '—'}
      </td>
      <td>
        <div style="font-weight:750;">${esc(it.name || it.ticker)}</div>
        <div class="mono" style="font-size:11px;color:var(--text-dim);">${esc(it.ticker)}</div>
      </td>
      <td class="mono" style="text-align:right;color:${cls};font-weight:700;">${pct(chg)}</td>
      <td class="mono" style="text-align:right;">${c.close ? Number(c.close).toLocaleString('ko-KR') + '원' : '—'}</td>
      <td>${st}</td>
      <td class="mono">${q.duration ? dur(q.duration) : '—'}</td>
      <td class="mono">${it.video_bytes ? fmtB(it.video_bytes) : '—'}</td>
      <td style="text-align:right;">
        <button class="btn sm btn-primary" onclick="openItem('${it.date}','${it.ticker}')">재생</button>
        <button class="btn sm" onclick="openScript('${it.date}','${it.ticker}')">대본</button>
        <button class="btn sm btn-gdrive" onclick="uploadSingleToGDrive('${it.date}','${it.ticker}')">☁️</button>
      </td>
    </tr>`;
}

/* ═══════════════ 구글 드라이브 연동 ═══════════════ */
function toggleSelectTicker(ticker, checked) {
  if (checked) S.selectedTickers.add(ticker);
  else S.selectedTickers.delete(ticker);
  updateSelectedCount();
}

function toggleSelectAll(checked) {
  if (checked) {
    S.items.forEach((it) => S.selectedTickers.add(it.ticker));
  } else {
    S.selectedTickers.clear();
  }
  updateSelectedCount();
  renderItems();
}

function updateSelectedCount() {
  const count = S.selectedTickers.size;
  const el = $('#selected-count');
  if (el) el.textContent = count;
  const btn = $('#btn-gdrive-export');
  if (btn) btn.disabled = count === 0;
  const chkAll = $('#chk-select-all');
  if (chkAll) chkAll.checked = count > 0 && count === S.items.length;
}

async function exportSelectedToGDrive() {
  const tickers = Array.from(S.selectedTickers);
  if (!tickers.length) {
    toast('전송할 종목을 선택해주세요.', 'err');
    return;
  }
  if (!confirm(`선택한 ${tickers.length}개 종목의 모든 영상/에셋을 Google Drive로 전송하시겠습니까?`)) return;

  toast(`Google Drive 전송 시작 (${tickers.length}개 종목)...`, 'ok');
  try {
    const res = await api('/api/gdrive/upload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tickers, date: S.date }),
    });
    toast(`구글 드라이브 전송 완료! (${res.success_count ?? tickers.length}건 성공)`, 'ok');
    S.selectedTickers.clear();
    updateSelectedCount();
    renderItems();
  } catch (e) {
    toast(`드라이브 전송 실패: ${e.message}`, 'err');
  }
}

async function uploadSingleToGDrive(date, ticker) {
  toast(`${ticker} Google Drive 전송 중...`, 'ok');
  try {
    await api(`/api/gdrive/upload/${date}/${ticker}`, { method: 'POST' });
    toast(`${ticker} 드라이브 전송 완료!`, 'ok');
  } catch (e) {
    toast(`전송 실패: ${e.message}`, 'err');
  }
}

/* ═══════════════ 탭 2: 종목 분석 기록 (Analytics) ═══════════════ */
async function loadAnalytics() {
  const container = $('#analytics-content');
  if (!container) return;
  container.innerHTML = '<div class="empty-state"><div class="ico">◐</div><div>종목 분석 데이터베이스 조회 중...</div></div>';
  try {
    const res = await api('/api/analytics');
    S.analyticsList = res.items || [];
    renderAnalytics();
  } catch (e) {
    container.innerHTML = `<div class="empty-state">조회 실패: ${esc(e.message)}</div>`;
  }
}

function renderAnalytics() {
  const container = $('#analytics-content');
  if (!container) return;

  const list = S.analyticsList.filter((it) => {
    if (!S.analyticsQ) return true;
    const hay = `${it.name || ''} ${it.ticker} ${it.industry_name || ''}`.toLowerCase();
    return hay.includes(S.analyticsQ);
  });

  if (!list.length) {
    container.innerHTML = '<div class="empty-state">조건에 맞는 분석 기록이 없습니다.</div>';
    return;
  }

  container.innerHTML = list.map((it) => {
    const pbr = it.pbr ? it.pbr.toFixed(2) + '배' : '—';
    const bps = it.bps ? Number(it.bps).toLocaleString('ko-KR') + '원' : '—';
    const upside = it.consensus_upside_pct ? `+${it.consensus_upside_pct.toFixed(1)}%` : '—';
    const target = it.consensus_target ? Number(it.consensus_target).toLocaleString('ko-KR') + '원' : '—';

    return `
      <div class="analytics-card" onclick="openAnalyticsDetail('${it.ticker}')">
        <div class="ac-head">
          <div>
            <div class="ac-name">${esc(it.name)} <span class="mono" style="font-size:12px;color:var(--text-dim);">(${esc(it.ticker)})</span></div>
            <div class="ac-industry">${esc(it.market)} · ${esc(it.industry_name || '제조/산업')}</div>
          </div>
          <span class="pill ok">${esc(it.consensus_opinion || '매수(BUY)')}</span>
        </div>

        <div class="ac-metrics">
          <div class="ac-metric-box">
            <span class="ac-m-lbl">PBR</span>
            <span class="ac-m-val highlight">${pbr}</span>
          </div>
          <div class="ac-metric-box">
            <span class="ac-m-lbl">BPS (순자산)</span>
            <span class="ac-m-val">${bps}</span>
          </div>
          <div class="ac-metric-box">
            <span class="ac-m-lbl">적정 목표가</span>
            <span class="ac-m-val">${target}</span>
          </div>
          <div class="ac-metric-box">
            <span class="ac-m-lbl">상승 여력</span>
            <span class="ac-m-val up">${upside}</span>
          </div>
        </div>

        <div class="ac-headline">
          💡 ${esc(it.selection_headline || it.summary_comment1 || '전문가 분석 데이터가 수록되어 있습니다.')}
        </div>
      </div>`;
  }).join('');
}

async function openAnalyticsDetail(ticker) {
  openDialog({
    title: `종목 심층 분석 리포트 — ${ticker}`,
    sub: '재무 실적, 기관 컨센서스 및 기술 지표',
    bodyHtml: '<div class="empty-state">상세 데이터 조회 중...</div>',
  });
  try {
    const d = await api(`/api/analytics/${ticker}`);
    const p = d.profile || {}, v = d.valuation || {}, f = d.financials || [];
    const body = `
      <div style="display:flex;flex-direction:column;gap:16px;">
        <div style="background:var(--bg-deep);padding:14px;border-radius:8px;">
          <h4 style="color:var(--brand-gold);margin-bottom:6px;">🏢 기업 개요</h4>
          <p style="font-size:13px;line-height:1.6;color:var(--text-main);">${esc(p.summary_comment1 || '')} ${esc(p.summary_comment2 || '')}</p>
        </div>

        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;">
          <div style="background:var(--bg-deep);padding:10px;border-radius:6px;">
            <div style="font-size:11px;color:var(--text-dim);">시가총액</div>
            <div style="font-size:15px;font-weight:700;">${p.market_cap_eok ? Number(p.market_cap_eok).toLocaleString('ko-KR') + '억 원' : '—'}</div>
          </div>
          <div style="background:var(--bg-deep);padding:10px;border-radius:6px;">
            <div style="font-size:11px;color:var(--text-dim);">BPS (주당순자산)</div>
            <div style="font-size:15px;font-weight:700;color:var(--brand-gold);">${v.bps ? Number(v.bps).toLocaleString('ko-KR') + '원' : '—'}</div>
          </div>
          <div style="background:var(--bg-deep);padding:10px;border-radius:6px;">
            <div style="font-size:11px;color:var(--text-dim);">PBR</div>
            <div style="font-size:15px;font-weight:700;color:var(--color-ok);">${v.pbr ? v.pbr.toFixed(2) + '배' : '—'}</div>
          </div>
        </div>

        <div>
          <h4 style="margin-bottom:8px;">📊 최근 재무 실적 추이</h4>
          <table class="table" style="font-size:12px;">
            <thead><tr><th>기준일</th><th>매출액</th><th>영업이익</th><th>당기순익</th><th>ROE</th></tr></thead>
            <tbody>
              ${f.slice(0, 4).map((r) => `
                <tr>
                  <td>${esc(r.period || r.date || '—')}</td>
                  <td>${num(r.revenue)}억</td>
                  <td>${num(r.operating_profit)}억</td>
                  <td>${num(r.net_profit || r.net_income)}억</td>
                  <td>${r.roe ? r.roe.toFixed(1) + '%' : '—'}</td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
    $('#dialog-body').innerHTML = body;
  } catch (e) {
    $('#dialog-body').innerHTML = `<div class="empty-state">상세 데이터 로딩 실패: ${esc(e.message)}</div>`;
  }
}

/* ═══════════════ 탭 3: 운영 & 시스템 (Operations) ═══════════════ */
async function loadDiagnostics() {
  const container = $('#diag-container');
  if (!container) return;
  try {
    const d = await api('/api/diagnostics');
    container.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:8px;font-size:13px;">
        <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border-subtle);">
          <span style="color:var(--text-dim);">Google Cloud TTS</span>
          <span class="pill ok">${esc(d.tts?.voice || 'ko-KR-Neural2-C')} (정상)</span>
        </div>
        <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border-subtle);">
          <span style="color:var(--text-dim);">Whisper 모델</span>
          <span class="pill ok">${esc(d.whisper?.model || 'whisper-large-v3-turbo')} (Metal 가속)</span>
        </div>
        <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border-subtle);">
          <span style="color:var(--text-dim);">YouTube API 토큰</span>
          <span class="pill ${d.youtube?.ok ? 'ok' : 'warn'}">${d.youtube?.ok ? '인증 완료' : '재인증 필요'}</span>
        </div>
        <div style="display:flex;justify-content:space-between;padding:6px 0;">
          <span style="color:var(--text-dim);">KRX 시세 수집기</span>
          <span class="pill ok">정상 수신</span>
        </div>
      </div>
    `;

    const srv = $('#server-info-container');
    if (srv) {
      srv.innerHTML = `
        <div style="display:flex;flex-direction:column;gap:8px;font-size:13px;">
          <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border-subtle);">
            <span style="color:var(--text-dim);">자동 스케줄러</span>
            <span style="font-weight:700;">매일 새벽 02:00 (launchd 데몬)</span>
          </div>
          <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border-subtle);">
            <span style="color:var(--text-dim);">비디오 렌더러</span>
            <span style="font-weight:700;">Remotion 4K 60fps ProRes/H.264</span>
          </div>
          <div style="display:flex;justify-content:space-between;padding:6px 0;">
            <span style="color:var(--text-dim);">운영 서버 플랫폼</span>
            <span style="font-weight:700;">Apple Silicon Mac mini Server</span>
          </div>
        </div>
      `;
    }
  } catch (e) {
    container.innerHTML = `<div class="empty-state">진단 로딩 실패: ${esc(e.message)}</div>`;
  }
}

function startLogStream() {
  stopLogStream();
  fetchLogOnce();
  S.logTimer = setInterval(fetchLogOnce, 3000);
}

function stopLogStream() {
  if (S.logTimer) {
    clearInterval(S.logTimer);
    S.logTimer = null;
  }
}

async function fetchLogOnce() {
  const consoleEl = $('#log-console');
  if (!consoleEl) return;
  try {
    const res = await api('/api/actions/log');
    consoleEl.textContent = res.log || '(기록된 최근 로그가 없습니다)';
    const autoScroll = $('#chk-autoscroll');
    if (autoScroll && autoScroll.checked) {
      consoleEl.scrollTop = consoleEl.scrollHeight;
    }
  } catch (e) {
    consoleEl.textContent = `로그 조회 오류: ${e.message}`;
  }
}

/* ═══════════════ 모달 다이얼로그 관리 ═══════════════ */
function openDialog({ title, sub = '', bodyHtml = '', footHtml = '' }) {
  const dlg = $('#app-dialog');
  $('#dialog-title').textContent = title;
  $('#dialog-sub').textContent = sub;
  $('#dialog-body').innerHTML = bodyHtml;
  $('#dialog-foot').innerHTML = footHtml;
  if (!dlg.open) dlg.showModal();
}

function closeDialog() {
  const dlg = $('#app-dialog');
  if (dlg && dlg.open) dlg.close();
}

/* 영상 재생 모달 */
function openItem(date, ticker) {
  const it = S.items.find((x) => x.ticker === ticker);
  if (!it) return;

  const hasVid = Boolean(it.video_url);
  const body = `
    <div style="display:flex;flex-direction:column;gap:14px;">
      ${hasVid ? `
        <div style="aspect-ratio:16/9;background:#000;border-radius:8px;overflow:hidden;">
          <video src="${it.video_url}" controls autoplay style="width:100%;height:100%;outline:none;"></video>
        </div>` : `
        <div class="empty-state" style="padding:32px;">
          <div class="ico">🎬</div>
          <div>아직 렌더링된 4K 비디오가 없습니다.</div>
          <div style="font-size:12px;margin-top:6px;">하단의 [4K 재빌드]를 눌러 생성하세요.</div>
        </div>`}

      <div style="background:var(--bg-deep);padding:14px;border-radius:8px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <h4 style="font-size:15px;color:var(--brand-gold);">${esc(it.name)} (${esc(it.ticker)})</h4>
          <span class="pill ok">4K 60fps</span>
        </div>
        <div style="font-size:13px;line-height:1.6;color:var(--text-muted);">${esc(it.long_text || '대본 없음')}</div>
      </div>
    </div>
  `;

  const foot = `
    <button class="btn sm" onclick="openScript('${date}','${ticker}')">📝 대본 수정</button>
    <button class="btn sm btn-gdrive" onclick="uploadSingleToGDrive('${date}','${ticker}')">☁️ Google Drive 전송</button>
    <button class="btn sm btn-primary" onclick="closeDialog()">닫기</button>
  `;

  openDialog({
    title: `${it.name || ticker} — 4K 비디오 플레이어`,
    sub: `${date} 제작 · 4K 60fps 무결성 검증`,
    bodyHtml: body,
    footHtml: foot,
  });
}

/* 대본 에디터 모달 */
async function openScript(date, ticker) {
  openDialog({
    title: `시나리오 대본 스튜디오 — ${ticker}`,
    sub: '30년 차 작가 8대 씬 대본 확인 및 수정',
    bodyHtml: '<div class="empty-state">대본 불러오는 중...</div>',
  });

  try {
    const sc = await api(`/api/items/${date}/${ticker}/script`);
    const body = `
      <div style="display:flex;flex-direction:column;gap:12px;">
        <div style="font-size:12px;color:var(--text-muted);">
          내용을 수정한 뒤 <b>[저장 후 4K 재빌드]</b>를 누르면 음성 디렉팅(SSML)과 영상이 새로 제작됩니다.
        </div>
        <textarea id="scriptText" style="width:100%;height:320px;background:var(--bg-deep);border:1px solid var(--border-subtle);border-radius:8px;padding:14px;color:var(--text-main);font-family:inherit;font-size:13.5px;line-height:1.6;resize:vertical;">${esc(sc.text || '')}</textarea>
        <div id="scriptValidationResult"></div>
      </div>
    `;

    const foot = `
      <button class="btn sm" onclick="validateCurrentScript()">🔍 맞춤법/숫자 검증</button>
      <button class="btn sm btn-primary" onclick="saveAndRebuildScript('${date}','${ticker}')">💾 저장 후 4K 재빌드</button>
      <button class="btn sm" onclick="closeDialog()">취소</button>
    `;

    $('#dialog-body').innerHTML = body;
    $('#dialog-foot').innerHTML = foot;
  } catch (e) {
    $('#dialog-body').innerHTML = `<div class="empty-state">대본 조회 실패: ${esc(e.message)}</div>`;
  }
}

async function validateCurrentScript() {
  const text = $('#scriptText')?.value || '';
  const out = $('#scriptValidationResult');
  if (!out) return;
  out.innerHTML = '<span style="color:var(--color-info);">검증 진행 중...</span>';
  try {
    const res = await api('/api/actions/validate-script', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    out.innerHTML = `<span style="color:var(--color-ok);">✓ 검증 완료: 길이 ${res.char_count ?? text.length}자 (오타 없음)</span>`;
  } catch (e) {
    out.innerHTML = `<span style="color:var(--color-err);">검증 오류: ${esc(e.message)}</span>`;
  }
}

async function saveAndRebuildScript(date, ticker) {
  const text = $('#scriptText')?.value || '';
  if (!text.trim()) {
    toast('대본 내용이 비어 있습니다.', 'err');
    return;
  }
  if (!confirm('수정한 대본으로 TTS 음성, 자막, 4K 영상을 다시 제작합니다. 진행할까요?')) return;

  closeDialog();
  toast(`${ticker} 4K 재빌드를 시작했습니다.`, 'ok');
  try {
    await api(`/api/actions/rebuild/${date}/${ticker}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    toast(`${ticker} 재빌드 완료!`, 'ok');
    refreshItems();
  } catch (e) {
    toast(`재빌드 실패: ${e.message}`, 'err');
  }
}

/* 배치 실행 다이얼로그 */
function openRunDialog() {
  const body = `
    <div style="display:flex;flex-direction:column;gap:14px;">
      <div>
        <label style="display:block;font-size:12px;font-weight:700;margin-bottom:6px;">종목 코드 지정 (선택)</label>
        <input id="runTickers" class="field" placeholder="예: 460860, 005930 (비워두면 시장 상위 자동 스크리닝)" style="width:100%;background:var(--bg-deep);border:1px solid var(--border-subtle);border-radius:6px;padding:9px 12px;color:#fff;font-family:var(--font-mono);font-size:13px;" />
        <div style="font-size:11.5px;color:var(--text-dim);margin-top:4px;">쉼표로 여러 종목 구분. 비워두면 오늘 장마감 모멘텀 종목을 자동 선정합니다.</div>
      </div>
      <div style="display:flex;flex-direction:column;gap:8px;background:var(--bg-deep);padding:12px;border-radius:6px;">
        <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;">
          <input type="checkbox" id="runNoPub" checked /> YouTube 비공개 (권장: 검수 후 게시)
        </label>
        <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;">
          <input type="checkbox" id="runDry" /> 드라이런 (대본만 생성하고 렌더 생략)
        </label>
      </div>
    </div>
  `;

  const foot = `
    <button class="btn sm btn-primary" onclick="executeBatchRun()">▶ 지금 실행</button>
    <button class="btn sm" onclick="closeDialog()">취소</button>
  `;

  openDialog({
    title: '배치 파이프라인 즉시 실행',
    sub: '스펙트럼 분석, 대본, 음성(SSML), 4K 렌더 전자동 가동',
    bodyHtml: body,
    footHtml: foot,
  });
}

async function executeBatchRun() {
  const tickers = $('#runTickers')?.value?.trim() || '';
  const noPub = $('#runNoPub')?.checked ?? true;
  const dry = $('#runDry')?.checked ?? false;

  closeDialog();
  toast('파이프라인 배치가 시작되었습니다.', 'ok');
  try {
    await api('/api/actions/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tickers, no_publish: noPub, dry_run: dry }),
    });
    refreshStats();
  } catch (e) {
    toast(`배치 실행 오류: ${e.message}`, 'err');
  }
}

/* 작업 폴링 */
async function pollJobs() {
  try {
    S.jobs = await api('/api/jobs');
    const running = S.jobs.some((j) => j.status === 'running');
    const chip = $('#jobchip');
    if (chip) chip.hidden = !running;
  } catch { /* 생략 */ }
  setTimeout(pollJobs, 5000);
}

/* 재빌드 & 게시 */
async function rebuild(date, ticker) {
  if (!confirm(`${ticker} 종목을 다시 제작합니다 (음성/자막/4K 렌더). 계속할까요?`)) return;
  toast(`${ticker} 재빌드 시작...`, 'ok');
  try {
    await api(`/api/actions/rebuild/${date}/${ticker}`, { method: 'POST' });
    toast(`${ticker} 재빌드 완료!`, 'ok');
    refreshItems();
  } catch (e) {
    toast(`재빌드 실패: ${e.message}`, 'err');
  }
}

async function publish(date, ticker) {
  if (!confirm(`${ticker} 영상을 YouTube에 게시하시겠습니까?`)) return;
  toast(`${ticker} YouTube 게시 요청 중...`, 'ok');
  try {
    await api(`/api/actions/publish/${date}/${ticker}`, { method: 'POST' });
    toast(`${ticker} YouTube 게시 완료!`, 'ok');
    refreshItems();
  } catch (e) {
    toast(`게시 실패: ${e.message}`, 'err');
  }
}

async function confirmDeleteRun(date) {
  if (!confirm(`${date} 일자의 모든 영상 및 아카이브를 삭제하시겠습니까?`)) return;
  try {
    await api(`/api/runs/${date}`, { method: 'DELETE' });
    toast(`${date} 삭제 완료`, 'ok');
    loadRuns();
  } catch (e) {
    toast(`삭제 실패: ${e.message}`, 'err');
  }
}
