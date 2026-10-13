const $ = s => document.querySelector(s);
let data;
const money = n => n == null ? '시세 미수신' : `${n.toLocaleString('ko-KR')}원`;
const percent = n => n == null ? '집계 대기' : `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
const tone = n => n > 0 ? 'up' : n < 0 ? 'down' : 'neutral';
const escape = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function chart(item) {
  if (!item.history.length) return `<p class="empty">${item.latest ? '최신 종가는 위에 표시했습니다. D+1부터의 추이는 후속 거래일에 추가됩니다.' : item.status === 'fetch-error' ? '시세 조회에 실패했습니다. 다음 갱신 시 재시도합니다.' : '시세를 아직 수신하지 못했습니다.'}</p>`;
  const points = [0, ...item.history.map(p => p.changePct)];
  const low = Math.min(...points, -1), high = Math.max(...points, 1);
  const y = v => 105 - (v-low)/(high-low)*90;
  const path = points.map((v,i) => `${i ? 'L':'M'}${10+i/(points.length-1)*430},${y(v)}`).join(' ');
  return `<svg viewBox="0 0 460 130" role="img" aria-label="제작 기준가격 대비 증감률 추이"><line x1="10" x2="440" y1="${y(0)}" y2="${y(0)}" stroke="#596880" stroke-dasharray="4 4"/><path d="${path}" fill="none" stroke="#6ddbd0" stroke-width="2.5"/><text x="10" y="126" fill="#9daec6" font-size="10">${escape(item.baselineDate)}</text><text x="440" y="126" text-anchor="end" fill="#9daec6" font-size="10">${escape(item.latest.date)}</text></svg>`;
}
function render() {
  const term = $('#search').value.trim();
  let items = data.items.filter(i => `${i.name} ${i.ticker}`.includes(term));
  const sort = $('#sort').value;
  if (sort !== 'date') items.sort((a,b) => (a.latest == null)-(b.latest == null) || (sort==='return'? -1:1)*((a.latest?.changePct??0)-(b.latest?.changePct??0)));
  $('#summary').innerHTML = `<div><strong>${data.items.length}</strong><span>제작 기록</span></div><div><strong>${data.items.filter(i=>i.latest).length}</strong><span>최신 종가 확인</span></div><div><strong>${new Set(data.items.map(i=>i.ticker)).size}</strong><span>추적 종목</span></div>`;
  const labels = {'fetch-error':'조회 실패 · 이전 시세 유지','waiting':'후속 거래일 대기','missing-baseline':'기준가격 또는 날짜 확인 필요','no-new-data':'새 거래 시세 없음','pending':'시세 갱신 대기','ok':'시세 조회 완료'};
  $('#cards').innerHTML = items.map(i=>`<article><h2>${escape(i.name)} <small>${escape(i.ticker)}</small></h2><time>제작 기록 ${escape(i.createdAt.replace('T',' '))}${i.createdAtSource==='archive'?' · 아카이브 시각':''}</time><div class="prices"><div><small>영상 기준가격 · ${escape(i.baselineDate||'날짜 미상')}</small><strong>${money(i.baseline)}</strong></div><div><small>최근 종가 · ${escape(i.latest?.date||'대기')}</small><strong>${money(i.latest?.close)}</strong></div></div><div class="change ${tone(i.latest?.changePct)}">${percent(i.latest?.changePct)}</div><div class="milestones">${[1,5,20].map(n=>`<div><span>D+${n}</span><b class="${tone(i.milestones[n])}">${percent(i.milestones[n])}</b></div>`).join('')}</div>${chart(i)}<p class="status">${labels[i.status]||'확인 필요'} · 마지막 조회 ${escape(i.checkedAt?.replace('T',' ')||'없음')}</p><details><summary>일별 가격 기록 보기</summary><table><thead><tr><th>거래일</th><th>종가</th><th>기준 대비</th></tr></thead><tbody>${[...i.history].reverse().map(p=>`<tr><td>${escape(p.date)}</td><td>${money(p.close)}</td><td class="${tone(p.changePct)}">${percent(p.changePct)}</td></tr>`).join('')}</tbody></table></details></article>`).join('') || '<p class="empty">해당 제작 기록이 없습니다.</p>';
}
async function load() {
  try {
    const response = await fetch(`data.json?t=${Date.now()}`, {cache:'no-store'});
    if (!response.ok) throw Error(response.status);
    data = await response.json();
    $('#updated').textContent = `데이터 생성 ${data.generatedAt.replace('T',' ')} · 조회 대상 ${data.marketThrough}까지${data.offline?' · 저장된 이력 표시':''}`;
    $('#policy').textContent = data.pricePolicy;
    render();
  } catch(e) { $('#updated').textContent = '데이터를 불러오지 못했습니다. 잠시 후 새로고침해 주세요.'; }
}
$('#search').addEventListener('input',()=>data&&render());
$('#sort').addEventListener('change',()=>data&&render());
$('#refresh').addEventListener('click',load);
load();
setInterval(load, 300000);
