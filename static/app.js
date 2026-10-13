/* stock-pipeline 관리자 콘솔
   원칙: 어떤 요청이 실패해도 화면이 비지 않는다 — 실패는 해당 영역에만 표시한다. */

'use strict';

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

/* ── 포맷 ── */
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

const num = (v, d = 2) => (typeof v === 'number' && Number.isFinite(v)
  ? v.toLocaleString('ko-KR', { minimumFractionDigits: d, maximumFractionDigits: d })
  : '—');

const pct = (v) => (typeof v === 'number' && Number.isFinite(v) ? `${v >= 0 ? '+' : ''}${v.toFixed(2)}%` : '—');

/* ── 상태 ── */
const S = {
  stats: null, health: null,
  runs: [], date: null, items: [],
  view: localStorage.getItem('sp.view') || 'card',
  filter: 'all', q: '',
  jobs: [], jobTimer: null, logTimer: null,
};

/* ── API ── */
async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = (typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)) || msg;
    } catch { /* 본문이 JSON 이 아님 */ }
    throw new Error(`${res.status} · ${msg}`);
  }
  return res.status === 204 ? null : res.json();
}

function toast(msg, kind = 'ok', ms = 4200) {
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.textContent = msg;
  $('#toasts').appendChild(el);
  setTimeout(() => {
    el.style.transition = 'opacity .25s, transform .25s';
    el.style.opacity = '0';
    el.style.transform = 'translateX(14px)';
    setTimeout(() => el.remove(), 260);
  }, ms);
}

/* ═══════════════ 부트 ═══════════════ */
document.addEventListener('DOMContentLoaded', init);

function init() {
  $$('[data-open]').forEach((b) => b.addEventListener('click', () => openSheet(b.dataset.open)));
  $('#modal-close').addEventListener('click', closeModal);
  $('#modal').addEventListener('click', (e) => { if (e.target === $('#modal')) closeModal(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('#modal').hidden) closeModal(); });
  $('#runs-reload').addEventListener('click', () => loadRuns());
  $$('#viewtoggle button').forEach((b) => b.addEventListener('click', () => setView(b.dataset.view)));
  $('#q').addEventListener('input', (e) => { S.q = e.target.value.trim().toLowerCase(); renderItems(); });

  refreshStats();
  loadRuns();
  pollJobs();
  setInterval(() => { if ($('#modal').hidden) { refreshStats(); loadRuns(true); } }, 30000);
  applyHash();
  window.addEventListener('hashchange', applyHash);
}

/* 딥링크 — #diag · #run · #logs · #item/2026-10-12/000650 · #script/... */
function applyHash() {
  const h = location.hash.slice(1);
  if (!h) return;
  const [kind, a, b] = h.split('/');
  if (kind === 'diag') openDiag();
  else if (kind === 'run') openRunDialog();
  else if (kind === 'logs') openLogs();
  else if (kind === 'item' && a && b) openItem(a, b);
  else if (kind === 'script' && a && b) openScript(a, b);
  else if (kind === 'date' && a) selectRun(a);
}

/* ═══════════════ 통계 / 상태 ═══════════════ */
async function refreshStats() {
  try {
    S.stats = await api('/api/stats');
    renderStats();
    renderPills();
  } catch (e) {
    $('#stats').innerHTML =
      `<div class="stat bad" style="grid-column:1/-1">
         <div class="k">서버 연결 실패</div>
         <div class="v bad">—</div>
         <div class="s">${esc(e.message)}</div>
       </div>`;
  }
  try { S.health = await api('/api/health'); renderPills(); } catch { /* 상태는 선택 */ }
}

function renderStats() {
  const s = S.stats;
  if (!s) return;
  const q = s.avg_quality;
  const w = s.whisper || {};
  const free = s.free_disk_gb;

  const tiles = [
    { k: '생성 영상', v: s.video_count, s: `총 ${s.item_count}건${s.long_count ? ` · 장편 ${s.long_count}` : ''}`, c: 'acc', m: 'hot' },
    { k: 'QC 통과', v: `${s.qc_ok_count}/${s.video_count}`, s: 'ffprobe 검증', c: s.qc_ok_count === s.video_count ? 'ok' : 'warn', m: s.qc_ok_count === s.video_count ? 'good' : '' },
    { k: '게시 완료', v: s.published_count, s: 'YouTube', c: s.published_count ? 'ok' : '' },
    { k: '품질 점수', v: q ?? '—', s: s.quality_errors ? `오류 ${s.quality_errors}` : (s.quality_warnings ? `경고 ${s.quality_warnings}` : '이상 없음'), c: q >= 90 ? 'ok' : (q >= 70 ? 'warn' : 'bad'), m: q >= 90 ? 'good' : (q && q < 70 ? 'bad' : '') },
    { k: '다음 실행', v: s.next_run || '—', s: s.launchd_installed ? 'launchd 등록됨' : 'launchd 미등록', vs: true, m: s.launchd_installed ? 'good' : 'bad' },
    { k: 'Whisper', v: w.ready ? '준비' : '미수신', s: `${w.model || ''}${w.fallback_ready ? ' · 폴백 ✓' : ' · 폴백 ✗'}`, c: w.ready && w.fallback_ready ? 'ok' : 'warn' },
    { k: '여유 공간', v: `${free ?? '—'} GB`, s: `output ${fmtB(s.output_bytes)}`, c: free > 50 ? '' : (free > 20 ? 'warn' : 'bad'), m: free > 20 ? '' : 'bad' },
    { k: '마지막 실행', v: s.last_run?.date?.slice(5) || '—', s: s.last_run?.elapsed_sec ? `${s.last_run.elapsed_sec.toFixed(0)}초` : '기록 없음', vs: true },
  ];

  $('#stats').innerHTML = tiles.map((t) => `
    <div class="stat ${t.m || ''}">
      <div class="k">${t.k}</div>
      <div class="v ${t.c || ''}" ${t.vs ? 'style="font-size:17px"' : ''}>${esc(t.v)}</div>
      <div class="s" title="${esc(t.s)}">${esc(t.s)}</div>
    </div>`).join('');

  // 경고 배너 — 설정 누락만. 실패가 아니라 "확인이 필요한 상태".
  const miss = Object.entries(s.env_keys || {}).filter(([, v]) => !v).map(([k]) => k);
  const boxes = [];
  if (miss.length) {
    boxes.push(`<div class="banner">
      <b>환경 설정 일부 미완료</b> — ${esc(miss.join(', '))} 항목이 <code>.env</code> 에 없습니다.
      <div class="row">· YouTube: <code>venv/bin/python3 token_auth.py</code></div>
      <div class="row">· LLM/TTS: <code>.env</code> 의 <code>OPENAI_API_KEY</code> 등</div>
    </div>`);
  }
  if (s.pipeline_running) {
    boxes.push(`<div class="banner" style="background:rgba(100,210,255,.08);border-color:rgba(100,210,255,.28)">
      <b style="color:var(--info)">파이프라인 실행 중</b> — 완료되면 자동으로 갱신됩니다.
    </div>`);
  }
  if (S.health && S.health.whisper && !S.health.whisper.fallback_ready) {
    boxes.push(`<div class="banner">
      <b>Whisper 폴백 모델 미수신</b> — 폴백이 발동하면 1.4GB 를 내려받습니다.
      <div class="row"><code>venv/bin/python3 setup_status.py --prefetch-whisper</code></div>
    </div>`);
  }
  $('#banner').innerHTML = boxes.join('');
}

function renderPills() {
  const s = S.stats, h = S.health;
  const p = [];
  if (s) {
    p.push(s.launchd_installed ? ['ok', 'launchd'] : ['bad', 'launchd 미등록']);
    if (s.pipeline_running) p.push(['', '파이프라인 실행 중']);
    if (s.active_jobs > 0) p.push(['', `작업 ${s.active_jobs}`]);
  }
  if (h) {
    p.push([h.krx && h.llm ? 'ok' : 'warn', '데이터/AI']);
    p.push([h.youtube ? 'ok' : 'warn', 'YouTube']);
  }
  $('#pills').innerHTML = p.map(([c, t]) => `<span class="pill ${c}">${esc(t)}</span>`).join('');
}

/* ═══════════════ 실행 이력 ═══════════════ */
async function loadRuns(quiet = false) {
  try {
    S.runs = await api('/api/runs');
    renderRuns();
    if (!S.date && S.runs.length) selectRun(S.runs[0].date);
    else if (S.date && quiet) refreshItems();
  } catch (e) {
    $('#runs-list').innerHTML =
      `<div style="padding:16px;color:var(--err);font-size:12px">이력 불러오기 실패<br><span style="color:var(--fg-3)">${esc(e.message)}</span></div>`;
  }
}

function renderRuns() {
  if (!S.runs.length) {
    $('#runs-list').innerHTML = '<div style="padding:18px;color:var(--fg-3);font-size:12px">기록이 없습니다</div>';
    return;
  }
  $('#runs-list').innerHTML = S.runs.map((r) => {
    const vids = (r.items || []).filter((i) => i.has_video).length;
    const dot = r.status !== 'ok' ? 'err' : (r.dry_run ? 'warn' : 'ok');
    const errTag = r.error ? '<span class="tag err">오류</span>' : '';
    const dryTag = r.dry_run ? '<span class="tag">dry-run</span>' : '';
    return `<div class="runitem ${r.date === S.date ? 'on' : ''}" onclick="selectRun('${r.date}')">
      <div class="d"><span class="mono">${esc(r.date)}</span><span class="dot ${dot}"></span></div>
      <div class="m">
        <span>${r.item_count ?? 0}건</span>
        <span>영상 ${vids}</span>
        ${r.elapsed_sec ? `<span>${r.elapsed_sec.toFixed(0)}초</span>` : ''}
        ${errTag}${dryTag}
      </div>
    </div>`;
  }).join('');
}

async function selectRun(date) {
  S.date = date;
  renderRuns();
  $('#content').innerHTML = loading('불러오는 중');
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
    $('#content').innerHTML = empty('⚠', '불러오기 실패', e.message);
  }
}

function renderRunHead(run) {
  const okBadge = run.status === 'ok'
    ? (run.dry_run ? '<span class="pill warn">dry-run</span>' : '<span class="pill ok">정상</span>')
    : '<span class="pill bad">오류</span>';
  $('#runhead').innerHTML = `
    <div class="runhead">
      <h2 class="mono">${esc(run.date)}</h2>
      ${okBadge}
      <span class="meta">${esc(run.started_at || '—')} → ${esc(run.finished_at || '미완료')}${
        run.elapsed_sec ? ` · ${run.elapsed_sec.toFixed(1)}초` : ''}</span>
      <div class="spacer"></div>
      <button class="btn danger sm" onclick="confirmDeleteRun('${run.date}')">이 날짜 삭제</button>
    </div>
    ${run.error ? `<div class="banner"><b>실행 오류</b><div class="row mono" style="margin-top:4px">${esc(run.error)}</div></div>` : ''}`;
}

const loading = (t) => `<div class="empty"><div class="ico">◐</div><div class="t">${esc(t)}…</div></div>`;
const empty = (ico, t, d) =>
  `<div class="empty"><div class="ico">${ico}</div><div class="t">${esc(t)}</div>${d ? `<div style="font-size:12px">${esc(d)}</div>` : ''}</div>`;

/* ═══════════════ 항목 ═══════════════ */
function setView(v) {
  S.view = v;
  localStorage.setItem('sp.view', v);
  $$('#viewtoggle button').forEach((b) => b.classList.toggle('on', b.dataset.view === v));
  renderItems();
}

const FILTERS = [
  ['all', '전체'], ['published', '게시됨'], ['rendered', '렌더완료'],
  ['pending', '미렌더'], ['blocked', '차단'],
];

function renderItems() {
  $('#filters').innerHTML = FILTERS
    .map(([k, l]) => `<button class="chip ${S.filter === k ? 'on' : ''}" onclick="setFilter('${k}')">${l}</button>`).join('');

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
    $('#content').innerHTML = empty('📭', '생성된 콘텐츠가 없습니다', '상단 [▶ 배치 실행] 으로 새 영상을 만드세요.');
    return;
  }
  if (!list.length) {
    $('#content').innerHTML = empty('🔍', '조건에 맞는 항목이 없습니다');
    return;
  }
  $('#content').innerHTML = S.view === 'table'
    ? `<table class="table">${tableHead()}<tbody>${list.map(tableRow).join('')}</tbody></table>`
    : `<div class="grid">${list.map(card).join('')}</div>`;
}

function setFilter(k) { S.filter = k; renderItems(); }

function badges(it) {
  let b = '';
  if (it.blocked) b += '<span class="tag-badge b-block">⛔ 검증 차단</span>';
  else if (it.published_video_id) b += '<span class="tag-badge b-pub">▶ 게시됨</span>';
  else if (it.video) b += '<span class="tag-badge b-render">● 렌더 완료</span>';
  else b += '<span class="tag-badge b-none">○ 미렌더</span>';
  if (it.video && it.qc && it.qc.duration) b += `<span class="tag-badge b-dur">${dur(it.qc.duration)}</span>`;
  return b;
}

function card(it) {
  if (it._err) return `<div class="card"><div class="card-body">
    <div class="cb-name">${esc(it.name || it.ticker)}</div>
    <div style="color:var(--err);font-size:12px">불러오기 실패: ${esc(it._err)}</div></div></div>`;

  const c = it.candidate || {}, sc = it.script || {}, q = it.qc || {};
  const chg = c.change_rate ?? 0;
  const cls = chg >= 0 ? 'up' : 'down';

  return `<div class="card">
    <div class="thumb" onclick="openItem('${it.date}','${it.ticker}')">
      ${it.video_url
        ? `<img loading="lazy" src="${it.thumb_url}" alt="" onerror="this.style.opacity=0">`
        : '<div class="none"><span style="font-size:22px;opacity:.5">🎬</span><span>렌더된 영상 없음</span></div>'}
      ${badges(it)}
      ${it.video_url ? '<div class="overlay"><div>▶</div></div>' : ''}
    </div>
    <div class="card-body">
      <div class="cb-top">
        <div>
          <div class="cb-name">${esc(sc.name || c.name || it.name || it.ticker)}</div>
          <div class="cb-tick">${esc(it.ticker)}${c.score != null ? ` · 점수 ${c.score.toFixed(1)}` : ''}</div>
        </div>
        <div>
          <div class="cb-chg ${cls}">${pct(chg)}</div>
          <div class="cb-px">${c.close ? Number(c.close).toLocaleString('ko-KR') + '원' : '—'}</div>
        </div>
      </div>
      <div class="quote">${esc(sc.hook || it.long_text?.slice(0, 90) || '대본 없음')}</div>
      <div class="kv">
        ${q.resolution ? `<span>${esc(q.resolution)}</span>` : ''}
        ${it.video_bytes ? `<span>${fmtB(it.video_bytes)}</span>` : ''}
        ${(it.timestamps || []).length ? `<span>자막 ${it.timestamps.length}</span>` : ''}
        ${it.video && q.ok === false ? '<span class="er">QC 실패</span>' : ''}
        ${(it.investors || []).slice(0, 2).map((n) => `<span class="hi">${esc(typeof n === 'string' ? n : (n.name || ''))}</span>`).join('')}
      </div>
      <div class="acts">
        <button class="btn sm primary" onclick="openItem('${it.date}','${it.ticker}')">상세</button>
        <button class="btn sm" onclick="openScript('${it.date}','${it.ticker}')">대본</button>
        <button class="btn sm" onclick="rebuild('${it.date}','${it.ticker}')" ${it.long_text ? '' : 'disabled'}>재빌드</button>
        <button class="btn sm" onclick="publish('${it.date}','${it.ticker}')" ${it.video && !it.published_video_id ? '' : 'disabled'}>게시</button>
      </div>
    </div>
  </div>`;
}

function tableHead() {
  return `<thead><tr>
    <th class="tthumb"></th><th>종목</th><th class="num">등락률</th><th class="num">종가</th>
    <th>상태</th><th>품질</th><th class="num">길이</th><th class="num">용량</th><th></th>
  </tr></thead>`;
}

function tableRow(it) {
  const c = it.candidate || {}, q = it.qc || {};
  const chg = c.change_rate ?? 0;
  const st = it.blocked ? '<span class="pill bad">차단</span>'
    : it.published_video_id ? '<span class="pill ok">게시됨</span>'
    : it.video ? '<span class="pill ok">렌더완료</span>' : '<span class="pill warn">미렌더</span>';
  const qual = it.quality?.score;
  return `<tr>
    <td class="tthumb">${it.video_url ? `<img loading="lazy" src="${it.thumb_url}" onclick="openItem('${it.date}','${it.ticker}')">` : ''}</td>
    <td class="tname">${esc(it.name || it.ticker)}<div class="cb-tick">${esc(it.ticker)}</div></td>
    <td class="num" style="color:${chg >= 0 ? 'var(--up)' : 'var(--down)'}">${pct(chg)}</td>
    <td class="num">${c.close ? Number(c.close).toLocaleString('ko-KR') : '—'}</td>
    <td>${st}</td>
    <td class="num">${qual ?? '—'}</td>
    <td class="num">${q.duration ? dur(q.duration) : '—'}</td>
    <td class="num">${it.video_bytes ? fmtB(it.video_bytes) : '—'}</td>
    <td><button class="btn sm" onclick="openItem('${it.date}','${it.ticker}')">열기</button></td>
  </tr>`;
}

/* ═══════════════ 모달 ═══════════════ */
function openSheet(title, sub, html, foot = '', narrow = false) {
  $('#modal-title').textContent = title;
  $('#modal-sub').textContent = sub || '';
  $('#modal-body').innerHTML = html;
  $('#modal-foot').innerHTML = foot;
  $('#modal-card').className = narrow ? 'modal-card narrow' : 'modal-card';
  $('#modal').hidden = false;
}
function closeModal() {
  $('#modal').hidden = true;
  if (S.logTimer) { clearInterval(S.logTimer); S.logTimer = null; }
}

/* ── 배치 실행 ── */
function openRunDialog() {
  const running = S.stats?.pipeline_running || S.jobs.some((j) => j.status === 'running');
  openSheet('배치 실행', 'main_orchestrator.py 실행', `
    ${running ? '<div class="banner"><b>이미 실행 중입니다</b><div class="row">완료될 때까지 기다려주세요.</div></div>' : ''}
    <div class="field-row">
      <label>종목 코드 (비우면 스크리닝 자동 선정)</label>
      <input class="field" id="runTickers" placeholder="예: 000650,001210,012170" ${running ? 'disabled' : ''}>
      <div class="help">쉼표 구분 · 최대 10종목 · 비우면 야간 배치와 동일하게 자동 선정합니다</div>
    </div>
    <label class="check"><input type="checkbox" id="runNoPub" checked ${running ? 'disabled' : ''}>
      <div><div class="t">게시하지 않기</div><div class="d">렌더·QC·아카이브까지만. YouTube 업로드를 하지 않습니다 (권장)</div></div></label>
    <label class="check"><input type="checkbox" id="runDry" ${running ? 'disabled' : ''}>
      <div><div class="t">드라이런</div><div class="d">대본까지만 생성하고 렌더·게시를 생략합니다 (검증용)</div></div></label>
    <div class="banner" style="background:rgba(100,210,255,.07);border-color:rgba(100,210,255,.25)">
      <b style="color:var(--info)">예상 소요</b>
      <div class="row">· 대본 생성 (LLM) 약 4~6분 · TTS+자막 약 2분 · 4K 렌더 약 3~4분/종목</div>
      <div class="row">· LLM API 비용이 발생합니다</div>
    </div>
  `, `<button class="btn ghost" onclick="closeModal()">취소</button>
      <button class="btn primary" id="runGo" onclick="startRun()" ${running ? 'disabled' : ''}>실행</button>`, true);
}

async function startRun() {
  const btn = $('#runGo');
  btn.disabled = true; btn.textContent = '시작 중…';
  try {
    const r = await api('/api/actions/run', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tickers: $('#runTickers').value,
        no_publish: $('#runNoPub').checked,
        dry_run: $('#runDry').checked,
      }),
    });
    closeModal();
    toast('배치 실행을 시작했습니다', 'ok');
    pollJobs(true);
  } catch (e) {
    toast('실행 실패: ' + e.message, 'err', 8000);
    btn.disabled = false; btn.textContent = '실행';
  }
}

/* ── 진단 ── */
async function openDiag() {
  openSheet('환경 진단', '설정 누락의 원인 추적', loading('확인 중'));
  let d;
  try { d = await api('/api/diagnostics'); }
  catch (e) { $('#modal-body').innerHTML = empty('⚠', '진단 실패', e.message); return; }

  const yn = (ok) => `<span class="v ${ok ? 'ok' : 'no'}">${ok ? '정상' : '미설정'}</span>`;
  const keys = Object.entries(d.env_keys || {});
  $('#modal-body').innerHTML = `
    <div class="section"><h4>API 키</h4><div class="kvlist">
      ${keys.map(([k, v]) => `<div class="kvrow"><span class="k">${esc(k)}</span>${yn(v)}</div>`).join('')}
      <div class="kvrow"><span class="k">YouTube 연결</span><span class="v ${d.youtube_channel ? 'ok' : 'no'}">${esc(d.youtube_channel || '연결 안 됨')}</span></div>
    </div></div>

    <div class="section"><h4>실행 환경</h4><div class="kvlist">
      <div class="kvrow"><span class="k">launchd</span>${yn(d.launchd)}${d.launchd_pid ? `<span class="k mono">PID ${d.launchd_pid}</span>` : ''}</div>
      <div class="kvrow"><span class="k">파이프라인</span><span class="v ${d.pipeline_running ? '' : 'ok'}">${d.pipeline_running ? '실행 중' : '대기'}</span></div>
      <div class="kvrow"><span class="k">다음 실행</span><span class="v">${esc(d.next_run)}</span></div>
      <div class="kvrow"><span class="k">node</span>${yn(d.node)}</div>
      <div class="kvrow"><span class="k">ffmpeg</span>${yn(d.ffmpeg)}</div>
      <div class="kvrow"><span class="k">remotion</span>${yn(d.remotion)}</div>
      <div class="kvrow"><span class="k">여유 공간</span><span class="v ${d.disk.free_gb < 20 ? 'no' : 'ok'}">${d.disk.free_gb} GB</span></div>
    </div></div>

    <div class="section"><h4>Whisper 모델</h4><div class="kvlist">
      <div class="kvrow"><span class="k">1순위</span><span class="v ${d.whisper.ready ? 'ok' : 'no'}">${d.whisper.ready ? '준비' : '미수신'}</span></div>
      <div class="kvrow"><span class="k">2순위(폴백)</span><span class="v ${d.whisper.fallback_ready ? 'ok' : 'no'}">${d.whisper.fallback_ready ? '준비' : '미수신'}</span></div>
    </div>
    <div class="bodybox mono" style="max-height:120px">${esc(d.whisper.model)}\n${esc(d.whisper.fallback)}</div>
    ${d.whisper.ready && d.whisper.fallback_ready ? '' :
      '<div class="banner"><b>폴백 모델 미수신</b><div class="row"><code>venv/bin/python3 setup_status.py --prefetch-whisper</code></div></div>'}
    </div>

    <div class="section"><h4>경로</h4><div class="bodybox mono" style="max-height:130px">
${Object.entries(d.paths).map(([k, v]) => `${k.padEnd(8)} ${v}`).join('\n')}</div></div>`;

  $('#modal-foot').innerHTML = `<button class="btn" onclick="closeModal()">닫기</button>`;
}

/* ── 작업(Job) 로그 ── */
async function openLogs() {
  openSheet('작업 로그', '장시간 실행되는 작업 현황', loading('확인 중'));
  const render = () => {
    const running = S.jobs.filter((j) => j.status === 'running');
    const past = S.jobs.filter((j) => j.status !== 'running');
    const row = (j) => `<div class="jobrow">
      <div><div class="lbl">${esc(j.label)}</div><div class="step">${esc(j.step)} · ${j.elapsed_sec.toFixed(0)}초 경과</div></div>
      <div class="st ${j.status}">${j.status === 'running' ? '실행 중' : j.status === 'done' ? '완료' : '실패'}</div>
    </div>`;
    $('#modal-body').innerHTML =
      `<div class="section"><h4>진행 중 (${running.length})</h4>
        <div style="display:flex;flex-direction:column;gap:8px">${
          running.length ? running.map(row).join('') : '<div style="color:var(--fg-3);font-size:12px;padding:8px">없음</div>'}</div></div>
       <div class="section"><h4>최근 완료 (${past.length})</h4>
        <div style="display:flex;flex-direction:column;gap:8px">${
          past.length ? past.slice(0, 12).map(row).join('') : '<div style="color:var(--fg-3);font-size:12px;padding:8px">없음</div>'}</div></div>
       ${(S.lastLog || '') ? `<div class="section"><h4>최근 배치 로그</h4><div class="logbox">${esc(S.lastLog)}</div></div>` : ''}`;

    $('#modal-foot').innerHTML = `<button class="btn ghost" onclick="fetchBatchLog()">배치 로그 보기</button>
      <button class="btn" onclick="closeModal()">닫기</button>`;
  };
  await fetchJobs();
  render();
  S.logTimer = setInterval(async () => { await fetchJobs(); render(); }, 3000);
}

async function fetchBatchLog() {
  try {
    const t = await api('/api/actions/log?path=dashboard_run.log');
    S.lastLog = t.split('\n').slice(-160).join('\n');
    toast('로그를 불러왔습니다');
    await openLogs();
  } catch (e) { toast('로그 없음: ' + e.message, 'warn'); }
}

/* ── 항목 상세 ── */
async function openItem(date, ticker) {
  openSheet('불러오는 중', '', loading(''));
  let it;
  try { it = await api(`/api/items/${date}/${ticker}`); }
  catch (e) { $('#modal-body').innerHTML = empty('⚠', '불러오기 실패', e.message); return; }

  const q = it.qc || {}, c = it.candidate || {}, sc = it.script || {};
  const chg = c.change_rate ?? 0;
  const chartUrls = (it.chart_paths || []).map((p) => `/media/chart/${ticker}/${p.split('/').pop()}`);
  const qual = it.quality || {};

  openSheet(`${esc(it.name || ticker)} (${ticker})`, `${date} · ${esc(q.resolution || '')}`, `
    ${it.video_url
      ? `<video controls preload="metadata" poster="${it.thumb_url}" src="${it.video_url}"></video>`
      : empty('🎬', '렌더된 영상 없음', '대본 편집 → 재빌드로 만들 수 있습니다')}
    ${it.audio_url ? `<audio controls preload="none" src="${it.audio_url}"></audio>` : ''}

    <div class="kvlist">
      <div class="kvrow"><span class="k">등락률</span><span class="v" style="color:${chg >= 0 ? 'var(--up)' : 'var(--down)'}">${pct(chg)}</span></div>
      <div class="kvrow"><span class="k">종가</span><span class="v">${c.close ? Number(c.close).toLocaleString('ko-KR') + '원' : '—'}</span></div>
      <div class="kvrow"><span class="k">QC</span><span class="v ${q.ok ? 'ok' : 'no'}">${esc(q.reason || '미검증')}</span></div>
      <div class="kvrow"><span class="k">영상 크기</span><span class="v">${it.video_bytes ? fmtB(it.video_bytes) : '—'}</span></div>
      <div class="kvrow"><span class="k">자막 토큰</span><span class="v">${(it.timestamps || []).length}</span></div>
      <div class="kvrow"><span class="k">게시</span><span class="v">${it.published_video_id ? '<a style="color:var(--info)" target="_blank" href="https://youtu.be/' + esc(it.published_video_id) + '">' + esc(it.published_video_id) + '</a>' : '미게시'}</span></div>
    </div>

    ${it.blocked ? '<div class="banner"><b>검증 차단됨</b> — 대본이 게이트를 통과하지 못해 생산이 중단됐습니다. 대본을 수정 후 재빌드하세요.</div>' : ''}

    ${chartUrls.length ? `<div class="section"><h4>차트</h4>
      <div class="tagwrap">${chartUrls.map((u) => `<img src="${u}" style="width:calc(50% - 5px);border-radius:8px;border:1px solid var(--line)" onerror="this.style.display='none'">`).join('')}</div></div>` : ''}

    ${(qual.issues || []).length ? `<div class="section"><h4>품질 검사 · 점수 ${qual.score ?? '—'}</h4>
      <div style="display:flex;flex-direction:column;gap:6px">
        ${qual.issues.slice(0, 12).map((i) => `<div class="issue ${esc(i.level)}">
          <div class="hd">${esc(i.kind)}</div>${esc(i.message)}${i.fix ? `<div class="fix">→ ${esc(i.fix)}</div>` : ''}
        </div>`).join('')}
      </div></div>` : ''}

    ${(it.sections || []).length ? `<div class="section"><h4>구간 구성</h4><div class="tagwrap">
      ${it.sections.map((x) => `<span class="kv"><span>${esc(x.title || x.id)} · ${x.chars || 0}자</span></span>`).join('')}</div></div>` : ''}

    ${(it.investors || []).length ? `<div class="section"><h4>인용 투자자</h4><div class="tagwrap">
      ${it.investors.map((i) => `<span class="kv"><span class="hi">${esc(typeof i === 'string' ? i : (i.name || ''))}</span></span>`).join('')}</div></div>` : ''}

    ${sc.hook ? `<div class="section"><h4>HOOK</h4><div class="bodybox">${esc(sc.hook)}</div></div>` : ''}
    ${it.long_text ? `<div class="section"><h4>장편 대본 (${it.long_text.length}자)</h4>
      <div class="bodybox" style="max-height:260px">${esc(it.long_text)}</div></div>` : ''}
  `, `
    <button class="btn" onclick="openScript('${date}','${ticker}')">대본 편집</button>
    <button class="btn" onclick="rebuild('${date}','${ticker}')">재빌드</button>
    ${it.video && !it.published_video_id ? `<button class="btn primary" onclick="publish('${date}','${ticker}')">YouTube 게시</button>` : ''}
    <button class="btn ghost danger" onclick="confirmDeleteItem('${date}','${ticker}')">삭제</button>
  `);
}

/* ── 대본 편집 ── */
async function openScript(date, ticker) {
  openSheet('대본', '불러오는 중', loading(''));
  let s;
  try { s = await api(`/api/items/${date}/${ticker}/script`); }
  catch (e) { $('#modal-body').innerHTML = empty('⚠', '대본 없음', e.message); return; }

  const g = s.gate;
  const gateBox = !g ? '' : `<div class="banner" style="background:${g.passed ? 'rgba(50,215,75,.08)' : 'rgba(255,105,97,.08)'};border-color:${g.passed ? 'rgba(50,215,75,.3)' : 'rgba(255,105,97,.3)'}">
      <b style="color:${g.passed ? 'var(--ok)' : 'var(--err)'}">${g.passed ? '✅ 검증 통과' : '⛔ 검증 실패 — 생산 차단됨'}</b>
      <div class="row">한국어 ${g.lint_score ?? '—'}점 (오류 ${g.lint_errors ?? 0}, 경고 ${g.lint_warnings ?? 0}) ·
        조사 오류 ${g.josa_errors ?? 0} · 숫자 ${g.num_checked ?? 0}건 (오류 ${g.num_errors ?? 0})</div>
      <div class="row">자동 교정 ${(g.auto_fixed || []).length}건 · LLM 교정 ${g.proofread_done ? '완료' : '미실시'}</div>
    </div>`;

  openSheet(`대본 편집 · ${esc(s.name || ticker)}`, `${ticker} · ${s.chars}자`, `
    ${gateBox}
    ${(s.sections || []).length ? `<div class="section"><h4>구간</h4><div class="tagwrap">
      ${s.sections.map((x) => `<span class="kv"><span>${esc(x.title || x.id)} · ${x.chars || 0}자</span></span>`).join('')}</div></div>` : ''}
    <div class="section"><h4>본문</h4>
      <textarea class="editor" id="ed" spellcheck="false">${esc(s.text)}</textarea>
      <div style="display:flex;gap:10px;align-items:center;margin-top:8px;font-size:11.5px;color:var(--fg-3)">
        <span id="edStat"></span><span class="spacer" style="flex:1"></span>
        <span>수정 후 [저장 후 재빌드] 하면 TTS·자막·렌더까지 다시 실행됩니다</span>
      </div>
    </div>
    <div id="vdOut"></div>
  `, `
    <button class="btn ghost" onclick="closeModal()">취소</button>
    <button class="btn" onclick="validateScript('${date}','${ticker}')">검증만</button>
    <button class="btn" onclick="saveScript('${date}','${ticker}',false)">저장만</button>
    <button class="btn primary" onclick="saveScript('${date}','${ticker}',true)">저장 후 재빌드</button>
  `);

  const ta = $('#ed');
  const upd = () => { $('#edStat').textContent = `${ta.value.length}자`; };
  ta.addEventListener('input', upd); upd();
}

async function validateScript(date, ticker) {
  const out = $('#vdOut');
  out.innerHTML = '<div class="section"><h4>검증 결과</h4>' + loading('검사 중') + '</div>';
  try {
    const r = await api('/api/actions/validate-script', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date, ticker, text: $('#ed').value }),
    });
    const g = r.gate || {};
    const errs = (g.issues || []).filter((i) => i.level === 'error');
    const warns = (g.issues || []).filter((i) => i.level === 'warn');
    out.innerHTML = `<div class="section"><h4>검증 결과</h4>
      <div class="banner" style="background:${r.passed ? 'rgba(50,215,75,.08)' : 'rgba(255,105,97,.08)'};border-color:${r.passed ? 'rgba(50,215,75,.3)' : 'rgba(255,105,97,.3)'}">
        <b style="color:${r.passed ? 'var(--ok)' : 'var(--err)'}">${r.passed ? '✅ 통과 — 생산 가능' : `⛔ 실패 — 오류 ${errs.length}건`}</b>
        <div class="row">한국어 ${g.lint_score ?? '—'}점 · 조사 오류 ${g.josa_errors ?? 0} · 숫자 ${g.num_checked ?? 0}건</div>
      </div>
      <div style="display:flex;flex-direction:column;gap:6px;margin-top:9px">
        ${errs.concat(warns).slice(0, 14).map((i) => `<div class="issue ${esc(i.level)}">
          <div class="hd">${esc(i.level === 'error' ? '오류' : '경고')} · ${esc(i.kind)}</div>${esc(i.message)}
          ${i.suggestion ? `<div class="fix">→ ${esc(i.suggestion)}</div>` : ''}</div>`).join('')
          || '<div style="color:var(--ok);font-size:12.5px">검출된 문제 없음</div>'}
      </div></div>`;
  } catch (e) {
    out.innerHTML = `<div class="section"><h4>검증 결과</h4><div class="issue error">${esc(e.message)}</div></div>`;
  }
}

async function saveScript(date, ticker, rebuild) {
  const text = $('#ed').value.trim();
  if (!text) return toast('대본이 비어 있습니다', 'err');
  if (rebuild && !confirm('저장 후 TTS → 자막 → 렌더까지 다시 실행합니다.\n수 분에서 10분 이상 소요됩니다.\n계속할까요?')) return;

  try {
    await api(`/api/items/${date}/${ticker}/script`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    toast('대본을 저장했습니다', 'ok');
    if (rebuild) {
      const r = await api(`/api/actions/rebuild/${date}/${ticker}`, { method: 'POST' });
      closeModal();
      toast('재빌드를 시작했습니다 (TTS → 렌더)', 'ok');
      pollJobs(true);
    } else {
      loadRuns(true);
    }
  } catch (e) { toast('저장 실패: ' + e.message, 'err', 8000); }
}

async function rebuild(date, ticker) {
  if (!confirm(`${ticker} 를 재빌드합니다.\nTTS → 자막 → 4K 렌더 → QC 순서로 실행되며 게시하지 않습니다.\n수 분에서 10분 이상 소요됩니다.\n계속할까요?`)) return;
  try {
    await api(`/api/actions/rebuild/${date}/${ticker}`, { method: 'POST' });
    closeModal();
    toast('재빌드 시작 — 상단에서 진행 상황을 확인할 수 있습니다', 'ok', 6000);
    pollJobs(true);
  } catch (e) { toast('재빌드 실패: ' + e.message, 'err', 8000); }
}

async function publish(date, ticker) {
  const name = S.items.find((i) => i.ticker === ticker)?.name || ticker;
  if (!confirm(`${name}(${ticker}) 영상을 YouTube 에 게시합니다.\n\n· 채널에 공개 업로드되며 되돌릴 수 없습니다\n· 기본은 [공개] 상태입니다\n\n진행할까요?`)) return;
  try {
    const r = await api(`/api/actions/publish/${date}/${ticker}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}),
    });
    toast('게시 완료: ' + r.url, 'ok', 7000);
    loadRuns(true);
  } catch (e) { toast('게시 실패: ' + e.message, 'err', 9000); }
}

async function confirmDeleteItem(date, ticker) {
  const withMedia = confirm(`[1/2] ${ticker} 항목을 삭제합니다.\n영상·음원까지 함께 지우려면 확인을 누르세요.`);
  if (!confirm('[2/2] 삭제할까요? 되돌릴 수 없습니다.')) return;
  try {
    await api(`/api/items/${date}/${ticker}?media=${withMedia}`, { method: 'DELETE' });
    closeModal(); toast('삭제했습니다'); selectRun(date);
  } catch (e) { toast('삭제 실패: ' + e.message, 'err'); }
}

async function confirmDeleteRun(date) {
  if (!confirm(`${date} 실행 기록을 삭제합니다. (생성물은 남습니다)`)) return;
  if (!confirm('정말 삭제할까요? 되돌릴 수 없습니다.')) return;
  try {
    await api(`/api/runs/${date}?media=false`, { method: 'DELETE' });
    S.date = null; toast('삭제했습니다'); loadRuns();
  } catch (e) { toast('삭제 실패: ' + e.message, 'err'); }
}

/* ═══════════════ 작업 폴링 ═══════════════ */
async function fetchJobs() {
  try { S.jobs = await api('/api/jobs'); } catch { /* 서버 지연 무시 */ }
  const running = S.jobs.filter((j) => j.status === 'running');
  const chip = $('#jobchip');
  if (running.length) {
    chip.hidden = false;
    $('#jobchip-text').textContent = `${running[0].label} · ${running[0].step}`;
  } else {
    chip.hidden = true;
  }
  $('#jobchip').onclick = openLogs;
}

function pollJobs(now = false) {
  fetchJobs();
  clearInterval(S.jobTimer);
  S.jobTimer = setInterval(async () => {
    const before = S.jobs.filter((j) => j.status === 'running').length;
    await fetchJobs();
    const after = S.jobs.filter((j) => j.status === 'running').length;
    if (before > 0 && after === 0) {
      toast('작업이 끝났습니다 — 목록을 갱신합니다', 'ok');
      refreshStats(); loadRuns(true);
    }
    if (now) return;
  }, 5000);
}
