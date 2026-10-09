/* HFTA Stack Planner v2 - five-step workflow. Plain JS; state lives in the project file on the local server. */
"use strict";
let META = null, S = null, SLUG = null, STEP = "sites", RES = null, saveTimer = null;
const $ = (s, el = document) => el.querySelector(s), $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = (v, d = 2) => v === null || v === undefined || Number.isNaN(v) ? "–" : Number(v).toFixed(d);
const P = () => S.project;
function css(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
function plotLayout(extra = {}) {
  return Object.assign({ paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { color: css("--ink"), size: 12 },
    margin: { l: 50, r: 16, t: 28, b: 42 }, xaxis: { gridcolor: css("--line"), zerolinecolor: css("--line") },
    yaxis: { gridcolor: css("--line"), zerolinecolor: css("--line") }, legend: { orientation: "h", y: -0.22 } }, extra);
}
const PAL = ["#1d5c8c", "#d9822b", "#2c7a4b", "#8e44ad", "#b33a3a", "#16a085", "#7f8c8d", "#c0a000"];
async function api(method, url, body, isForm) {
  const o = { method, headers: {} };
  if (body !== undefined) { if (isForm) o.body = body; else { o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(body); } }
  const r = await fetch(url, o); const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText); return j;
}
function toast(msg, ms = 2600) { const t = $("#toast"); t.textContent = msg; t.hidden = false; clearTimeout(t._h); t._h = setTimeout(() => t.hidden = true, ms); }
function save(now) {
  $("#saveState").textContent = "Saving…"; clearTimeout(saveTimer);
  const go = async () => { try { S = await api("PUT", `/api/v2/p/${SLUG}`, P()); $("#saveState").textContent = "Saved"; status(); } catch (e) { $("#saveState").textContent = "Not saved: " + e.message; } };
  if (now) return go(); saveTimer = setTimeout(go, 500);
}
function bind(el, obj, key, after, num) {
  el.addEventListener("change", () => { obj[key] = num ? (el.value === "" ? null : Number(el.value)) : (el.type === "checkbox" ? el.checked : el.value); save(); after && after(); });
}
function status() {
  const p = P(), on = Object.entries(p.settings.layers || {}).filter(([k, v]) => v).map(([k]) => k);
  const b = $("#hftaBadge"); b.className = "badge " + (on.length ? "layer" : "pure");
  b.textContent = on.length ? "Layers on: " + on.map(k => ({ jk_gain: "maker gain", beam_loss: "beam loss" }[k])).join(", ") : "Pure HFTA";
  b.title = on.length ? "Some numbers include additions beyond HFTA. The HFTA value is always shown beside them." : "Every number shown can be reproduced in the original HFTA";
  const ready = p.sites.filter(s => (S.site_files[s.id] || {}).n).length;
  $("#st-sites").textContent = `${ready}/${p.sites.length} with terrain`;
  $("#st-targets").textContent = `${p.targets.length} targets, ${S.prns.length} .PRN`;
  $("#st-towers").textContent = `${p.towers.length} towers`;
  $("#st-compare").textContent = S.has_results ? "results " + (S.results_stamp || "").slice(5, 16) : "not run";
}
function go(step) {
  STEP = step; $$(".step").forEach(b => b.classList.toggle("on", b.dataset.step === step));
  $$(".page").forEach(p => p.hidden = p.id !== "p-" + step); render();
}
function render() { status(); ({ sites: rSites, targets: rTargets, towers: rTowers, compare: rCompare, report: rReport })[STEP](); }
function modal(html) { $("#modalBody").innerHTML = html; $("#modal").hidden = false; }
function closeModal() { $("#modal").hidden = true; }
function uid(p) { return p + Math.random().toString(16).slice(2, 8); }

/* ---------------------------------------------------------------- 1. Sites */
function rSites() {
  const p = P(), el = $("#p-sites"), st = p.settings;
  el.innerHTML = `<h1>Sites</h1><p class="lead">Each site is one possible tower position on your property, with its own set of terrain profiles (one file per azimuth).
  Add two or more sites to compare them with the same towers and targets.</p>
  <div class="card"><h2>Ground</h2><div class="row">
    <label>Soil<select id="soil">${Object.keys(META.soils).map(k => `<option ${k === st.soil ? "selected" : ""}>${esc(k)}</option>`).join("")}</select></label>
    <label>Dielectric constant<input id="epsr" type="number" step="0.5" value="${st.epsr}"></label>
    <label>Conductivity (S/m)<input id="sigma" type="number" step="0.001" value="${st.sigma}"></label>
    <label style="flex-direction:row;align-items:center;gap:6px"><input id="diff" type="checkbox" ${st.diffraction ? "checked" : ""}> Diffraction (HFTA default: on)</label></div></div>
  <div id="siteCards"></div>
  <button id="addSite">Add site</button>
  <div id="siteCompare"></div>`;
  $("#soil").onchange = e => { const [s, k] = META.soils[e.target.value]; Object.assign(st, { soil: e.target.value, sigma: s, epsr: k }); save(); rSites(); };
  bind($("#epsr"), st, "epsr", null, true); bind($("#sigma"), st, "sigma", null, true); bind($("#diff"), st, "diffraction");
  $("#addSite").onclick = () => { p.sites.push({ id: uid("s"), name: `Site ${p.sites.length + 1}`, lat: null, lon: null, notes: "", terrain: { source: "" } }); save(true).then(rSites); };
  const box = $("#siteCards");
  p.sites.forEach((s, i) => {
    const f = S.site_files[s.id] || { n: 0 }, c = document.createElement("div"); c.className = "card";
    const tchip = f.n ? `<span class="chip good">${f.n} profiles${f.step ? `, every ${f.step}°` : ""}</span> <span class="chip">${esc(s.terrain?.source || "")}</span>`
                      : `<span class="chip warn">No terrain yet</span>`;
    c.innerHTML = `<h2><input class="w" value="${esc(s.name)}" data-k="name" aria-label="Site name"> ${tchip}</h2>
      <div class="row"><label>Latitude<input type="number" step="0.00001" data-k="lat" value="${s.lat ?? ""}"></label>
      <label>Longitude<input type="number" step="0.00001" data-k="lon" value="${s.lon ?? ""}"></label>
      <label style="flex:1">Notes<input data-k="notes" value="${esc(s.notes || "")}" style="width:100%"></label></div>
      <div class="row" style="margin-top:10px">
        <label>Source of the files you import<select data-src><option>MicroDEM .PRO</option><option>K6TU terrain set</option><option>Other .PRO files</option></select></label>
        <button data-act="import">Import .PRO or .zip</button><input type="file" multiple accept=".pro,.PRO,.zip" hidden data-file>
        <button class="ghost" data-act="dem">Generate from DEM file</button>
        <button class="ghost" data-act="flat">Flat ground</button>
        ${f.n ? `<button class="ghost" data-act="clear">Remove profiles</button>` : ""}
        <button class="danger" data-act="del">Delete site</button></div>
      <p class="small mute" style="margin:8px 0 0">K6TU sells HFTA-ready one-degree terrain sets: <a href="https://www.k6tu.net" target="_blank" rel="noopener">k6tu.net</a>.
      MicroDEM makes .PRO files from free elevation data. A DEM file is processed on this computer only.</p>`;
    $$("[data-k]", c).forEach(inp => bind(inp, s, inp.dataset.k, null, inp.type === "number"));
    const fileIn = $("[data-file]", c), srcSel = $("[data-src]", c);
    if ([...srcSel.options].some(o => o.text === s.terrain?.source)) srcSel.value = s.terrain.source;
    $("[data-act=import]", c).onclick = () => fileIn.click();
    fileIn.onchange = async () => {
      const fd = new FormData(); [...fileIn.files].forEach(x => fd.append("files", x));
      try { const r = await api("POST", `/api/v2/p/${SLUG}/sites/${s.id}/import`, fd, true); s.terrain = { source: srcSel.value };
        toast(`${r.added.length} profiles imported${r.skipped.length ? `, ${r.skipped.length} skipped` : ""}`); await save(true); rSites(); }
      catch (e) { toast(e.message, 5000); }
    };
    $("[data-act=flat]", c).onclick = async () => { await api("POST", `/api/v2/p/${SLUG}/sites/${s.id}/flat`); s.terrain = { source: "Flat ground" }; await save(true); rSites(); };
    const clr = $("[data-act=clear]", c); if (clr) clr.onclick = async () => { await api("DELETE", `/api/v2/p/${SLUG}/sites/${s.id}/files`); s.terrain = { source: "" }; await save(true); rSites(); };
    $("[data-act=del]", c).onclick = async () => { p.sites.splice(i, 1); await save(true); rSites(); };
    $("[data-act=dem]", c).onclick = () => demDialog(s);
    box.appendChild(c);
  });
  siteCompare();
}
function demDialog(s) {
  modal(`<h2>Generate terrain profiles from a DEM file</h2>
  <p class="small mute">GeoTIFF (.tif) in latitude/longitude or UTM metres, or ESRI ASCII grid (.asc). USGS 3DEP 1 m LiDAR and 1/3 arc-second DEMs work.
  The file stays on this computer. Profiles are written in HFTA .PRO format.</p>
  <form id="demForm" class="row">
    <label style="width:100%">DEM file<input type="file" name="dem" accept=".tif,.tiff,.asc" required></label>
    <label>Latitude<input type="number" step="0.000001" name="lat" value="${s.lat ?? ""}" required></label>
    <label>Longitude<input type="number" step="0.000001" name="lon" value="${s.lon ?? ""}" required></label>
    <label>Coordinate system<select name="crs"><option value="">From the file</option><option value="geographic">Latitude/longitude</option>
      ${Array.from({ length: 13 }, (_, k) => `<option value="utm:${k + 10}">UTM zone ${k + 10}</option>`).join("")}</select></label>
    <label>Elevation units<select name="z_units"><option value="m">metres</option><option value="ft">feet</option></select></label>
    <label>Azimuth step (°)<input type="number" name="az_step" value="1" min="0.5" step="0.5"></label>
    <label>Point spacing (m)<input type="number" name="spacing_m" value="30" min="5"></label>
    <label>Length (m)<input type="number" name="length_m" value="4410"></label>
    <input type="hidden" name="prefix" value="${esc(s.name)}">
    <div style="width:100%;display:flex;gap:8px;margin-top:8px"><button type="submit">Generate</button><button type="button" class="ghost" id="demCancel">Cancel</button></div>
    <p class="small mute" style="width:100%">HFTA reads at most 148 points per profile, so spacing × 147 limits the length.</p></form>`);
  $("#demCancel").onclick = closeModal;
  $("#demForm").onsubmit = async e => {
    e.preventDefault(); const fd = new FormData(e.target); s.lat = Number(fd.get("lat")); s.lon = Number(fd.get("lon"));
    e.target.querySelector("button[type=submit]").disabled = true; e.target.querySelector("button[type=submit]").textContent = "Working…";
    try { const r = await api("POST", `/api/v2/p/${SLUG}/sites/${s.id}/dem`, fd, true); s.terrain = { source: "DEM: " + fd.get("dem").name };
      closeModal(); toast(`${r.written} profiles written. Ground ${r.ground_elevation_m} m.${r.short_azimuths.length ? ` ${r.short_azimuths.length} profiles cut short at the DEM edge.` : ""}`, 6000);
      await save(true); rSites(); }
    catch (err) { toast(err.message, 6000); e.target.querySelector("button[type=submit]").disabled = false; e.target.querySelector("button[type=submit]").textContent = "Generate"; }
  };
}
async function siteCompare() {
  const p = P(), ready = p.sites.filter(s => (S.site_files[s.id] || {}).n);
  const box = $("#siteCompare"); if (!ready.length) { box.innerHTML = ""; return; }
  box.innerHTML = `<div class="card" style="margin-top:14px"><h2>Compare terrain</h2>
    <p class="small mute">For a first look only. HFTA uses the whole profile. Positive slope = ground falls away from the tower (good for low angles).</p>
    <div class="grid2"><div><div class="row"><label>Azimuth (°)<input id="cmpAz" type="number" min="0" max="359" value="${p.targets[0]?.heading ?? 50}"></label></div>
      <div id="profPlot" class="plot"></div></div><div><div id="slopePlot" class="plot"></div></div></div>
    <div class="tbl"><table id="siteSlopeTbl"></table></div></div>`;
  const draw = async () => {
    const az = Number($("#cmpAz").value), tr = [];
    for (const [i, s] of ready.entries()) {
      const r = await api("GET", `/api/v2/p/${SLUG}/sites/${s.id}/profile?az=${az}`);
      tr.push({ x: r.d_ft.map(d => d / 3280.84), y: r.h_ft.map(h => h - r.h_ft[0]), name: `${s.name} (${r.file})`, mode: "lines", line: { color: PAL[i % 8] } });
    }
    Plotly.react("profPlot", tr, plotLayout({ title: { text: `Terrain profile at ${az}°`, font: { size: 13 } }, xaxis: { title: "km from tower", gridcolor: css("--line") }, yaxis: { title: "ft relative to tower base", gridcolor: css("--line") } }), { displaylogo: false, responsive: true });
  };
  $("#cmpAz").onchange = draw; draw();
  const sums = await Promise.all(ready.map(s => api("GET", `/api/v2/p/${SLUG}/sites/${s.id}/summary?step=5`)));
  const tr = sums.map((sm, i) => ({ type: "scatterpolar", r: sm.rows.map(r => r.slope1000), theta: sm.rows.map(r => r.az), name: ready[i].name, mode: "lines", line: { color: PAL[i % 8] } }));
  Plotly.react("slopePlot", tr, plotLayout({ margin: { l: 40, r: 40, t: 60, b: 40 }, title: { text: "Ground slope over the first 1,000 m (%)", font: { size: 13 } }, polar: { bgcolor: "rgba(0,0,0,0)", angularaxis: { direction: "clockwise", rotation: 90, gridcolor: css("--line") }, radialaxis: { gridcolor: css("--line") } } }), { displaylogo: false, responsive: true });
  const tg = p.targets;
  if (tg.length) {
    const near = (rows, az) => rows.reduce((a, b) => Math.abs(((b.az - az + 540) % 360) - 180) < Math.abs(((a.az - az + 540) % 360) - 180) ? b : a);
    $("#siteSlopeTbl").innerHTML = `<tr><th>Site</th>${tg.map(t => `<th class="n">${esc(t.name)} ${t.heading}°<br><span class="mute">slope 1 km / horizon</span></th>`).join("")}</tr>` +
      sums.map((sm, i) => `<tr><td>${esc(ready[i].name)}</td>${tg.map(t => { const r = near(sm.rows, t.heading); return `<td class="n">${fmt(r.slope1000, 1)} % / ${fmt(r.horizon_deg, 1)}°</td>`; }).join("")}</tr>`).join("");
  }
}

/* ---------------------------------------------------------------- 2. Targets */
function offsetsFrom(spread, step) {
  if (!spread || !step) return [0]; const o = []; for (let x = -spread; x <= spread + 1e-9; x += step) o.push(Math.round(x * 100) / 100); return o;
}
function rTargets() {
  const p = P(), el = $("#p-targets");
  el.innerHTML = `<h1>Targets</h1><p class="lead">A target is a path you want to work, for example Europe at 52°. Each target uses one ARRL elevation-angle file (.PRN)
  and one or more headings around its bearing. The result is the weighted mean of the FOM at those headings, exactly as you would average several HFTA runs.</p>
  <div class="card"><h2>Elevation-angle files (.PRN)</h2>
    <p class="small mute">The ARRL files come with the ARRL Antenna Book (e.g. W1-MA-EU.PRN). They are not included here.</p>
    <div class="row"><button id="prnBtn">Add .PRN files</button><input type="file" id="prnIn" multiple accept=".prn,.PRN" hidden></div>
    <div class="split" style="margin-top:10px"><div class="tbl"><table><tr><th>File</th><th></th></tr>
      ${S.prns.map(f => `<tr><td>${esc(f)}</td><td><button class="ghost small" data-prv="${esc(f)}">View</button></td></tr>`).join("") || `<tr><td class="mute">No files yet.</td><td></td></tr>`}</table></div>
      <div><div id="prnPlot" class="plot sm"></div></div></div></div>
  <div class="card"><h2>Targets</h2><div class="tbl"><table id="tgTbl"></table></div>
    <div class="row" style="margin-top:10px"><button id="addTg">Add target</button></div>
    <p class="small mute">Headings: the bearing ± spread in steps (e.g. ±8° in 8° steps gives three headings). Weights are equal unless you type them, e.g. "1, 2, 1".
    Weights from contest logs are not part of this release.</p></div>`;
  $("#prnBtn").onclick = () => $("#prnIn").click();
  $("#prnIn").onchange = async () => { const fd = new FormData(); [...$("#prnIn").files].forEach(x => fd.append("files", x));
    const r = await api("POST", `/api/v2/p/${SLUG}/prn`, fd, true); const bad = r.filter(x => x.error); toast(`${r.length - bad.length} added${bad.length ? `, ${bad.length} rejected: ${bad[0].error}` : ""}`, 4000);
    S = await api("GET", `/api/v2/p/${SLUG}`); rTargets(); };
  $$("[data-prv]").forEach(b => b.onclick = async () => {
    const d = await api("GET", `/api/v2/p/${SLUG}/prn/${encodeURIComponent(b.dataset.prv)}`);
    const tr = d.columns.slice(1).map((c, j) => ({ x: d.rows.map(r => r[0]), y: d.rows.map(r => r[j + 1]), name: c, mode: "lines", line: { color: PAL[j % 8] } }));
    Plotly.react("prnPlot", tr, plotLayout({ title: { text: esc(d.title), font: { size: 13 } }, xaxis: { title: "Elevation angle (°)", gridcolor: css("--line") }, yaxis: { title: "% of openings", gridcolor: css("--line") } }), { displaylogo: false, responsive: true });
  });
  const tb = $("#tgTbl");
  tb.innerHTML = `<tr><th>Name</th><th>.PRN file</th><th class="n">Bearing (°)</th><th class="n">± spread (°)</th><th class="n">Step (°)</th><th>Weights</th><th>Bands</th><th></th></tr>`;
  p.targets.forEach((t, i) => {
    const tr = document.createElement("tr");
    const spread = t.offsets.length > 1 ? Math.max(...t.offsets) : 0, step = t.offsets.length > 1 ? Math.abs(t.offsets[1] - t.offsets[0]) : 0;
    tr.innerHTML = `<td><input class="w" data-k="name" value="${esc(t.name)}"></td>
      <td><select data-k="prn">${["", ...S.prns].map(f => `<option ${f === t.prn ? "selected" : ""}>${esc(f)}</option>`).join("")}</select></td>
      <td class="n"><input type="number" data-k="heading" value="${t.heading}" min="0" max="359"></td>
      <td class="n"><input type="number" class="s" data-sp value="${spread}" min="0"></td><td class="n"><input type="number" class="s" data-st value="${step}" min="0"></td>
      <td><input class="s" style="width:110px" data-w value="${t.weights.every(w => w === t.weights[0]) ? "" : t.weights.join(", ")}" placeholder="equal"></td>
      <td><div class="bandbox">${META.bands.filter(b => b !== "6").map(b => `<label><input type="checkbox" data-b="${b}" ${t.bands.includes(b) ? "checked" : ""}>${b}</label>`).join("")}</div></td>
      <td><button class="danger small" data-del>Delete</button></td>`;
    $$("[data-k]", tr).forEach(inp => bind(inp, t, inp.dataset.k, null, inp.type === "number"));
    const reoff = () => { t.offsets = offsetsFrom(Number($("[data-sp]", tr).value), Number($("[data-st]", tr).value)); rew(); save(); };
    const rew = () => { const v = $("[data-w]", tr).value.trim(); const w = v ? v.split(/[ ,;]+/).map(Number) : [];
      t.weights = w.length === t.offsets.length ? w : t.offsets.map(() => 1); };
    $("[data-sp]", tr).onchange = reoff; $("[data-st]", tr).onchange = reoff; $("[data-w]", tr).onchange = () => { rew(); save(); };
    $$("[data-b]", tr).forEach(cb => cb.onchange = () => { t.bands = META.bands.filter(b => $(`[data-b="${b}"]`, tr)?.checked); save(); });
    $("[data-del]", tr).onclick = () => { p.targets.splice(i, 1); save(true).then(rTargets); };
    tb.appendChild(tr);
  });
  const first = $("[data-prv]"); if (first) first.click();
  $("#addTg").onclick = () => { p.targets.push({ id: uid("t"), name: "New target", prn: S.prns[0] || "", heading: 0, offsets: [-8, 0, 8], weights: [1, 1, 1], bands: ["20", "15", "10"] }); save(true).then(rTargets); };
}

/* ---------------------------------------------------------------- 3. Towers */
function bandsText(model) {
  const m = META.library[model]; if (!m) return "";
  if (m.bands === "any") return `any band (${m.hfta_type})`;
  return Object.entries(m.bands).sort((a, b) => META.bands.indexOf(a[0]) - META.bands.indexOf(b[0])).map(([b, x]) => `${b} m: ${x.hfta_type}`).join(", ");
}
function towerSvg(t) {
  const H = Math.max(t.height_ft || 0, ...t.antennas.map(a => a.h), 50) * 1.08, W = 150, Ht = 300, y = h => Ht - 10 - h / H * (Ht - 30);
  let s = `<svg viewBox="0 0 ${W} ${Ht}" class="tower-fig" role="img" aria-label="Tower drawing"><line x1="40" y1="${y(0)}" x2="40" y2="${y(t.height_ft || H / 1.08)}" stroke="${css("--ink")}" stroke-width="3"/>`;
  for (const g of (t.kind === "rotating" ? t.guys?.levels || [] : [])) s += `<line x1="40" y1="${y(g.h)}" x2="${W - 4}" y2="${y(Math.max(0, g.h * (1 - 100 / g.r)))}" stroke="${css("--mute")}" stroke-dasharray="3 3"/>`;
  for (const a of t.antennas) {
    const m = META.library[a.model] || {}, w = Math.min(90, (m.turning_radius_ft || 20) * 1.6);
    const col = m.bands && m.bands["40"] ? "#d9822b" : m.bands && m.bands["80"] ? "#8e44ad" : "#2c7a4b";
    s += `<line x1="40" y1="${y(a.h)}" x2="${40 + w}" y2="${y(a.h)}" stroke="${col}" stroke-width="4"/><text x="34" y="${y(a.h) + 4}" font-size="10" text-anchor="end" fill="${css("--ink")}">${a.h}</text>`;
  }
  return s + `<text x="40" y="${Ht - 0}" font-size="10" text-anchor="middle" fill="${css("--mute")}">ft</text></svg>`;
}
function rTowers() {
  const p = P(), el = $("#p-towers");
  el.innerHTML = `<h1>Towers</h1><p class="lead">Each tower is a stack of antennas. On each band, the antennas that work on that band form one HFTA stack (at most four, one antenna type).
  Rotating towers point at each target. Fixed towers point one way; the optional beam-loss layer then accounts for targets off that heading.</p>
  <div id="towerCards"></div><button id="addTw">Add tower</button><div id="scanCard"></div>`;
  const box = $("#towerCards"), models = Object.keys(META.library);
  p.towers.forEach((t, i) => {
    t.guys = t.guys || { levels: [], ice_in: 1.0, margin_ft: 2.0 };
    const c = document.createElement("div"); c.className = "card";
    c.innerHTML = `<h2><input class="w" data-k="name" value="${esc(t.name)}"></h2>
      <div class="split"><div class="figwrap">${towerSvg(t)}</div><div>
      <div class="row"><label>Type<select data-k="kind"><option value="rotating" ${t.kind === "rotating" ? "selected" : ""}>Rotating</option><option value="fixed" ${t.kind === "fixed" ? "selected" : ""}>Fixed</option></select></label>
        ${t.kind === "fixed" ? `<label>Fixed heading (°)<input type="number" data-k="heading" value="${t.heading ?? 0}"></label>` : ""}
        <label>Tower height (ft)<input type="number" data-k="height_ft" value="${t.height_ft ?? ""}"></label>
        <label>Switching<select data-k="switching">
          <option value="full" ${t.switching === "full" ? "selected" : ""}>Whole stack only</option>
          <option value="stackmatch" ${(t.switching || "stackmatch") === "stackmatch" ? "selected" : ""}>Stack switch: all, pairs, singles</option>
          <option value="all" ${t.switching === "all" ? "selected" : ""}>Every combination</option></select></label></div>
      <div class="row" style="margin-top:8px"><span class="small mute">Serves:</span>${p.targets.map(g => `<label style="flex-direction:row;align-items:center;gap:4px"><input type="checkbox" data-tg="${g.id}" ${!t.targets || t.targets.includes(g.id) ? "checked" : ""}>${esc(g.name)}</label>`).join("")}</div>
      <div class="tbl" style="margin-top:8px"><table><tr><th>Antenna</th><th class="n">Height (ft)</th><th>Bands and HFTA type</th><th></th></tr>
        ${t.antennas.map((a, j) => `<tr><td><select data-am="${j}">${models.map(m => `<option ${m === a.model ? "selected" : ""}>${esc(m)}</option>`).join("")}</select></td>
          <td class="n"><input type="number" data-ah="${j}" value="${a.h}"></td><td class="small">${esc(bandsText(a.model))}</td>
          <td><button class="danger small" data-ad="${j}">Remove</button></td></tr>`).join("")}</table></div>
      <div class="row" style="margin-top:8px"><button class="ghost" data-add>Add antenna</button><button class="danger" data-del>Delete tower</button></div>
      ${t.kind === "rotating" ? guyBlock(t) : ""}</div></div>`;
    $$("[data-k]", c).forEach(inp => bind(inp, t, inp.dataset.k, () => {
      if ((inp.dataset.k === "kind" || inp.dataset.k === "heading") && t.kind === "fixed")
        t.targets = p.targets.filter(g => Math.abs(((g.heading - (t.heading || 0)) % 360 + 540) % 360 - 180) <= 60).map(g => g.id);
      save(); rTowers(); }, inp.type === "number"));
    $$("[data-tg]", c).forEach(cb => cb.onchange = () => { t.targets = $$("[data-tg]", c).filter(x => x.checked).map(x => x.dataset.tg); save(); });
    $$("[data-am]", c).forEach(s => s.onchange = () => { t.antennas[s.dataset.am].model = s.value; save(); rTowers(); });
    $$("[data-ah]", c).forEach(s => s.onchange = () => { t.antennas[s.dataset.ah].h = Number(s.value); save(); rTowers(); });
    $$("[data-ad]", c).forEach(b => b.onclick = () => { t.antennas.splice(Number(b.dataset.ad), 1); save(); rTowers(); });
    $("[data-add]", c).onclick = () => { t.antennas.push({ model: "JK Big-Tri", h: 60 }); save(); rTowers(); };
    $("[data-del]", c).onclick = () => { p.towers.splice(i, 1); save(true).then(rTowers); };
    if (t.kind === "rotating") wireGuys(c, t);
    box.appendChild(c);
  });
  $("#addTw").onclick = () => { p.towers.push({ id: uid("w"), name: `Tower ${p.towers.length + 1}`, kind: "rotating", switching: "stackmatch", height_ft: 100, antennas: [{ model: "JK Big-Tri", h: 60 }], guys: { levels: [], ice_in: 1.0, margin_ft: 2.0 } }); save(true).then(rTowers); };
  scanCard();
}
function guyBlock(t) {
  const g = t.guys, wires = Object.keys(META.wires);
  return `<div class="card" style="margin-top:12px;background:var(--soft)"><h2>Guy and ice check <span class="chip">not part of HFTA</span></h2>
    <p class="small mute">An antenna sweeps a circle of its turning radius as the tower turns. Guys sag under ice; elements droop. Negative clearance = contact.</p>
    <div class="tbl"><table><tr><th class="n">Guy height (ft)</th><th class="n">Anchor radius (ft)</th><th>Guy line</th><th class="n">Initial tension (lb)</th><th></th></tr>
    ${g.levels.map((l, j) => `<tr><td class="n"><input type="number" data-gh="${j}" value="${l.h}"></td><td class="n"><input type="number" data-gr="${j}" value="${l.r}"></td>
      <td><select data-gw="${j}">${wires.map(w => `<option ${w === l.wire ? "selected" : ""}>${esc(w)}</option>`).join("")}</select></td>
      <td class="n"><input type="number" data-gt="${j}" value="${l.tension ?? META.wires[l.wire].tension}"></td><td><button class="danger small" data-gd="${j}">Remove</button></td></tr>`).join("")}</table></div>
    <div class="row" style="margin-top:8px"><button class="ghost small" data-gadd>Add guy level</button><button class="ghost small" data-rohn>Rohn 65G 160 ft standard</button>
      <label>Radial ice (in)<input type="number" step="0.25" data-gi value="${g.ice_in ?? 1}"></label><label>Hardware margin (ft)<input type="number" step="0.5" data-gm value="${g.margin_ft ?? 2}"></label>
      <button data-gcheck>Check clearances</button></div><div data-gout></div></div>`;
}
function wireGuys(c, t) {
  const g = t.guys, upd = (sel, key, num = true) => $$(sel, c).forEach(inp => inp.onchange = () => { g.levels[inp.getAttribute(sel.slice(1, -1))][key] = num ? Number(inp.value) : inp.value; save(); });
  upd("[data-gh]", "h"); upd("[data-gr]", "r"); upd("[data-gw]", "wire", false); upd("[data-gt]", "tension");
  $$("[data-gd]", c).forEach(b => b.onclick = () => { g.levels.splice(Number(b.dataset.gd), 1); save(); rTowers(); });
  $("[data-gadd]", c).onclick = () => { g.levels.push({ h: 50, r: 100, wire: "Phillystran HPTG-11200I", tension: 1120 }); save(); rTowers(); };
  $("[data-rohn]", c).onclick = () => { g.levels = [52, 100, 152].map(h => ({ h, r: 128, wire: "Phillystran HPTG-11200I", tension: 1120 })); t.height_ft = 160; save(); rTowers(); };
  $("[data-gi]", c).onchange = e => { g.ice_in = Number(e.target.value); save(); };
  $("[data-gm]", c).onchange = e => { g.margin_ft = Number(e.target.value); save(); };
  $("[data-gcheck]", c).onclick = async () => {
    await save(true); const r = await api("GET", `/api/v2/p/${SLUG}/guys/${t.id}`); const out = $("[data-gout]", c);
    const cls = v => v === null ? "" : v < 0 ? "neg" : v < 2 ? "amb" : "pos";
    out.innerHTML = `<div class="tbl"><table><tr><th>Antenna</th><th class="n">Height</th><th class="n">Turning radius</th><th class="n">Clearance, bare (ft)</th><th class="n">Clearance, ice (ft)</th><th>Limited by</th></tr>
      ${r.rows.sort((a, b) => b.h - a.h).map(x => `<tr><td>${esc(x.name)}</td><td class="n">${x.h}</td><td class="n">${x.turning_radius ?? "–"}</td><td class="n ${cls(x.clearance_bare)}">${fmt(x.clearance_bare, 1)}</td><td class="n ${cls(x.clearance)}">${fmt(x.clearance, 1)}</td><td class="small">${esc(x.limit)}</td></tr>`).join("")}</table></div>
      <div class="plot" data-gplot></div>`;
    const tr = [];
    for (const l of g.levels) { tr.push({ x: [0, l.r], y: [l.h, 0], mode: "lines", line: { color: css("--mute"), width: 1 }, name: `guy ${l.h} ft`, showlegend: false }); }
    r.rows.forEach(x => x.detail.forEach(d => { if (d.why.startsWith("below")) tr.push({ x: [x.turning_radius], y: [d.iced_wire_ft], mode: "markers", marker: { symbol: "x", color: "#1d5c8c" }, name: "iced guy at tip", showlegend: false }); }));
    r.rows.forEach((x, k) => tr.push({ x: [0, x.turning_radius || 0], y: [x.h, x.h], mode: "lines", line: { width: 5, color: x.clearance < 0 ? "#b33a3a" : "#2c7a4b" }, name: `${x.name} ${x.h} ft`, showlegend: false }));
    Plotly.react($("[data-gplot]", c), tr, plotLayout({ title: { text: "Side view: antenna reach and guys (× = iced guy at the antenna tips)", font: { size: 12 } }, xaxis: { title: "ft from tower", gridcolor: css("--line") }, yaxis: { title: "height (ft)", gridcolor: css("--line") } }), { displaylogo: false, responsive: true });
  };
}
function scanCard() {
  const p = P(); if (!p.sites.length || !p.targets.length) { $("#scanCard").innerHTML = ""; return; }
  $("#scanCard").innerHTML = `<div class="card" style="margin-top:14px"><h2>Height scan <span class="chip good">HFTA</span></h2>
    <p class="small mute">FOM of a single antenna against height, for one site, target and band. Useful to find good heights before building a stack.</p>
    <div class="row"><label>Site<select id="scSite">${p.sites.map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join("")}</select></label>
    <label>Target<select id="scTg">${p.targets.map(t => `<option value="${t.id}">${esc(t.name)}</option>`).join("")}</select></label>
    <label>Antenna<select id="scModel">${Object.keys(META.library).map(m => `<option>${esc(m)}</option>`).join("")}</select></label>
    <label>Band<select id="scBand">${META.bands.map(b => `<option ${b === "20" ? "selected" : ""}>${b}</option>`).join("")}</select></label>
    <label>From (ft)<input type="number" id="scLo" value="30"></label><label>To (ft)<input type="number" id="scHi" value="150"></label><label>Step (ft)<input type="number" id="scSt" value="5"></label>
    <button id="scGo">Scan</button></div><div class="prog" hidden id="scProg"><i></i></div><div id="scPlot" class="plot" hidden></div></div>`;
  $("#scGo").onclick = async () => {
    const body = { site: $("#scSite").value, target: $("#scTg").value, model: $("#scModel").value, band: $("#scBand").value, lo: $("#scLo").value, hi: $("#scHi").value, step: $("#scSt").value };
    const m = META.library[body.model]; if (m.bands !== "any" && !m.bands[body.band]) return toast(`${body.model} has no ${body.band} m elements`);
    const { job } = await api("POST", `/api/v2/p/${SLUG}/scan`, body); const r = await poll(job, $("#scProg"));
    if (!r) return; $("#scPlot").hidden = false;
    Plotly.react("scPlot", [{ x: r.rows.map(x => x.h), y: r.rows.map(x => x.fom), mode: "lines+markers", line: { color: PAL[0] } }],
      plotLayout({ title: { text: `${body.model} (${r.type}), ${body.band} m, ${$("#scTg").selectedOptions[0].text}`, font: { size: 13 } }, xaxis: { title: "height (ft)", gridcolor: css("--line") }, yaxis: { title: "FOM (dB)", gridcolor: css("--line") } }), { displaylogo: false, responsive: true });
  };
}
async function poll(job, bar) {
  bar.hidden = false; const i = $("i", bar);
  for (;;) {
    const j = await api("GET", `/api/job/${job}`);
    i.style.width = j.total ? `${100 * j.done / j.total}%` : "5%";
    if (j.state === "done") { bar.hidden = true; return j.result; }
    if (j.state === "error") { bar.hidden = true; toast(j.error, 6000); return null; }
    await new Promise(r => setTimeout(r, 600));
  }
}

/* ---------------------------------------------------------------- 4. Compare */
let CMP = { target: null, ref: null, delta: false };
async function rCompare() {
  const p = P(), el = $("#p-compare"), L = p.settings.layers;
  el.innerHTML = `<h1>Compare</h1><p class="lead">Every value is an HFTA Figure of Merit (dB, higher is better). Click a value to see the HFTA runs behind it and how to reproduce it.
    Differences of 0.3 dB or less are not significant.</p>
  <div class="grid2"><div class="card"><h2>Run</h2><p class="small mute" id="runInfo">${S.has_results ? "Last run " + esc(S.results_stamp) + "." : "Not run yet."}
    Runs already computed with the same inputs are reused.</p><div class="row"><button id="evalBtn">Evaluate</button></div><div class="prog" hidden id="evProg"><i></i></div></div>
  <div class="card"><h2>Layers beyond HFTA <span class="chip">off by default</span></h2>
    <label style="display:flex;gap:6px;align-items:flex-start"><input type="checkbox" id="lyJk" ${L.jk_gain ? "checked" : ""}><span>Maker gain: manufacturer free-space gain minus the HFTA generic type
      (e.g. Big-Tri 7-el on 10 m, which HFTA can only enter as 6-el).</span></label>
    <label style="display:flex;gap:6px;align-items:flex-start;margin-top:6px"><input type="checkbox" id="lyBl" ${L.beam_loss ? "checked" : ""}><span>Beam loss of fixed antennas off their heading
      (−12 × (offset ÷ beamwidth)² dB).</span></label>
    <p class="small mute">With a layer on, the HFTA value stays visible beside each total, and exports mark the layer.</p></div></div>
  <div class="card"><div class="row" id="cmpCtl"></div><div class="tbl" style="margin-top:10px"><table id="cmpTbl"></table></div><div id="cmpPlot" class="plot"></div></div>`;
  $("#lyJk").onchange = e => { L.jk_gain = e.target.checked; save(true).then(rCompare); };
  $("#lyBl").onchange = e => { L.beam_loss = e.target.checked; save(true).then(rCompare); };
  $("#evalBtn").onclick = async () => {
    await save(true); const bad = checkReady(); if (bad) return toast(bad, 5000);
    const { job } = await api("POST", `/api/v2/p/${SLUG}/evaluate`); const r = await poll(job, $("#evProg"));
    if (r) { toast(`${r.cells} results from ${r.runs} HFTA runs (${r.reused} reused)`); S = await api("GET", `/api/v2/p/${SLUG}`); rCompare(); }
  };
  RES = await api("GET", `/api/v2/p/${SLUG}/results`);
  if (!RES.cells.length) { $("#cmpTbl").innerHTML = `<tr><td class="mute">No results yet. Press Evaluate.</td></tr>`; return; }
  matrix();
}
function checkReady() {
  const p = P();
  if (!p.sites.some(s => (S.site_files[s.id] || {}).n)) return "Add terrain to at least one site (step 1).";
  if (!p.targets.length) return "Add a target (step 2)."; if (p.targets.some(t => !t.prn)) return "Every target needs a .PRN file (step 2).";
  if (!p.towers.length) return "Add a tower (step 3).";
  return null;
}
function matrix() {
  const p = P(), on = Object.values(p.settings.layers).some(Boolean);
  const tg = p.targets.filter(t => RES.cells.some(c => c.target === t.id)); if (!CMP.target || !tg.some(t => t.id === CMP.target)) CMP.target = tg[0]?.id;
  const site = id => p.sites.find(s => s.id === id)?.name ?? id, tower = id => p.towers.find(t => t.id === id)?.name ?? id;
  const cells = RES.cells.filter(c => c.target === CMP.target);
  const bands = META.bands.filter(b => cells.some(c => c.band === b));
  const rows = [...new Set(cells.map(c => c.site + "|" + c.tower))];
  if (!CMP.ref || !rows.includes(CMP.ref)) CMP.ref = rows[0];
  $("#cmpCtl").innerHTML = `<label>Target<select id="cmpTg">${tg.map(t => `<option value="${t.id}" ${t.id === CMP.target ? "selected" : ""}>${esc(t.name)} (${t.heading}°)</option>`).join("")}</select></label>
    <label style="flex-direction:row;align-items:center;gap:6px"><input type="checkbox" id="cmpDelta" ${CMP.delta ? "checked" : ""}> Show differences from the reference row</label>`;
  $("#cmpTg").onchange = e => { CMP.target = e.target.value; matrix(); };
  $("#cmpDelta").onchange = e => { CMP.delta = e.target.checked; matrix(); };
  const val = c => c ? (on ? c.total : c.hfta) : null;
  const get = (row, b) => cells.find(c => c.site + "|" + c.tower === row && c.band === b);
  const best = Object.fromEntries(bands.map(b => [b, Math.max(...rows.map(r => val(get(r, b)) ?? -1e9))]));
  let h = `<tr><th>Ref.</th><th>Site</th><th>Tower</th>${bands.map(b => `<th class="n">${b} m</th><th class="small mute">switch (ft)</th>`).join("")}</tr>`;
  for (const r of rows) {
    const [sid, tid] = r.split("|");
    h += `<tr><td><input type="radio" name="ref" value="${r}" ${r === CMP.ref ? "checked" : ""} aria-label="Reference row"></td><td>${esc(site(sid))}</td><td>${esc(tower(tid))}</td>`;
    for (const b of bands) {
      const c = get(r, b), v = val(c);
      if (!c) { h += `<td class="mute">–</td><td></td>`; continue; }
      if (c.issues.length) { h += `<td class="small neg" colspan="2">${esc(c.issues[0])}</td>`; continue; }
      let shown = fmt(v), cls = "n cell" + (Math.abs(v - best[b]) < 0.005 ? " best" : "");
      if (CMP.delta && r !== CMP.ref) { const rv = val(get(CMP.ref, b)); shown = rv === null ? "–" : (v - rv >= 0 ? "+" : "") + fmt(v - rv); }
      let sub = on ? `<br><span class="small mute">HFTA ${fmt(c.hfta)}</span>` : "";
      if (c.off_heading && !P().settings.layers.beam_loss) { sub += `<br><span class="chip warn" title="Fixed antennas point ${c.off_heading}° away from this target. Pure HFTA does not know where an antenna points. Switch on the beam-loss layer, or untick this target for the tower.">${c.off_heading}° off heading</span>`; cls += " off"; }
      h += `<td class="${cls}" data-i="${c.i}" title="Show the HFTA runs">${shown}${sub}</td><td class="small mute">${(c.use || []).join(" / ")}</td>`;
    }
    h += "</tr>";
  }
  $("#cmpTbl").innerHTML = h;
  $$("input[name=ref]").forEach(x => x.onchange = () => { CMP.ref = x.value; matrix(); });
  $$("td.cell").forEach(td => td.onclick = () => cellDrawer(Number(td.dataset.i)));
  const tr = rows.map((r, k) => { const [sid, tid] = r.split("|"); return { type: "bar", name: `${site(sid)} / ${tower(tid)}`, x: bands.map(b => b + " m"), y: bands.map(b => val(get(r, b))), marker: { color: PAL[k % 8] } }; });
  const all = tr.flatMap(t => t.y).filter(v => v !== null);
  Plotly.react("cmpPlot", tr, plotLayout({ barmode: "group", title: { text: "FOM by band", font: { size: 13 } }, yaxis: { title: "FOM (dB)", range: [Math.min(...all) - 2, Math.max(...all) + 1], gridcolor: css("--line") } }), { displaylogo: false, responsive: true });
}
async function cellDrawer(i) {
  const d = await api("GET", `/api/v2/p/${SLUG}/cell/${i}`), c = d.cell, p = P();
  const site = p.sites.find(s => s.id === c.site)?.name, tower = p.towers.find(t => t.id === c.tower)?.name, tgt = p.targets.find(t => t.id === c.target);
  const st = p.settings, best = c.options[c.best];
  let h = `<h2>${esc(site)} · ${esc(tower)} · ${esc(tgt.name)} · ${c.band} m</h2>
    <p><b>HFTA FOM ${fmt(c.hfta_fom)} dB</b> with antennas at ${best.heights.join(" / ")} ft. Layers: maker gain ${fmt(c.layers.jk_gain)} dB, beam loss ${fmt(c.layers.beam_loss)} dB (not included unless switched on).</p>
    <h3>Switch settings</h3><div class="tbl"><table><tr><th>Antennas in use (ft)</th>${c.options[0].az.map(a => `<th class="n">${a.az}°</th>`).join("")}<th class="n">Weighted mean</th></tr>
    ${c.options.map((o, k) => `<tr><td>${o.heights.join(" / ")}${k === c.best ? ' <span class="chip good">best</span>' : ""}</td>${o.az.map(a => `<td class="n">${fmt(a.fom)}</td>`).join("")}<td class="n"><b>${fmt(o.score)}</b></td></tr>`).join("")}</table></div>
    <p class="small mute">Weights: ${c.options[0].az.map(a => a.weight).join(", ")}. Mean = Σ(weight × FOM) ÷ Σ weight. Best setting = highest mean.</p>
    <div id="cellPlot" class="plot"></div>
    <h3>Reproduce in the original HFTA</h3><p class="small">Units feet. All antennas in phase. Ground: dielectric ${st.epsr}, conductivity ${st.sigma} S/m. Diffraction ${st.diffraction ? "on" : "off"}. Elevation file: <b>${esc(d.prn)}</b>.</p>
    <div class="tbl"><table><tr><th>Heading</th><th>Terrain file</th><th class="n">MHz</th><th>Type</th><th>Heights (ft)</th><th class="n">HFTA FOM</th></tr>
    ${best.az.map(a => { const r = d.runs[a.run]; return `<tr><td>${a.az}°</td><td>${esc(r.file)}</td><td class="n">${r.freq}</td><td>${r.hfta_type}</td><td>${r.heights_ft.join(" / ")}</td><td class="n">${fmt(a.fom)}</td></tr>`; }).join("")}</table></div>
    <button class="ghost small" id="copyRec">Copy these runs as text</button>`;
  $("#drawerBody").innerHTML = h; $("#drawer").hidden = false;
  const tr = best.az.map((a, k) => ({ x: d.angles, y: d.patterns[a.run], name: `${a.az}° (${d.runs[a.run].file})`, mode: "lines", line: { color: PAL[k % 8] } }));
  const ang = Object.keys(d.aoa).map(Number); tr.push({ type: "bar", x: ang, y: ang.map(a => d.aoa[a]), name: "arrival angles (%)", yaxis: "y2", marker: { color: "rgba(127,140,141,.35)" } });
  Plotly.react("cellPlot", tr, plotLayout({ margin: { l: 50, r: 60, t: 34, b: 42 }, title: { text: "Elevation pattern of the best setting, with arrival angles", font: { size: 13 } }, xaxis: { title: "elevation (°)", range: [0, 35], gridcolor: css("--line") },
    yaxis: { title: "gain (dBi)", gridcolor: css("--line") }, yaxis2: { overlaying: "y", side: "right", title: "% of openings", showgrid: false } }), { displaylogo: false, responsive: true });
  $("#copyRec").onclick = () => {
    const txt = best.az.map(a => { const r = d.runs[a.run]; return `HFTA: freq ${r.freq} MHz; ${r.heights_ft.length} x ${r.hfta_type} at ${r.heights_ft.join("/")} ft; terrain ${r.file} (all antennas); elevation file ${d.prn}; dielectric ${st.epsr}, conductivity ${st.sigma}; diffraction ${st.diffraction ? "on" : "off"} -> FOM ${fmt(a.fom)} dB`; }).join("\n");
    navigator.clipboard.writeText(txt).then(() => toast("Copied")).catch(() => toast("Copy failed: select the table instead"));
  };
}

/* ---------------------------------------------------------------- 5. Report */
function rReport() {
  const p = P(), on = Object.entries(p.settings.layers).filter(([k, v]) => v).map(([k]) => k);
  const ex = (k, t, d) => `<div class="card"><h2>${t}</h2><p class="small">${d}</p><button data-ex="${k}" ${!S.has_results && k !== "project" ? "disabled" : ""}>Download</button></div>`;
  $("#p-report").innerHTML = `<h1>Report and export</h1><p class="lead">${on.length ? `Layers beyond HFTA are on (${on.join(", ")}). Exports show the HFTA value and each layer in separate columns.` : "No layers are on: every exported number is a pure HFTA result."}</p>
  ${S.has_results ? "" : `<div class="note">Run the evaluation in step 4 first.</div>`}
  <div class="exports">
    ${ex("html", "Report (HTML)", "One self-contained page to read, print or send: inputs, comparison tables, charts, guy check, and how to reproduce.")}
    ${ex("xlsx", "Workbook (Excel)", "Results, every HFTA run, and the combination of runs as live formulas, so each number can be traced.")}
    ${ex("replay", "HFTA replay pack (zip)", "Every terrain and .PRN file used, each run with its exact HFTA inputs and FOM, expected patterns in OUT.PRN layout, and step-by-step instructions.")}
    ${ex("csv", "Results (CSV)", "One row per site, tower, target and band, for your own spreadsheet.")}
    ${ex("project", "Project file", "Everything needed to open this study again or share it (terrain and .PRN files are in the replay pack).")}
  </div>`;
  $$("[data-ex]").forEach(b => b.onclick = () => { window.location = `/api/v2/p/${SLUG}/export/${b.dataset.ex}`; });
}

/* ---------------------------------------------------------------- start */
async function openProject(slug) {
  SLUG = slug; S = await api("GET", `/api/v2/p/${slug}`);
  try { localStorage.setItem("hfta-project", slug); } catch (e) { /* storage unavailable */ }
  render();
}
async function init() {
  META = await api("GET", "/api/v2/meta");
  const sel = $("#projSel"), fill = () => sel.innerHTML = META.projects.map(n => `<option ${n === SLUG ? "selected" : ""}>${esc(n)}</option>`).join("");
  let last = null; try { last = localStorage.getItem("hfta-project"); } catch (e) { last = null; }
  if (!META.projects.length) { const r = await api("POST", "/api/v2/projects", { name: "My station" }); META.projects = [r.slug]; }
  SLUG = META.projects.includes(last) ? last : META.projects[0]; fill();
  sel.onchange = () => openProject(sel.value);
  $("#newProj").onclick = () => { modal(`<h2>New project</h2><form id="npf" class="row"><label>Name<input id="npn" class="w" required></label><button>Create</button><button type="button" class="ghost" id="npc">Cancel</button></form>`);
    $("#npc").onclick = closeModal; $("#npf").onsubmit = async e => { e.preventDefault(); const r = await api("POST", "/api/v2/projects", { name: $("#npn").value });
      META.projects.push(r.slug); SLUG = r.slug; fill(); closeModal(); openProject(r.slug); go("sites"); }; };
  $$(".step").forEach(b => b.onclick = () => go(b.dataset.step));
  $("#drawerX").onclick = () => $("#drawer").hidden = true;
  document.addEventListener("keydown", e => { if (e.key === "Escape") { $("#drawer").hidden = true; closeModal(); } });
  await openProject(SLUG);
}
init().catch(e => { document.body.innerHTML = `<p style="padding:20px">Could not start: ${esc(e.message)}</p>`; });
