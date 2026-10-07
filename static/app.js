// HFTA Stack Planner - browser side
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const FT = 3.28084;
const DEFAULT_H = [50, 100, 150, 200];   // feet
const COLOURS = ['#0b5f7a', '#b5562b', '#6a8f2a', '#7a4fa0', '#c08a00', '#2d8a8a', '#a0406a',
                 '#4a6fb5', '#8a6a3a', '#3a8a5a', '#b54a4a', '#5a5a9a', '#9a7a2a', '#2a7a9a', '#111'];
const PRESETS = {
  single: [{ freq: 14.2, ant: '3-Ele' }],
  tri: [{ freq: 14.2, ant: '3-Ele' }, { freq: 21.2, ant: '3-Ele' }, { freq: 28.4, ant: '4-Ele' }],
};
let analysis = null;      // last stack detail (analyse, or best result of a search)
let search = null;        // last optimiser result
let weights = [];         // band weights in effect for ranking
let currentPath = 0, pollTimer = null, currentJob = null;

// ---------- helpers ----------
const units = () => $('#units').value;
const uLabel = u => (u || units()) === 'm' ? 'm' : 'ft';
const conv = v => units() === 'm' ? +(v / FT).toFixed(1) : v;
const fmt = (v, d = 2) => v === null || v === undefined || Number.isNaN(v) ? '—' : (+v).toFixed(d);
const sgn = (v, d = 2) => v === null || v === undefined ? '—' : (v >= 0 ? '+' : '') + v.toFixed(d);
const cls = v => v === null ? '' : v > 0.005 ? 'pos' : v < -0.005 ? 'neg' : '';
const wavelength = f => 983.5712 / f / (units() === 'm' ? FT : 1);   // in display units
function wmean(vals, w) {
  let s = 0, t = 0;
  vals.forEach((v, i) => { if (v !== null && v !== undefined && w[i] > 0) { s += v * w[i]; t += w[i]; } });
  return t ? s / t : null;
}
function bandOf(f) {
  const t = [[1.8,2,'160m'],[3.5,4,'80m'],[5.3,5.4,'60m'],[7,7.3,'40m'],[10.1,10.15,'30m'],[14,14.35,'20m'],
             [18.068,18.168,'17m'],[21,21.45,'15m'],[24.89,24.99,'12m'],[28,29.7,'10m'],[50,54,'6m']];
  const b = t.find(([a, z]) => f >= a && f <= z); return b ? b[2] : null;
}

// ---------- bands ----------
function addBand(b = { freq: 14.2, ant: '3-Ele' }) {
  const tr = document.createElement('tr');
  tr.innerHTML = `<td><input type="checkbox" class="b-on" checked></td>
    <td><input type="number" class="b-f" step="0.001" value="${b.freq}"></td>
    <td><select class="b-a">${ANT_TYPES.map(a => `<option>${a}</option>`).join('')}</select></td>
    <td><input type="number" class="b-boom" step="0.5" min="0" value="${b.boom ?? ''}" placeholder="—"></td>
    <td><input type="number" class="b-w" step="0.1" min="0" value="${b.weight ?? 1}"></td>
    <td><button class="ghost small b-del" title="Remove band">&times;</button></td>`;
  $('.b-a', tr).value = b.ant;
  $('.b-del', tr).onclick = () => { if ($$('#band-rows tr').length > 1) { tr.remove(); refreshChecks(); } };
  $$('input,select', tr).forEach(e => e.addEventListener('input', refreshChecks));
  $('#band-rows').appendChild(tr);
}
function setPreset(name) { $('#band-rows').innerHTML = ''; PRESETS[name].forEach(addBand); refreshChecks(); }
function readBands() {
  return $$('#band-rows tr').map(tr => ({
    enabled: $('.b-on', tr).checked, freq: +$('.b-f', tr).value, antenna_type: $('.b-a', tr).value,
    boom: $('.b-boom', tr).value === '' ? null : +$('.b-boom', tr).value, weight: +$('.b-w', tr).value || 0 }));
}

// ---------- paths ----------
function addPath(name = '') {
  const node = $('#path-tpl').content.firstElementChild.cloneNode(true);
  $('.p-name', node).value = name || `Path ${$$('#paths .path').length + 1}`;
  $('.p-del', node).onclick = () => { if ($$('#paths .path').length > 1) node.remove(); };
  $('.p-pro', node).onchange = e => readFile(e.target, node, 'pro');
  $('.p-prn', node).onchange = e => readFile(e.target, node, 'prn');
  $('#paths').appendChild(node);
}
function readFile(input, node, kind) {
  const f = input.files[0];
  if (!f) return;
  const r = new FileReader();
  r.onload = async () => {
    node.dataset[kind] = r.result;
    const info = $(`.p-${kind}-info`, node);
    info.classList.remove('bad');
    if (kind === 'pro') {
      const lines = r.result.split(/\r?\n/).filter(l => /^\s*-?\d/.test(l));
      const unit = /meter/i.test(r.result.split(/\r?\n/)[0]) ? 'metres' : 'feet';
      info.textContent = `${f.name}: ${lines.length} points, ${unit}`;
      if (lines.length > 148) { info.textContent += ' — too many points (max 148)'; info.classList.add('bad'); }
    } else {
      try {
        const res = await post('/api/prn-bands', { text: r.result });
        node.dataset.bands = res.bands.join(',');
        info.textContent = `${f.name}: ${res.bands.join(' ')}`;
      } catch (e) { info.textContent = e.message; info.classList.add('bad'); }
    }
    refreshChecks();
  };
  r.readAsText(f);
}

// ---------- live checks on the input panel ----------
function refreshChecks() {
  const bands = readBands().filter(b => b.enabled), msgs = [];
  bands.forEach(b => {
    const band = bandOf(b.freq);
    if (!band) msgs.push(`${b.freq} MHz is outside the amateur bands: no FOM.`);
    else if (b.freq < 7) msgs.push(`${band}: below 7 MHz the diffraction method is less reliable (low antennas, steep terrain). Compare with diffraction off.`);
    else if (b.freq > 30) msgs.push(`${band}: above 30 MHz the method is not validated.`);
    $$('#paths .path').forEach(p => {
      if (band && p.dataset.bands && !p.dataset.bands.split(',').includes(band))
        msgs.push(`${$('.p-name', p).value}: the .PRN file has no ${band} column.`);
    });
  });
  const w = $('#band-warning'); w.hidden = !msgs.length; w.textContent = msgs.join(' ');
  // minimum spacing equivalent, from the lowest enabled band
  const fmin = Math.min(...bands.map(b => b.freq).filter(f => f > 0));
  const lam = +$('#min_spacing_lambda').value;
  $('#min_spacing_eq').textContent = Number.isFinite(fmin)
    ? `${(lam * wavelength(fmin)).toFixed(1)} ${uLabel()} (${bandOf(fmin) || fmin + ' MHz'})` : '—';
  $$('.eq').forEach(e => e.hidden = $('#mode').value === 'free' || +$('#n_ant').value < 2);
}

// ---------- antennas ----------
function renderAntRows() {
  const n = +$('#n_ant').value, old = readAnts(), body = $('#ant-rows');
  body.innerHTML = '';
  for (let i = 0; i < n; i++) {
    const o = old[i] || { height: conv(DEFAULT_H[i]), phase: 0, vary: true,
                          min: conv(Math.max(20, DEFAULT_H[i] - 40)), max: conv(DEFAULT_H[i] + 40) };
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${i + 1}</td>
      <td><input type="number" class="a-h" step="1" value="${o.height}"></td>
      <td><select class="a-p"><option value="0">0°</option><option value="180">180°</option></select></td>
      <td><input type="checkbox" class="a-v" ${o.vary ? 'checked' : ''}></td>
      <td><input type="number" class="a-min" step="1" value="${o.min}"></td>
      <td><input type="number" class="a-max" step="1" value="${o.max}"></td>`;
    $('.a-p', tr).value = o.phase;
    body.appendChild(tr);
  }
  refreshChecks();
}
function readAnts() {
  return $$('#ant-rows tr').map(tr => ({
    height: +$('.a-h', tr).value, phase: +$('.a-p', tr).value, vary: $('.a-v', tr).checked,
    min: +$('.a-min', tr).value, max: +$('.a-max', tr).value }));
}

// ---------- azimuth sector ----------
const sector = { profiles: {}, prn: '', bearings: null };
function azFromName(name) {
  const m = name.replace(/\.[^.]+$/, '').match(/(\d{1,3}(?:\.\d+)?)(?!.*\d)/);
  return m ? +m[1] % 360 : null;
}
function readMany(files, cb) {
  let left = files.length; const out = [];
  [...files].forEach(f => { const r = new FileReader(); r.onload = () => { out.push([f.name, r.result]); if (!--left) cb(out); }; r.readAsText(f); });
}
function sectorAzimuths() {
  const c = +$('#sec-centre').value, sp = +$('#sec-spread').value, st = +$('#sec-step').value || 1;
  const azs = [];
  for (let a = c - sp; a <= c + sp + 1e-6; a += st) azs.push(((a % 360) + 360) % 360);
  return azs;
}
function nearestProfile(az) {
  let best = null, d = 1e9;
  for (const k of Object.keys(sector.profiles)) {
    const dd = Math.abs(((+k - az + 540) % 360) - 180);
    if (dd < d) { d = dd; best = k; }
  }
  return d <= 0.51 ? best : null;
}
function stationWeights(azs) {
  const rep = sector.bearings, b = $('#sec-band').value;
  const h = rep?.bands?.[b]?.histogram;
  if (!h) return azs.map(() => 1);
  return azs.map(a => {   // gaussian smoothing, 3 degrees
    let s = 0; for (let k = -15; k <= 15; k++) s += h[((Math.round(a) + k) % 360 + 360) % 360] * Math.exp(-0.5 * (k / 3) ** 2);
    return s;
  });
}
function sectorPaths() {
  if (!$('#sec-on').checked) return [];
  const azs = sectorAzimuths(), mode = $('#sec-mode').value, c = +$('#sec-centre').value, sp = +$('#sec-spread').value || 1;
  let w = mode === 'taper' ? azs.map(a => Math.cos((Math.abs(((a - c + 540) % 360) - 180) / sp) * Math.PI / 2) + 0.2)
        : mode === 'stations' ? stationWeights(azs) : azs.map(() => 1);
  const total = w.reduce((x, y) => x + y, 0) || 1, sw = +$('#sec-weight').value || 0;
  const out = [];
  azs.forEach((a, i) => {
    const k = nearestProfile(a);
    if (k !== null) out.push({ name: `Az ${(+k).toFixed(1).replace(/\.0$/, '')}°`, weight: +(sw * w[i] / total * azs.length).toFixed(4),
                               profile: sector.profiles[k], aoa: sector.prn, azimuth: +k });
  });
  return out;
}
function sectorPreview() {
  if (!$('#sec-on').checked) return;
  const ps = sectorPaths(), missing = sectorAzimuths().filter(a => nearestProfile(a) === null);
  $('#sec-preview').textContent = ps.length
    ? `${ps.length} azimuths: ` + ps.map(p => `${p.name} ×${p.weight.toFixed(2)}`).join(', ') + (missing.length ? ` · no profile for ${missing.map(a => a.toFixed(1)).join(', ')}°` : '')
    : 'Load profiles that cover the sector.';
  $$('.sec-st').forEach(e => e.hidden = $('#sec-mode').value !== 'stations');
}

// ---------- requests ----------
function common() {
  const paths = $$('#paths .path').filter(p => p.dataset.pro).map(p => ({
    name: $('.p-name', p).value, weight: +$('.p-weight', p).value || 0,
    profile: p.dataset.pro || '', aoa: p.dataset.prn || '' })).concat(sectorPaths());
  return {
    units: units(), soil: $('#soil').value, sigma: +$('#sigma').value, epsr: +$('#epsr').value,
    diffraction: $('#diffraction').checked, move_tower: +$('#move_tower').value || 0,
    max_tower: $('#max_tower').value === '' ? null : +$('#max_tower').value,
    min_spacing_lambda: +$('#min_spacing_lambda').value || 0, bands: readBands(), paths };
}
async function post(url, body) {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
function status(msgs, kind = '') {
  const s = $('#status'), list = (Array.isArray(msgs) ? msgs : [msgs]).filter(Boolean);
  s.hidden = !list.length; s.className = 'status ' + kind;
  s.innerHTML = list.map(m => `<div>${m}</div>`).join('');
}
function busy(on) { $('#run-analyse').disabled = on; $('#run-optimise').disabled = on; }

async function runAnalyse(keepSearch = false) {
  status(''); busy(true);
  try {
    const res = await post('/api/analyse', { ...common(), antennas: readAnts() });
    if (!keepSearch) { search = null; $('#opt').hidden = true; }
    weights = keepSearch && search ? weights : res.bands.map(b => b.weight);
    showDetail(res, keepSearch ? 'Selected configuration' : 'Stack detail');
  } catch (e) { status(e.message, 'error'); }
  busy(false);
}

async function runOptimise() {
  status(''); busy(true);
  try {
    const body = { ...common(), antennas: readAnts(), mode: $('#mode').value, step: +$('#step').value,
                   spacing_min: +$('#spacing_min').value, spacing_max: +$('#spacing_max').value };
    const r = await post('/api/optimise', body);
    currentJob = r.job;
    $('#progress').hidden = false; $('#progress-fill').style.width = '0';
    $('#progress-text').textContent = Object.entries(r.combinations).map(([k, v]) => `${k}: ${v} combinations`).join(' · ');
    pollTimer = setInterval(poll, 700);
  } catch (e) { status(e.message, 'error'); busy(false); }
}
async function poll() {
  const j = await (await fetch(`/api/job/${currentJob}`)).json();
  if (j.state === 'running') {
    $('#progress-fill').style.width = (j.total ? 100 * j.done / j.total : 100) + '%';
    $('#progress-text').textContent = j.total ? `${j.phase}: ${j.done} / ${j.total}` : j.phase;
    return;
  }
  clearInterval(pollTimer); $('#progress').hidden = true; busy(false);
  if (j.state === 'error') { status(j.error, j.error === 'Cancelled' ? '' : 'error'); return; }
  search = j.result;
  weights = search.bands.map(b => b.weight);
  buildWeights(); buildMapControls();
  $('#opt').hidden = false;
  showDetail(search, 'Best overall result');
  renderSearch();
}

// ---------- optimiser rendering ----------
function allRows(src = 'all') {
  return search.searches.filter(s => src === 'all' || s.kind === src)
    .flatMap(s => s.rows.map(r => ({ ...r, kind: s.kind, score: wmean(r.b, weights) })));
}
function buildWeights() {
  const el = $('#weights'); el.innerHTML = '';
  $('#weights-card').hidden = search.bands.length < 2;
  search.bands.forEach((b, i) => {
    const row = document.createElement('label'); row.className = 'slider';
    row.innerHTML = `<span>${b.name} <small>${b.antenna}</small></span>
      <input type="range" min="0" max="3" step="0.1" value="${weights[i]}"><output>${weights[i].toFixed(1)}</output>`;
    $('input', row).oninput = e => { weights[i] = +e.target.value; $('output', row).textContent = weights[i].toFixed(1);
                                     renderSearch(); if (analysis) drawFomTable(analysis); };
    el.appendChild(row);
  });
}
function spacingText(h) { return h.length < 2 ? '—' : h.slice(1).map((x, i) => +(x - h[i]).toFixed(1)).join(' / '); }

function renderSearch() {
  if (!search) return;
  const u = uLabel(search.units), rows = allRows('all').filter(r => r.score !== null);
  rows.sort((a, b) => b.score - a.score);
  const best = rows[0], nb = search.bands.length;
  // heights within 0.5 dB of the best (overall score)
  const tol = rows.filter(r => r.score >= best.score - 0.5);
  const ranges = best.h.map((_, k) => `Ant ${k + 1}: ${Math.min(...tol.map(r => r.h[k]))}–${Math.max(...tol.map(r => r.h[k]))} ${u}`).join(' · ');
  const s = search.searches.map(x => `${x.kind === 'free' ? 'free' : 'equal'} ${x.evaluated}` +
    (x.coarse_step ? ` (coarse ${x.coarse_step} ${u} then fine; full grid ${x.full_grid})` : '')).join(', ');
  $('#opt-summary').innerHTML = `<p class="big">Best: ${best.h.join(' / ')} ${u} &nbsp;·&nbsp; FOM ${fmt(best.score)} dB
      ${nb > 1 ? `<small>(${search.bands.map((b, i) => `${b.name} ${fmt(best.b[i])}`).join(', ')})</small>` : ''}</p>
    <p>Heights that stay within 0.5 dB of the best: ${ranges}</p>
    <p class="hint">Calculated: ${s} configurations in ${search.seconds} s. The detail below is the best result at the
      starting band weights. Use the "Use" buttons to analyse any other row.</p>`;
  renderCompare(); renderMatrix(); drawMap();
}

function renderCompare() {
  const kinds = search.searches.map(s => s.kind);
  $('#compare-card').hidden = !(kinds.includes('free') && kinds.includes('equal'));
  if ($('#compare-card').hidden) return;
  const u = uLabel(search.units);
  const top = k => allRows(k).filter(r => r.score !== null).sort((a, b) => b.score - a.score)[0];
  const f = top('free'), e = top('equal'), d = e.score - f.score;
  let h = `<p class="big-line">Cost of equal spacing: <b class="${cls(d)}">${sgn(d)} dB</b> overall.</p>
    <div class="table-wrap"><table class="res"><thead><tr><th>Search</th><th>Heights (${u})</th><th>Spacing</th>`;
  search.bands.forEach(b => h += `<th>${b.name}</th>`);
  h += '<th>Overall</th><th></th></tr></thead><tbody>';
  [['Free spacing', f], ['Equal spacing', e]].forEach(([n, r]) => {
    h += `<tr><td class="l">${n}</td><td>${r.h.join(' / ')}</td><td>${spacingText(r.h)}</td>`;
    r.b.forEach(v => h += `<td>${fmt(v)}</td>`);
    h += `<td><b>${fmt(r.score)}</b></td><td>${useBtn(r.h)}</td></tr>`;
  });
  h += `<tr class="delta"><td class="l">Difference</td><td></td><td></td>`;
  e.b.forEach((v, i) => { const x = v === null || f.b[i] === null ? null : v - f.b[i]; h += `<td class="${cls(x)}">${sgn(x)}</td>`; });
  h += `<td class="${cls(d)}">${sgn(d)}</td><td></td></tr></tbody></table></div>`;
  $('#compare').innerHTML = h; wireUse('#compare');
}

function renderMatrix() {
  const u = uLabel(search.units), src = $('#matrix-src').value, nb = search.bands.length;
  const kinds = search.searches.map(s => s.kind);
  $('#matrix-src').parentElement.hidden = kinds.length < 2;
  const rows = allRows(kinds.length < 2 ? 'all' : src).filter(r => r.score !== null).sort((a, b) => b.score - a.score);
  if (!rows.length) { $('#matrix').innerHTML = '<p class="hint">No results.</p>'; return; }
  const bandBest = search.bands.map((_, i) => Math.max(...rows.map(r => r.b[i] ?? -1e9)));
  const picked = [], key = r => r.h.join(',');
  const add = (label, r) => {
    if (!r) return;
    const ex = picked.find(p => key(p.r) === key(r));
    if (!ex) picked.push({ label, r });
    else if (label.startsWith('Best')) ex.label += ` · ${label.replace('Best for', 'best for')}`;
    else if (!ex.label.startsWith('Best overall')) ex.label += ` (${label})`;
  };
  add('Best overall', rows[0]);
  if (nb > 1) search.bands.forEach((b, i) => add(`Best for ${b.name}`, [...rows].sort((x, y) => (y.b[i] ?? -1e9) - (x.b[i] ?? -1e9))[0]));
  rows.slice(0, 15).forEach((r, i) => add(`#${i + 1} overall`, r));
  let h = `<div class="table-wrap"><table class="res matrix"><thead><tr><th>Result</th><th>Heights (${u})</th><th>Spacing</th>`;
  search.bands.forEach(b => h += `<th colspan="2" class="band-h">${b.name}<br><small>FOM · Δ</small></th>`);
  if (nb > 1) h += '<th>Overall</th>';
  h += '<th></th></tr></thead><tbody>';
  picked.forEach(({ label, r }, k) => {
    h += `<tr class="${k === 0 ? 'best' : ''}"><td class="l">${label}${kinds.length > 1 ? ` <small class="tag">${r.kind}</small>` : ''}</td>
      <td>${r.h.join(' / ')}</td><td>${spacingText(r.h)}</td>`;
    r.b.forEach((v, i) => { const d = v === null ? null : v - bandBest[i];
      h += `<td class="band-c" title="${search.paths.map((p, j) => `${p.name}: ${fmt(r.p[i][j])}`).join('\n')}">${fmt(v)}</td>
            <td class="${d < -0.005 ? 'neg' : ''}">${d === null ? '—' : d.toFixed(2)}</td>`; });
    if (nb > 1) h += `<td><b>${fmt(r.score)}</b></td>`;
    h += `<td>${useBtn(r.h)}</td></tr>`;
  });
  $('#matrix').innerHTML = h + '</tbody></table></div>'; wireUse('#matrix');
}
const useBtn = h => `<button class="ghost small use" data-h="${h.join(',')}">Use</button>`;
function wireUse(sel) {
  $$(`${sel} button.use`).forEach(b => b.onclick = () => {
    const hs = b.dataset.h.split(',').map(Number);
    $$('#ant-rows .a-h').forEach((inp, i) => { if (hs[i] !== undefined) inp.value = hs[i]; });
    runAnalyse(true);
    $('#out').scrollIntoView({ behavior: 'smooth' });
  });
}

function buildMapControls() {
  $('#map-by').innerHTML = `<option value="-1">Overall (weighted)</option>` +
    search.bands.map((b, i) => `<option value="${i}">${b.name}</option>`).join('');
  $('#map-src').innerHTML = search.searches.map(s => `<option value="${s.kind}">${s.kind === 'free' ? 'Free spacing' : 'Equal spacing'}</option>`).join('');
  $('#map-src').parentElement.hidden = search.searches.length < 2;
}
function drawMap() {
  const kind = $('#map-src').value || search.searches[0].kind, by = +$('#map-by').value;
  const u = uLabel(search.units), n = search.rows[search.rows.length - 1].antennas.length;
  const rows = allRows(kind).map(r => ({ ...r, v: by < 0 ? r.score : r.b[by] })).filter(r => r.v !== null);
  const card = $('#map-card'), L = plotTheme();
  let x, y, xl, yl, oneD = false;
  if (kind === 'equal') {
    if (n === 1) { oneD = true; x = r => r.h[0]; xl = 'Height'; }
    else { x = r => r.h[0]; y = r => +(r.h[1] - r.h[0]).toFixed(2); xl = 'Bottom antenna height'; yl = 'Spacing'; }
  } else {
    const v = search.varying;
    if (v.length === 1) { oneD = true; x = r => r.h[v[0]]; xl = `Antenna ${v[0] + 1} height`; }
    else if (v.length === 2) { x = r => r.h[v[0]]; y = r => r.h[v[1]]; xl = `Antenna ${v[0] + 1} height`; yl = `Antenna ${v[1] + 1} height`; }
    else { card.hidden = true; return; }
  }
  card.hidden = false;
  $('#map-title').textContent = oneD ? 'FOM against height' : 'FOM map (best = star)';
  let traces;
  if (oneD) {
    rows.sort((a, b) => x(a) - x(b));
    traces = [{ x: rows.map(x), y: rows.map(r => r.v), mode: 'lines+markers', name: 'FOM' }];
    L.yaxis = { ...L.yaxis, title: 'FOM (dB)' }; L.showlegend = false;
  } else {
    const best = rows.reduce((a, b) => (b.v > a.v ? b : a));
    traces = [{ x: rows.map(x), y: rows.map(y), mode: 'markers', type: 'scatter',
                marker: { symbol: 'square', size: 11, color: rows.map(r => r.v), colorscale: 'Viridis', colorbar: { title: 'FOM dB' } },
                text: rows.map(r => r.h.join(' / ')),
                hovertemplate: `%{text} ${u}<br>FOM %{marker.color:.2f} dB<extra></extra>` },
              { x: [x(best)], y: [y(best)], mode: 'markers', hoverinfo: 'skip',
                marker: { symbol: 'star', size: 18, color: '#b5562b', line: { color: '#fff', width: 1 } } }];
    L.showlegend = false; L.yaxis = { ...L.yaxis, title: `${yl} (${u})` };
  }
  L.xaxis = { ...L.xaxis, title: `${xl} (${u})` };
  Plotly.react('map-plot', traces, L, { responsive: true, displaylogo: false });
}

// ---------- stack detail rendering ----------
function plotTheme() {
  const dark = matchMedia('(prefers-color-scheme: dark)').matches, ink = dark ? '#e5e8e6' : '#1d2327';
  const grid = dark ? '#2e373c' : '#e4e6e1';
  return { paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', font: { color: ink, size: 12 },
           margin: { l: 55, r: 50, t: 30, b: 45 }, legend: { orientation: 'h', y: -0.22 },
           xaxis: { gridcolor: grid, zeroline: false }, yaxis: { gridcolor: grid, zeroline: false } };
}

function showDetail(res, title) {
  analysis = res; currentPath = Math.min(currentPath, res.paths.length - 1);
  $('#empty').hidden = true; $('#out').hidden = false;
  $('#detail-title').textContent = title;
  status([...res.bands.map(b => b.warning && `${b.name}: ${b.warning}`), ...(res.geometry || [])]);
  $('#path-tabs').innerHTML = '';
  if (res.paths.length > 1) res.paths.forEach((p, i) => {
    const b = document.createElement('button'); b.textContent = p.name;
    b.className = i === currentPath ? 'on' : '';
    b.onclick = () => { currentPath = i; showDetail(analysis, title); };
    $('#path-tabs').appendChild(b);
  });
  drawPatterns(res); drawFomTable(res); drawAzimuth(res); drawGeometry(res); drawTerrain(res);
}

function comboName(r, u) {
  return r.antennas.length === 1 ? `Ant ${r.antennas[0]} @ ${r.heights[0]} ${u}` : `Ants ${r.antennas.join('+')}`;
}

function drawPatterns(res) {
  const u = uLabel(res.units), box = $('#pattern-plots'), n = Math.max(...res.rows.map(r => r.antennas.length));
  const allGroups = $('#show-groups').checked;
  $('#show-groups').parentElement.hidden = n < 3;
  const shown = res.rows.map((r, i) => ({ r, i })).filter(({ r }) => allGroups || n < 3 || r.antennas.length === 1 || r.antennas.length === n);
  box.innerHTML = '';
  box.className = 'plots-grid n' + res.bands.length;
  // one shared legend above the plots, so every plot keeps the same size
  const leg = document.createElement('div'); leg.className = 'legend';
  leg.innerHTML = `<span><i class="sw bar"></i>Arrival angles (%)</span>` + shown.map(({ r, i }) => {
    const single = r.antennas.length === 1 && n > 1;
    return `<span><i class="sw ${single ? 'dot' : ''} ${r.antennas.length === n ? 'thick' : ''}" style="border-color:${COLOURS[i % COLOURS.length]}"></i>${comboName(r, u)}</span>`;
  }).join('');
  $$('.legend', box.parentElement).forEach(e => e.remove());
  box.before(leg);
  res.bands.forEach((b, bi) => {
    const div = document.createElement('div'); div.className = 'plot'; box.appendChild(div);
    const traces = shown.map(({ r, i }) => {
      const full = r.antennas.length === n;
      return { x: res.angles, y: r.patterns[bi][currentPath], name: comboName(r, u), mode: 'lines', legendgroup: comboName(r, u),
               showlegend: bi === 0, line: { width: full ? 3 : 1.5, dash: r.antennas.length === 1 && n > 1 ? 'dot' : 'solid',
               color: COLOURS[i % COLOURS.length] } };
    });
    const aoa = b.aoa[currentPath];
    if (b.has_aoa[currentPath]) {
      const a = Object.entries(aoa);
      traces.unshift({ x: a.map(e => +e[0]), y: a.map(e => e[1]), type: 'bar', name: 'Arrival angles (%)', showlegend: bi === 0,
                       yaxis: 'y2', marker: { color: 'rgba(120,120,120,.28)' }, hovertemplate: '%{x}°: %{y:.1f}%<extra></extra>' });
    }
    const peak = Math.max(...res.rows.flatMap(r => r.patterns[bi][currentPath]));
    const L = plotTheme();
    L.title = { text: `${b.name} · ${b.freq} MHz · ${b.antenna}`, font: { size: 13 }, x: 0.02 };
    L.xaxis = { ...L.xaxis, title: 'Elevation (°)', range: [0, 35] };
    L.yaxis = { ...L.yaxis, title: 'Gain (dBi)', range: [Math.floor(peak - 25), Math.ceil(peak + 2)] };
    L.yaxis2 = { title: 'Arrival %', overlaying: 'y', side: 'right', showgrid: false, rangemode: 'tozero' };
    L.barmode = 'overlay'; L.showlegend = false; L.margin.b = 40;
    Plotly.newPlot(div, traces, L, { responsive: true, displaylogo: false });
  });
}

function drawFomTable(res) {
  const u = uLabel(res.units), nb = res.bands.length, n = Math.max(...res.rows.map(r => r.antennas.length));
  const w = weights.length === nb ? weights : res.bands.map(b => b.weight);
  const singles = res.rows.filter(r => r.antennas.length === 1);
  const bestSingle = res.bands.map((_, i) => {
    const v = singles.map(r => r.band_scores[i]).filter(x => x !== null); return v.length ? Math.max(...v) : null; });
  const overall = r => wmean(r.band_scores, w);
  const bestSingleAll = Math.max(...singles.map(overall).filter(x => x !== null));
  let h = `<div class="table-wrap"><table class="res matrix"><thead><tr><th>Configuration</th><th>Heights (${u})</th>`;
  res.bands.forEach(b => h += `<th colspan="${n > 1 ? 2 : 1}" class="band-h">${b.name}<br><small>${n > 1 ? 'FOM · Δ' : 'FOM'}</small></th>`);
  if (nb > 1) h += `<th colspan="${n > 1 ? 2 : 1}" class="band-h">Overall<br><small>${n > 1 ? 'FOM · Δ' : 'weighted'}</small></th>`;
  h += '</tr></thead><tbody>';
  res.rows.forEach(r => {
    h += `<tr class="${r.antennas.length === n && n > 1 ? 'stack' : ''}"><td class="l">${r.antennas.length === 1 ? 'Ant ' + r.antennas[0] + ' alone' : 'Stack ' + r.antennas.join('+')}</td>
          <td>${r.heights.join(' / ')}</td>`;
    r.band_scores.forEach((v, i) => {
      h += `<td class="band-c" title="${res.paths.map((p, j) => `${p.name}: ${fmt(r.band_foms[i][j])}`).join('\n')}">${fmt(v)}</td>`;
      if (n > 1) { const d = v === null || bestSingle[i] === null ? null : v - bestSingle[i]; h += `<td class="${cls(d)}">${sgn(d)}</td>`; }
    });
    if (nb > 1) { const o = overall(r); h += `<td class="band-c"><b>${fmt(o)}</b></td>`;
      if (n > 1) { const d = o === null ? null : o - bestSingleAll; h += `<td class="${cls(d)}">${sgn(d)}</td>`; } }
    h += '</tr>';
  });
  h += '</tbody></table></div>';
  if (!res.bands.some(b => b.has_aoa.some(Boolean))) h += '<p class="hint">No arrival-angle data loaded: FOM cannot be computed.</p>';
  else if (res.paths.length > 1) h += '<p class="hint">FOM per band is the path-weighted mean. Hold the pointer on a value to see each path.</p>';
  $('#fom-table').innerHTML = h;
}

function drawAzimuth(res) {
  const idx = res.paths.map((p, i) => ({ i, az: /^Az ([\d.]+)°/.exec(p.name) })).filter(x => x.az);
  $('#az-card').hidden = idx.length < 2;
  if (idx.length < 2) return;
  const stack = res.rows[res.rows.length - 1], L = plotTheme();
  const traces = res.bands.map((b, bi) => ({
    x: idx.map(x => +x.az[1]), y: idx.map(x => stack.band_foms[bi][x.i]), mode: 'lines+markers', name: `${b.name} stack`,
    line: { color: COLOURS[bi % COLOURS.length] } }));
  L.xaxis = { ...L.xaxis, title: 'Azimuth (° true)' }; L.yaxis = { ...L.yaxis, title: 'FOM (dB)' };
  Plotly.react('az-plot', traces, L, { responsive: true, displaylogo: false });
}

function drawGeometry(res) {
  const u = uLabel(res.units), stack = res.rows[res.rows.length - 1], hs = stack.heights;
  const lines = [];
  hs.forEach((x, i) => lines.push({ label: `Ant ${i + 1} height`, v: x, boom: false }));
  for (let i = 1; i < hs.length; i++) lines.push({ label: `Spacing ${i}–${i + 1}`, v: +(hs[i] - hs[i - 1]).toFixed(2), boom: true });
  const anyBoom = res.bands.some(b => b.boom);
  let h = `<div class="table-wrap"><table class="res matrix"><thead><tr><th></th><th>${u}</th>`;
  res.bands.forEach(b => h += `<th colspan="${anyBoom ? 2 : 1}" class="band-h">${b.name}<br><small>λ = ${b.lambda} ${u}${b.boom ? ` · boom ${b.boom} ${u}` : ''}</small></th>`);
  h += '</tr><tr><th></th><th></th>';
  res.bands.forEach(() => h += `<th class="band-h"><small>in λ</small></th>${anyBoom ? '<th><small>÷ boom</small></th>' : ''}`);
  h += '</tr></thead><tbody>';
  lines.forEach(l => {
    h += `<tr><td class="l">${l.label}</td><td>${l.v}</td>`;
    res.bands.forEach(b => {
      const lam = l.v / b.lambda, low = l.boom && lam < res.min_spacing_lambda - 1e-6;
      h += `<td class="band-c ${low ? 'neg' : ''}">${lam.toFixed(2)}</td>`;
      if (anyBoom) h += `<td>${l.boom && b.boom ? (l.v / b.boom).toFixed(2) : ''}</td>`;
    });
    h += '</tr>';
  });
  h += `</tbody></table></div><p class="hint">Minimum spacing set: ${res.min_spacing_lambda} λ on the lowest band = ${res.min_spacing} ${u}.
        ${res.max_tower ? `Maximum tower height: ${res.max_tower} ${u}.` : ''} Boom ratios are for your judgement; the model does not use boom length or coupling.</p>`;
  $('#geometry').innerHTML = h;
}

function drawTerrain(res) {
  const p = res.paths[currentPath], u = uLabel(res.units);
  const stack = res.rows[res.rows.length - 1], base = p.hgt[0];
  const traces = [{ x: p.dist, y: p.hgt, mode: 'lines', name: 'Terrain', fill: 'tozeroy',
                    line: { color: '#8a6a3a' }, fillcolor: 'rgba(138,106,58,.18)' },
                  { x: stack.heights.map(() => 0), y: stack.heights.map(h => base + h), mode: 'markers+text',
                    name: 'Antennas', text: stack.antennas.map(a => ' ' + a), textposition: 'middle right',
                    marker: { size: 9, color: '#b5562b', symbol: 'line-ew-open', line: { width: 3 } } },
                  { x: [0, 0], y: [base, base + Math.max(...stack.heights)], mode: 'lines', line: { color: '#555', width: 2 } }];
  const L = plotTheme(); L.showlegend = false; L.margin.b = 50;
  const near = res.units === 'm' ? 1500 : 5000, top = base + Math.max(...stack.heights);
  const xs = p.dist.filter(d => d <= near), ys = p.hgt.slice(0, Math.max(xs.length, 2));
  const lo = Math.min(...ys, base), hi = Math.max(...ys, top), pad = (hi - lo) * 0.08 + 1;
  L.xaxis = { ...L.xaxis, title: `Distance (${u}) · double-click for whole profile`, range: [-near * 0.03, Math.min(near, p.dist[p.dist.length - 1])] };
  L.yaxis = { ...L.yaxis, title: `Height (${u})`, range: [lo - pad, hi + pad] };
  Plotly.react('terrain-plot', traces, L, { responsive: true, displaylogo: false });
}

// ---------- wiring ----------
$('#add-path').onclick = () => addPath();
$('#sec-on').onchange = () => { $('#sector').hidden = !$('#sec-on').checked; sectorPreview(); };
$('#sec-pro').onchange = e => readMany(e.target.files, list => {
  sector.profiles = {};
  const bad = [];
  list.forEach(([n, t]) => { const a = azFromName(n); if (a === null) bad.push(n); else sector.profiles[a] = t; });
  const az = Object.keys(sector.profiles).map(Number).sort((a, b) => a - b);
  $('#sec-pro-info').textContent = `${az.length} profiles, ${az[0] ?? '—'}° to ${az[az.length - 1] ?? '—'}°` + (bad.length ? ` · no azimuth in: ${bad.join(', ')}` : '');
  sectorPreview();
});
$('#sec-prn').onchange = e => readMany(e.target.files, ([[n, t]]) => { sector.prn = t; $('#sec-prn-info').textContent = n; });
$('#sec-json').onchange = e => readMany(e.target.files, ([[n, t]]) => {
  try {
    sector.bearings = JSON.parse(t);
    const bands = Object.keys(sector.bearings.bands || {}).filter(b => sector.bearings.bands[b].n);
    $('#sec-band').innerHTML = bands.map(b => `<option value="${b}">${b === 'all' ? 'All bands' : b + ' m'}</option>`).join('');
    $('#sec-json-info').textContent = `${n}: ${sector.bearings.region}, ${sector.bearings.contests.join(', ')}, ${sector.bearings.reference_logs} reference logs`;
  } catch (err) { $('#sec-json-info').textContent = 'Not a bearings file'; }
  sectorPreview();
});
['#sec-centre', '#sec-spread', '#sec-step', '#sec-mode', '#sec-band', '#sec-weight'].forEach(s => $(s).addEventListener('input', sectorPreview));
$('#add-band').onclick = () => { addBand(); refreshChecks(); };
$$('[data-preset]').forEach(b => b.onclick = () => setPreset(b.dataset.preset));
$('#n_ant').onchange = renderAntRows;
$('#units').onchange = () => {
  const f = units() === 'm' ? 1 / FT : FT;
  $$('#ant-rows input[type=number], .b-boom').concat([$('#step'), $('#move_tower'), $('#max_tower'), $('#spacing_min'), $('#spacing_max')])
    .forEach(i => { if (i.value !== '') i.value = +(+i.value * f).toFixed(1); });
  refreshChecks();
};
$('#soil').onchange = () => $$('.custom-soil').forEach(e => e.hidden = $('#soil').value !== 'Custom');
['#min_spacing_lambda', '#mode'].forEach(s => $(s).addEventListener('input', refreshChecks));
$('#matrix-src').onchange = renderMatrix;
$('#show-groups').onchange = () => analysis && drawPatterns(analysis);
$('#map-by').onchange = drawMap;
$('#map-src').onchange = drawMap;
$('#run-analyse').onclick = () => runAnalyse(false);
$('#run-optimise').onclick = runOptimise;
$('#cancel').onclick = () => currentJob && fetch(`/api/job/${currentJob}/cancel`, { method: 'POST' });

setPreset('single');
addPath('Path 1');
renderAntRows();
