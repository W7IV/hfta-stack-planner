// HFTA Stack Planner - browser side
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const DEFAULT_H = [50, 100, 150, 200];          // feet
const COLOURS = ['#0b5f7a', '#b5562b', '#6a8f2a', '#7a4fa0', '#c08a00', '#2d8a8a', '#a0406a',
                 '#4a6fb5', '#8a6a3a', '#3a8a5a', '#b54a4a', '#5a5a9a', '#9a7a2a', '#2a7a9a', '#111'];
let lastResult = null, currentPath = 0, pollTimer = null, currentJob = null;

// ---------- paths ----------
function addPath(name = '') {
  const node = $('#path-tpl').content.firstElementChild.cloneNode(true);
  $('.p-name', node).value = name || `Path ${$$('#paths .path').length + 1}`;
  $('.p-del', node).onclick = () => { node.remove(); };
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
        checkBand();
      } catch (e) { info.textContent = e.message; info.classList.add('bad'); }
    }
  };
  r.readAsText(f);
}

function bandOf(f) {
  const t = [[1.8,2,'160m'],[3.5,4,'80m'],[5.3,5.4,'60m'],[7,7.3,'40m'],[10.1,10.15,'30m'],[14,14.35,'20m'],
             [18.068,18.168,'17m'],[21,21.45,'15m'],[24.89,24.99,'12m'],[28,29.7,'10m'],[50,54,'6m']];
  const b = t.find(([a, z]) => f >= a && f <= z); return b ? b[2] : null;
}

function checkBand() {
  const f = +$('#freq').value, band = bandOf(f), msgs = [];
  if (!band) msgs.push('Frequency is outside the amateur bands: no arrival-angle data, so no FOM.');
  else if (f < 7) msgs.push('Below 7 MHz the diffraction method is less reliable, mainly with low antennas and steep terrain near the tower. Compare with diffraction off.');
  else if (f > 30) msgs.push('Above 30 MHz the method is not validated. Terrain data must resolve features of about 1/8 wavelength.');
  $$('#paths .path').forEach(p => {
    if (band && p.dataset.bands && !p.dataset.bands.split(',').includes(band))
      msgs.push(`${$('.p-name', p).value}: the .PRN file has no ${band} column.`);
  });
  const w = $('#freq-warning'); w.hidden = !msgs.length; w.textContent = msgs.join(' ');
}

// ---------- antennas ----------
function renderAntRows() {
  const n = +$('#n_ant').value, old = readAnts(), body = $('#ant-rows'), u = $('#units').value;
  const def = h => u === 'm' ? +(h / 3.28084).toFixed(1) : h;
  body.innerHTML = '';
  for (let i = 0; i < n; i++) {
    const o = old[i] || { height: def(DEFAULT_H[i]), phase: 0, vary: true,
                          min: def(Math.max(20, DEFAULT_H[i] - 40)), max: def(DEFAULT_H[i] + 40) };
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
}
function readAnts() {
  return $$('#ant-rows tr').map(tr => ({
    height: +$('.a-h', tr).value, phase: +$('.a-p', tr).value, vary: $('.a-v', tr).checked,
    min: +$('.a-min', tr).value, max: +$('.a-max', tr).value }));
}

// ---------- request ----------
function common() {
  const paths = $$('#paths .path').map(p => ({
    name: $('.p-name', p).value, weight: +$('.p-weight', p).value || 0,
    profile: p.dataset.pro || '', aoa: p.dataset.prn || '' }));
  return {
    freq: +$('#freq').value, units: $('#units').value, antenna_type: $('#antenna_type').value,
    soil: $('#soil').value, sigma: +$('#sigma').value, epsr: +$('#epsr').value,
    diffraction: $('#diffraction').checked, move_tower: +$('#move_tower').value || 0, paths };
}
async function post(url, body) {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
function status(msg, kind = '') {
  const s = $('#status'); s.hidden = !msg; s.textContent = msg || ''; s.className = 'status ' + kind;
}
function busy(on) { $('#run-analyse').disabled = on; $('#run-optimise').disabled = on; }

async function runAnalyse() {
  status(''); busy(true); $('#opt-summary').hidden = true;
  try {
    const body = { ...common(), antennas: readAnts(), combinations: true };
    const res = await post('/api/analyse', body);
    res.mode = 'analyse'; show(res);
  } catch (e) { status(e.message, 'error'); }
  busy(false);
}

async function runOptimise() {
  status(''); busy(true);
  try {
    const ants = readAnts().map(a => a.vary ? { mode: 'range', min: a.min, max: a.max, phase: a.phase }
                                            : { mode: 'fixed', height: a.height, phase: a.phase });
    const body = { ...common(), antennas: ants, step: +$('#step').value, min_spacing: +$('#min_spacing').value };
    const r = await post('/api/optimise', body);
    currentJob = r.job;
    $('#progress').hidden = false; $('#progress-fill').style.width = '0';
    $('#progress-text').textContent = `${r.combinations} combinations in the full grid…`;
    pollTimer = setInterval(poll, 700);
  } catch (e) { status(e.message, 'error'); busy(false); }
}
async function poll() {
  const j = await (await fetch(`/api/job/${currentJob}`)).json();
  if (j.state === 'running') {
    const pct = j.total ? 100 * j.done / j.total : 0;
    $('#progress-fill').style.width = pct + '%';
    $('#progress-text').textContent = `${j.phase}: ${j.done} / ${j.total}`;
    return;
  }
  clearInterval(pollTimer); $('#progress').hidden = true; busy(false);
  if (j.state === 'error') { status(j.error, j.error === 'Cancelled' ? '' : 'error'); return; }
  const res = j.result; res.mode = 'optimise'; res.rows = res.detail; show(res);
}

// ---------- rendering ----------
const fmt = (v, d = 2) => v === null || v === undefined ? '—' : (+v).toFixed(d);
const uLabel = u => u === 'm' ? 'm' : 'ft';
function plotTheme() {
  const dark = matchMedia('(prefers-color-scheme: dark)').matches, ink = dark ? '#e5e8e6' : '#1d2327';
  const grid = dark ? '#2e373c' : '#e4e6e1';
  return { paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', font: { color: ink, size: 12 },
           margin: { l: 55, r: 55, t: 10, b: 45 }, legend: { orientation: 'h', y: -0.18 },
           xaxis: { gridcolor: grid, zeroline: false }, yaxis: { gridcolor: grid, zeroline: false } };
}

function show(res) {
  lastResult = res; currentPath = Math.min(currentPath, res.paths.length - 1);
  $('#empty').hidden = true; $('#out').hidden = false;
  if (res.warning) status(res.warning);
  $('#path-tabs').innerHTML = '';
  if (res.paths.length > 1) res.paths.forEach((p, i) => {
    const b = document.createElement('button'); b.textContent = p.name;
    b.className = i === currentPath ? 'on' : '';
    b.onclick = () => { currentPath = i; show(lastResult); };
    $('#path-tabs').appendChild(b);
  });
  drawPattern(res); drawFomTable(res); drawTerrain(res);
  if (res.mode === 'optimise') { drawSummary(res); drawMap(res); drawTop(res); }
  else { $('#opt-summary').hidden = true; $('#map-card').hidden = true; $('#top-card').hidden = true; }
}

function comboName(r, u) { return r.antennas.length === 1 ? `Ant ${r.antennas[0]} alone @ ${r.heights[0]} ${u}`
                                                     : `Ants ${r.antennas.join('+')} @ ${r.heights.join('/')} ${u}`; }

function drawPattern(res) {
  const u = uLabel(res.units), p = res.paths[currentPath], n = Math.max(...res.rows.map(r => r.antennas.length));
  const traces = res.rows.map((r, i) => {
    const full = r.antennas.length === n;
    return { x: res.angles, y: r.patterns[currentPath], name: comboName(r, u), mode: 'lines',
             line: { width: full ? 3 : 1.5, dash: r.antennas.length === 1 && n > 1 ? 'dot' : 'solid', color: COLOURS[i % COLOURS.length] } };
  });
  if (p.has_aoa) {
    const a = Object.entries(p.aoa);
    traces.unshift({ x: a.map(e => +e[0]), y: a.map(e => e[1]), type: 'bar', name: 'Arrival angles (%)',
                     yaxis: 'y2', marker: { color: 'rgba(120,120,120,.28)' }, hovertemplate: '%{x}°: %{y:.1f}%<extra></extra>' });
  }
  const L = plotTheme();
  L.xaxis = { ...L.xaxis, title: 'Elevation angle (degrees)', range: [0, 35] };
  const peak = Math.max(...res.rows.flatMap(r => r.patterns[currentPath]));
  L.yaxis = { ...L.yaxis, title: 'Gain (dBi)', range: [Math.floor(peak - 25), Math.ceil(peak + 2)] };
  L.yaxis2 = { title: 'Arrival (%)', overlaying: 'y', side: 'right', showgrid: false, rangemode: 'tozero' };
  L.barmode = 'overlay';
  Plotly.react('pattern-plot', traces, L, { responsive: true, displaylogo: false });
}

function drawFomTable(res) {
  const u = uLabel(res.units), multi = res.paths.length > 1;
  const singles = res.rows.filter(r => r.antennas.length === 1 && r.score !== null);
  const bestSingle = singles.length ? Math.max(...singles.map(r => r.score)) : null;
  const n = Math.max(...res.rows.map(r => r.antennas.length));
  let h = `<div class="table-wrap"><table class="res"><thead><tr><th>Configuration</th><th>Heights (${u})</th>`;
  res.paths.forEach(p => h += `<th>${p.name}${multi ? ` ×${p.weight}` : ''}</th>`);
  if (multi) h += '<th>Weighted</th>';
  if (n > 1) h += '<th>Δ vs best single</th>';
  h += '</tr></thead><tbody>';
  res.rows.forEach(r => {
    const d = bestSingle !== null && r.score !== null ? r.score - bestSingle : null;
    h += `<tr class="${r.antennas.length === n && n > 1 ? 'stack' : ''}"><td class="l">${r.antennas.length === 1 ? 'Ant ' + r.antennas[0] + ' alone' : 'Stack ' + r.antennas.join('+')}</td>
          <td>${r.heights.join(' / ')}</td>`;
    r.foms.forEach(f => h += `<td>${fmt(f)}</td>`);
    if (multi) h += `<td>${fmt(r.score)}</td>`;
    if (n > 1) h += `<td class="${d > 0.005 ? 'pos' : d < -0.005 ? 'neg' : ''}">${d === null ? '—' : (d >= 0 ? '+' : '') + d.toFixed(2)}</td>`;
    h += '</tr>';
  });
  h += '</tbody></table></div>';
  if (!res.paths.some(p => p.has_aoa)) h += '<p class="hint">No arrival-angle data loaded: FOM cannot be computed.</p>';
  $('#fom-table').innerHTML = h;
}

function drawTerrain(res) {
  const p = res.paths[currentPath], u = uLabel(res.units);
  const stack = res.rows[res.rows.length - 1], base = p.hgt[0];
  const traces = [{ x: p.dist, y: p.hgt, mode: 'lines', name: 'Terrain', fill: 'tozeroy',
                    line: { color: '#8a6a3a' }, fillcolor: 'rgba(138,106,58,.18)' },
                  { x: stack.heights.map(() => 0), y: stack.heights.map(h => base + h), mode: 'markers+text',
                    name: 'Antennas', text: stack.antennas.map(a => ' ' + a), textposition: 'middle right',
                    marker: { size: 9, color: '#b5562b', symbol: 'line-ew-open', line: { width: 3 } } },
                  { x: [0, 0], y: [base, base + Math.max(...stack.heights)], mode: 'lines', name: 'Tower',
                    line: { color: '#555', width: 2 }, showlegend: false }];
  const L = plotTheme();
  // open on the near terrain, where it matters most; double-click the plot to see the whole profile
  const near = res.units === 'm' ? 1500 : 5000, top = base + Math.max(...stack.heights);
  const xs = p.dist.filter(d => d <= near), ys = p.hgt.slice(0, Math.max(xs.length, 2));
  const lo = Math.min(...ys, base), hi = Math.max(...ys, top), pad = (hi - lo) * 0.08 + 1;
  L.xaxis = { ...L.xaxis, title: `Distance (${u}) · double-click for full profile`, range: [-near * 0.03, Math.min(near, p.dist[p.dist.length - 1])] };
  L.yaxis = { ...L.yaxis, title: `Height (${u})`, range: [lo - pad, hi + pad] };
  Plotly.react('terrain-plot', traces, L, { responsive: true, displaylogo: false });
}

function drawSummary(res) {
  const u = uLabel(res.units), b = res.top[0], el = $('#opt-summary');
  const ranges = res.within_half_db.map(r => `Ant ${r.antenna}: ${r.min}–${r.max} ${u}`).join(' · ');
  el.innerHTML = `<p class="big">Best: ${b.heights.join(' / ')} ${u} &nbsp;·&nbsp; FOM ${fmt(b.score)} dB</p>
    <p>Height ranges that stay within 0.5 dB of the best: ${ranges}</p>
    <p class="hint">${res.evaluated} configurations calculated in ${res.seconds} s
      ${res.coarse_step ? ` (coarse search at ${res.coarse_step} ${u}, then fine search near the 5 best; full grid would be ${res.full_grid})` : ''}.
      Table and patterns below show the best stack and each of its antennas alone.</p>`;
  el.hidden = false;
}

function drawMap(res) {
  const card = $('#map-card'), u = uLabel(res.units), m = res.map;
  if (!m) { card.hidden = true; return; }
  card.hidden = false;
  const L = plotTheme(); let traces;
  if (m.line) {
    $('#map-title').textContent = `FOM against height of ${m.x_label}`;
    traces = [{ x: m.line.map(p => p[0]), y: m.line.map(p => p[1]), mode: 'lines+markers', name: 'FOM' }];
    L.xaxis = { ...L.xaxis, title: `${m.x_label} height (${u})` }; L.yaxis = { ...L.yaxis, title: 'FOM (dB)' };
  } else {
    $('#map-title').textContent = 'FOM map (best = star)';
    const pts = m.points, best = pts[0];
    traces = [{ x: pts.map(p => p[0]), y: pts.map(p => p[1]), mode: 'markers', type: 'scatter',
                marker: { symbol: 'square', size: 11, color: pts.map(p => p[2]), colorscale: 'Viridis',
                          colorbar: { title: 'FOM dB' } },
                hovertemplate: `${m.x_label} %{x} ${u}<br>${m.y_label} %{y} ${u}<br>FOM %{marker.color:.2f} dB<extra></extra>` },
              { x: [best[0]], y: [best[1]], mode: 'markers', marker: { symbol: 'star', size: 18, color: '#b5562b',
                line: { color: '#fff', width: 1 } }, hoverinfo: 'skip' }];
    L.showlegend = false;
    L.xaxis = { ...L.xaxis, title: `${m.x_label} height (${u})` }; L.yaxis = { ...L.yaxis, title: `${m.y_label} height (${u})` };
  }
  Plotly.react('map-plot', traces, L, { responsive: true, displaylogo: false });
}

function drawTop(res) {
  const u = uLabel(res.units), multi = res.paths.length > 1, best = res.top[0].score;
  let h = `<div class="table-wrap"><table class="res"><thead><tr><th>#</th><th>Heights (${u})</th>`;
  res.paths.forEach(p => h += `<th>${p.name}</th>`);
  if (multi) h += '<th>Weighted</th>';
  h += '<th>Δ to best</th><th></th></tr></thead><tbody>';
  res.top.forEach((r, i) => {
    h += `<tr class="${i === 0 ? 'best' : ''}"><td class="l">${i + 1}</td><td>${r.heights.join(' / ')}</td>`;
    r.foms.forEach(f => h += `<td>${fmt(f)}</td>`);
    if (multi) h += `<td>${fmt(r.score)}</td>`;
    h += `<td>${(r.score - best).toFixed(2)}</td><td><button class="ghost small" data-h="${r.heights.join(',')}">Use</button></td></tr>`;
  });
  $('#top-table').innerHTML = h + '</tbody></table></div>';
  $$('#top-table button[data-h]').forEach(b => b.onclick = () => {
    const hs = b.dataset.h.split(',').map(Number);
    $$('#ant-rows .a-h').forEach((inp, i) => { if (hs[i] !== undefined) inp.value = hs[i]; });
    runAnalyse();
  });
}

// ---------- wiring ----------
$('#add-path').onclick = () => addPath();
$('#n_ant').onchange = renderAntRows;
$('#units').onchange = () => {
  const f = $('#units').value === 'm' ? 1 / 3.28084 : 3.28084;
  $$('#ant-rows input[type=number]').concat([$('#step'), $('#min_spacing'), $('#move_tower')])
    .forEach(i => i.value = +(+i.value * f).toFixed(1));
};
$('#soil').onchange = () => $$('.custom-soil').forEach(e => e.hidden = $('#soil').value !== 'Custom');
$('#freq').oninput = checkBand;
$('#run-analyse').onclick = runAnalyse;
$('#run-optimise').onclick = runOptimise;
$('#cancel').onclick = () => currentJob && fetch(`/api/job/${currentJob}/cancel`, { method: 'POST' });

addPath('Path 1');
renderAntRows();
checkBand();
