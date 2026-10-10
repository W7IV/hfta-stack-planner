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
  /* Keep the same project object after saving: the page's inputs hold references into it. Replacing it with the
     server's copy made later edits go to an old object and be lost. Only the file and result status come from the server. */
  const go = async () => { try { const proj = P(), r = await api("PUT", `/api/v2/p/${SLUG}`, proj); if (r.slug === SLUG) { r.project = proj; S = r; }
    $("#saveState").textContent = "Saved"; status(); } catch (e) { $("#saveState").textContent = "Not saved: " + e.message; } };
  if (now) return go(); saveTimer = setTimeout(go, 500);
}
function bind(el, obj, key, after, num) {
  el.addEventListener("change", () => { obj[key] = num ? (el.value === "" ? null : Number(el.value)) : (el.type === "checkbox" ? el.checked : el.value); save(); after && after(); });
}
function status() {
  const p = P(), b = $("#hftaBadge"); b.className = "badge pure"; b.textContent = "Pure HFTA";
  b.title = "Every number shown can be reproduced in the original HFTA";
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
        <button class="ghost" data-act="auto" title="Downloads USGS 3DEP elevation data for this position (United States only) and writes one profile per degree">Fetch terrain online (USGS)</button>
        <button class="ghost" data-act="flat">Flat ground</button>
        ${f.n ? `<button class="ghost" data-act="download">Download .PRO files</button>` : ""}
        ${f.n ? `<button class="ghost" data-act="clear">Remove profiles</button>` : ""}
        <button class="ghost" data-act="move" title="New site at a distance and bearing from this one, to test how sensitive the result is to the exact position (as HFTA's move-the-tower check)">Copy, moved…</button>
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
    const dl = $("[data-act=download]", c); if (dl) dl.onclick = () => { window.location.href = `/api/v2/p/${SLUG}/sites/${s.id}/download`; };
    const clr = $("[data-act=clear]", c); if (clr) clr.onclick = async () => { await api("DELETE", `/api/v2/p/${SLUG}/sites/${s.id}/files`); s.terrain = { source: "" }; await save(true); rSites(); };
    $("[data-act=del]", c).onclick = async () => { p.sites.splice(i, 1); await save(true); rSites(); };
    $("[data-act=dem]", c).onclick = () => demDialog(s);
    $("[data-act=move]", c).onclick = () => moveDialog(s);
    const autoBtn = $("[data-act=auto]", c);
    if (autoBtn) autoBtn.onclick = async () => {
      /* Read the inputs directly: a value typed but not yet committed (no change event) is still used. */
      const lat = Number($("[data-k=lat]", c).value), lon = Number($("[data-k=lon]", c).value);
      if (!$("[data-k=lat]", c).value || !$("[data-k=lon]", c).value) { toast("Enter latitude and longitude for this site first.", 4000); return; }
      s.lat = lat; s.lon = lon;
      autoBtn.disabled = true; autoBtn.textContent = "Fetching…";
      try {
        const r = await api("POST", `/api/v2/p/${SLUG}/sites/${s.id}/auto`,
          { lat, lon, prefix: s.name, az_step: 1, spacing_m: 30, length_m: 4410 });
        s.terrain = { source: r.source || "USGS 3DEP (online)" };
        toast(`${r.written} profiles written. Ground ${r.ground_elevation_m} m.${r.short_azimuths?.length ? ` ${r.short_azimuths.length} cut short at DEM edge.` : ""}`, 6000);
        await save(true); rSites();
      } catch (e) { toast(e.message, 8000); autoBtn.disabled = false; autoBtn.textContent = "Fetch terrain online (USGS)"; }
    };
    box.appendChild(c);
  });
  siteCompare();
}
function moveDialog(s) {
  if (s.lat == null || s.lon == null) { toast("Enter latitude and longitude for this site first.", 4000); return; }
  modal(`<h2>Copy site, moved</h2>
  <p class="small mute">Makes a new site at the given distance and bearing from "${esc(s.name)}", then fetches its terrain online (USGS, United States only).
  Use it to see how much the result changes when the tower moves, as with HFTA's move-the-tower check.</p>
  <form id="mvForm" class="row">
    <label>Distance (ft)<input type="number" name="dist" value="100" min="1" required></label>
    <label>Bearing (° true)<input type="number" name="brg" value="${P().targets[0]?.heading ?? 0}" min="0" max="360" required></label>
    <label style="flex:1">New site name<input name="name" value="${esc(s.name)} +100 ft" style="width:100%"></label>
    <div style="width:100%;display:flex;gap:8px;margin-top:8px"><button type="submit">Create and fetch terrain</button><button type="button" class="ghost" id="mvCancel">Cancel</button></div></form>`);
  $("#mvCancel").onclick = closeModal;
  const nm = $("#mvForm [name=name]"), dist = $("#mvForm [name=dist]"), brg = $("#mvForm [name=brg]");
  const auto = () => { nm.value = `${s.name} +${dist.value} ft at ${brg.value}°`; }; dist.oninput = brg.oninput = auto; auto();
  $("#mvForm").onsubmit = async e => {
    e.preventDefault(); const d = Number(dist.value) * 0.3048, b = Number(brg.value) * Math.PI / 180, R = 6371008.8;
    const p1 = s.lat * Math.PI / 180, l1 = s.lon * Math.PI / 180;
    const p2 = Math.asin(Math.sin(p1) * Math.cos(d / R) + Math.cos(p1) * Math.sin(d / R) * Math.cos(b));
    const l2 = l1 + Math.atan2(Math.sin(b) * Math.sin(d / R) * Math.cos(p1), Math.cos(d / R) - Math.sin(p1) * Math.sin(p2));
    const ns = { id: uid("s"), name: nm.value.trim() || `${s.name} moved`, lat: Math.round(p2 * 180 / Math.PI * 1e6) / 1e6, lon: Math.round(l2 * 180 / Math.PI * 1e6) / 1e6, notes: `Copy of ${s.name}, ${dist.value} ft at ${brg.value}°`, terrain: { source: "" } };
    P().sites.push(ns); closeModal(); await save(true);
    const btn = e.target.querySelector("button[type=submit]"); btn.disabled = true;
    try {
      const r = await api("POST", `/api/v2/p/${SLUG}/sites/${ns.id}/auto`, { lat: ns.lat, lon: ns.lon, prefix: ns.name, az_step: 1, spacing_m: 30, length_m: 4410 });
      ns.terrain = { source: r.source || "USGS 3DEP (online)" }; toast(`${ns.name}: ${r.written} profiles. Ground ${r.ground_elevation_m} m.`, 6000); await save(true);
    } catch (err) { toast(`${ns.name} created; terrain not fetched: ${err.message}`, 8000); }
    rSites();
  };
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
    /* Title: region from the ARRL file name (W1-MA-EU.PRN -> Europe). Files that do not follow that pattern show their own first line. */
    const REGION = { AF: "Africa", AS: "Asia", EU: "Europe", JA: "Japan", OC: "Oceania", SA: "South America", US: "USA" };
    const m = /-([A-Z]{2})\.PRN$/i.exec(b.dataset.prv), region = m && REGION[m[1].toUpperCase()];
    Plotly.react("prnPlot", tr, plotLayout({ title: { text: region ? `${region} (${esc(b.dataset.prv)})` : esc(d.title), font: { size: 13 } },
      margin: { l: 50, r: 16, t: 28, b: 80 }, legend: { orientation: "h", y: -0.4 },
      xaxis: { title: { text: "Elevation angle (°)", standoff: 6 }, gridcolor: css("--line") }, yaxis: { title: "% of openings", gridcolor: css("--line") } }), { displaylogo: false, responsive: true });
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
  $("#addTg").onclick = () => {
    const id = uid("t"); p.targets.push({ id, name: "New target", prn: S.prns[0] || "", heading: 0, offsets: [-8, 0, 8], weights: [1, 1, 1], bands: ["20", "15", "10"] });
    /* A new target is served by every tower and counts in the compromise search until the user unticks it. */
    p.towers.forEach(t => { if (Array.isArray(t.targets) && !t.targets.includes(id)) t.targets.push(id); });
    if (p.settings.compromise) p.settings.compromise.weights[id] = 1;
    save(true).then(rTargets);
  };
}

/* ---------------------------------------------------------------- 3. Towers */
/* Antennas as HFTA sees them: per band, the number of elements (1 = dipole). */
const elName = n => n === 1 ? "Dipole" : `${n}-el`;
const elOf = a => Object.fromEntries(Object.entries(a.el || {}).filter(([, n]) => n));
const bandsOf = a => META.bands.filter(b => elOf(a)[b]);
function describe(a) {
  const e = elOf(a), bs = bandsOf(a); if (!bs.length) return "no bands";
  return new Set(bs.map(b => e[b])).size === 1 ? `${bs.join("/")} m ${elName(e[bs[0]])}` : bs.map(b => `${b} m ${elName(e[b])}`).join(", ");
}
function towerBands(extra = []) {
  /* The HF bands the ARRL elevation-angle files cover (80 to 10 m), plus 160/6 m if any antenna already uses them. */
  const used = new Set(extra.flatMap(a => bandsOf(a)));
  return META.bands.filter(b => (b !== "160" && b !== "6") || used.has(b));
}
const elSelect = (attr, b, n) => `<select class="s el" ${attr} title="${b} m: elements (HFTA type)"><option value="">–</option>${META.elements.map(k => `<option value="${k}" ${k === n ? "selected" : ""}>${elName(k)}</option>`).join("")}</select>`;
/* Spacing warnings: the same rules as core/spacing.py. HFTA has no mutual coupling; warnings never change a number. */
function spacingCheck(ants) {
  const r = P().settings.spacing || META.spacing_defaults, out = [], lam = b => 983.571 / (Number(P().settings.band_freq?.[b]) || META.band_freq[b]);
  for (const b of META.bands) {
    const hs = ants.filter(a => elOf(a)[b]).map(a => Number(a.h)).sort((x, y) => x - y);
    for (let k = 1; k < hs.length; k++) {
      const ft = hs[k] - hs[k - 1], wl = ft / lam(b), lvl = wl < r.red_wl ? "red" : wl < r.amber_wl ? "amber" : null;
      if (lvl) out.push({ level: lvl, kind: "stack", text: `${b} m: antennas at ${hs[k - 1]} and ${hs[k]} ft are ${ft} ft = ${wl.toFixed(2)} wavelength apart. ${lvl === "red" ? "Too close: HFTA overstates the stacking gain by 1 dB or more." : "Close: HFTA overstates the stacking gain, probably by 0.5-1 dB."}` });
    }
  }
  for (let i = 0; i < ants.length; i++) for (let j = i + 1; j < ants.length; j++) {
    const a = ants[i], c = ants[j]; if (bandsOf(a).some(b => elOf(c)[b])) continue;
    const gap = Math.abs(a.h - c.h), lvl = gap < r.gap_red_ft ? "red" : gap < r.gap_amber_ft ? "amber" : null;
    const [lo, hi] = a.h <= c.h ? [a, c] : [c, a];
    if (lvl) out.push({ level: lvl, kind: "gap", text: `${describe(lo)} at ${lo.h} ft and ${describe(hi)} at ${hi.h} ft are only ${gap} ft apart. ${lvl === "red" ? "Too close" : "Close"}: interaction likely, not modelled by HFTA.` });
  }
  return out.sort((x, y) => (x.level === "red" ? 0 : 1) - (y.level === "red" ? 0 : 1));
}
const worstOf = w => w.some(x => x.level === "red") ? "red" : w.length ? "amber" : null;
function warnList(w, okText = "Spacing: no warnings.") {
  if (!w.length) return `<p class="small mute" style="margin:6px 0 0">${okText}</p>`;
  return `<ul class="warnl">${w.map(x => `<li class="${x.level}"><b>${x.level === "red" ? "TOO CLOSE" : "CLOSE"}</b> ${esc(x.text)}</li>`).join("")}</ul>`;
}
function towerSvg(t) {
  /* Side view to one scale: the same feet-per-pixel vertically and horizontally, so a guy line and an
     antenna's turning radius can be compared by eye. Guys run from the tower to their anchor on the ground.
     Antennas are drawn to their turning radius (20 ft if not given); a dotted bar means the radius was not given. */
  const guys = t.guys?.levels || [], tower = t.height_ft || Math.max(...t.antennas.map(a => a.h), 0);
  const Hft = Math.max(tower, ...t.antennas.map(a => a.h), ...guys.map(g => g.h), 50) * 1.06;
  const Xft = Math.max(...guys.map(g => g.r || 0), ...t.antennas.map(a => a.turning_radius || 20), 30) * 1.04;
  const Ht = 300, X0 = 40, top = 18, bottom = Ht - 14, maxW = 280;
  let k = (bottom - top) / Hft;                        // px per ft
  if (X0 + Xft * k + 6 > maxW) k = (maxW - X0 - 6) / Xft;   // wide guy anchors: shrink both axes together
  const W = Math.max(150, Math.ceil(X0 + Xft * k + 6)), y = h => bottom - h * k, x = ft => X0 + ft * k;
  let s = `<svg viewBox="0 0 ${W} ${Ht}" class="tower-fig" role="img" aria-label="Tower side view, to scale">`;
  s += `<line x1="${X0 - 30}" y1="${y(0)}" x2="${W}" y2="${y(0)}" stroke="${css("--line")}"/>`;                 // ground
  s += `<line x1="${X0}" y1="${y(0)}" x2="${X0}" y2="${y(tower)}" stroke="${css("--ink")}" stroke-width="3"/>`;   // tower
  for (const g of guys) {
    if (!(g.h > 0 && g.r > 0)) continue;
    s += `<line x1="${X0}" y1="${y(g.h)}" x2="${x(g.r)}" y2="${y(0)}" stroke="${css("--mute")}" stroke-dasharray="3 3"/>`;
    s += `<circle cx="${x(g.r)}" cy="${y(0)}" r="2" fill="${css("--mute")}"/>`;
  }
  for (const a of t.antennas) {
    const e = elOf(a), r = a.turning_radius || 20;
    const col = e["80"] || e["160"] ? "#8e44ad" : e["40"] || e["30"] ? "#d9822b" : "#2c7a4b";
    s += `<line x1="${X0}" y1="${y(a.h)}" x2="${x(r)}" y2="${y(a.h)}" stroke="${col}" stroke-width="4" ${a.turning_radius ? "" : 'stroke-dasharray="4 3"'}/>`;
    s += `<text x="${X0 - 6}" y="${y(a.h) + 4}" font-size="10" text-anchor="end" fill="${css("--ink")}">${a.h}</text>`;
  }
  s += `<text x="${X0}" y="${Ht - 2}" font-size="10" text-anchor="middle" fill="${css("--mute")}">ft</text>`;
  if (Xft > 40) s += `<text x="${x(Xft / 1.04)}" y="${Ht - 2}" font-size="10" text-anchor="end" fill="${css("--mute")}">${Math.round(Xft / 1.04)} ft</text>`;
  return s + `</svg>`;
}
function rTowers() {
  const p = P(), el = $("#p-towers");
  el.innerHTML = `<h1>Towers</h1><p class="lead">Each tower is a stack of antennas. On each band, the antennas that work on that band form one HFTA stack (at most four, one antenna type).
  HFTA treats the antennas as facing the azimuth of the terrain file. Tick the targets each tower serves: that choice sets the directions it is evaluated in.
  Location: pick the site (from the Sites page) where this tower stands, or leave "Every site" to try the tower at all sites and compare them.</p>
  <div id="spcCard"></div><div id="towerCards"></div><button id="addTw">Add tower</button><div id="compCard"></div><div id="scanCard"></div>`;
  const box = $("#towerCards");
  spacingCard();
  p.towers.forEach((t, i) => {
    t.guys = t.guys || { levels: [], ice_in: 1.0, margin_ft: 2.0 };
    const c = document.createElement("div"); c.className = "card"; const tb = towerBands(t.antennas);
    const sw = worstOf(spacingCheck(t.antennas)), site = p.sites.find(s => s.id === t.site);
    const schip = site ? `<span class="chip ${(S.site_files[site.id] || {}).n ? "good" : "warn"}">at ${esc(site.name)}${(S.site_files[site.id] || {}).n ? "" : " (no terrain)"}</span>` : `<span class="chip">every site</span>`;
    c.innerHTML = `<h2><input class="w" data-k="name" value="${esc(t.name)}"> ${schip}${sw ? ` <span class="chip ${sw === "red" ? "bad" : "warn"}">${sw === "red" ? "Spacing too close" : "Spacing close"}</span>` : ""}</h2>
      <div class="split"><div class="figwrap">${towerSvg(t)}</div><div>
      <div class="row"><label>Location<select data-k="site">
          <option value="" ${!t.site ? "selected" : ""}>Every site (compare sites)</option>
          ${p.sites.map(s => `<option value="${s.id}" ${t.site === s.id ? "selected" : ""}>${esc(s.name)}${(S.site_files[s.id] || {}).n ? "" : " (no terrain)"}</option>`).join("")}</select></label>
        <label>Tower height (ft)<input type="number" data-k="height_ft" value="${t.height_ft ?? ""}"></label>
        <label>Switching<select data-k="switching">
          <option value="full" ${t.switching === "full" ? "selected" : ""}>Whole stack only</option>
          <option value="stackmatch" ${(t.switching || "stackmatch") === "stackmatch" ? "selected" : ""}>Stack switch: all, pairs, singles</option>
          <option value="all" ${t.switching === "all" ? "selected" : ""}>Every combination</option></select></label></div>
      <div class="row" style="margin-top:8px"><span class="small mute">Serves:</span>${p.targets.map(g => `<label style="flex-direction:row;align-items:center;gap:4px"><input type="checkbox" data-tg="${g.id}" ${!t.targets || t.targets.includes(g.id) ? "checked" : ""}>${esc(g.name)}</label>`).join("")}</div>
      <div class="tbl" style="margin-top:8px"><table><tr><th class="n">Height (ft)</th>${tb.map(b => `<th>${b} m</th>`).join("")}<th class="n" title="Only for the guy check">Turning radius (ft)</th><th class="n" title="Only for the guy check">Element droop (ft)</th><th></th></tr>
        ${t.antennas.map((a, j) => `<tr><td class="n"><input type="number" data-ah="${j}" value="${a.h}"></td>
          ${tb.map(b => `<td>${elSelect(`data-ae="${j}" data-band="${b}"`, b, elOf(a)[b])}</td>`).join("")}
          <td class="n"><input type="number" class="s" step="0.5" data-atr="${j}" value="${a.turning_radius ?? ""}" placeholder="–"></td>
          <td class="n"><input type="number" class="s" step="0.5" data-adr="${j}" value="${a.droop ?? ""}" placeholder="–"></td>
          <td><button class="danger small" data-ad="${j}">Remove</button></td></tr>`).join("")}</table></div>
      <p class="small mute" style="margin:4px 0 0">Choose the number of elements on each band, as in HFTA (Dipole, 2–6 or 8 elements). Turning radius and droop are used only by the guy check.</p>
      ${warnList(spacingCheck(t.antennas))}
      <div class="row" style="margin-top:8px"><button class="ghost" data-add>Add antenna</button>
        <button class="ghost" data-copy title="Make a copy of this tower (same antennas, guys and targets) at another site">Copy to…</button>
        <button class="danger" data-del>Delete tower</button></div>
      ${guyBlock(t)}</div></div>`;
    $$("[data-k]", c).forEach(inp => bind(inp, t, inp.dataset.k, () => rTowers(), inp.type === "number"));
    $$("[data-tg]", c).forEach(cb => cb.onchange = () => { t.targets = $$("[data-tg]", c).filter(x => x.checked).map(x => x.dataset.tg); save(); });
    $$("[data-ae]", c).forEach(s => s.onchange = () => { const a = t.antennas[s.dataset.ae]; a.el = a.el || {}; if (s.value) a.el[s.dataset.band] = Number(s.value); else delete a.el[s.dataset.band]; save(); rTowers(); });
    $$("[data-atr]", c).forEach(s => s.onchange = () => { t.antennas[s.dataset.atr].turning_radius = s.value === "" ? null : Number(s.value); save(); });
    $$("[data-adr]", c).forEach(s => s.onchange = () => { t.antennas[s.dataset.adr].droop = s.value === "" ? null : Number(s.value); save(); });
    $$("[data-ah]", c).forEach(s => s.onchange = () => { t.antennas[s.dataset.ah].h = Number(s.value); save(); rTowers(); });
    $$("[data-ad]", c).forEach(b => b.onclick = () => { t.antennas.splice(Number(b.dataset.ad), 1); save(); rTowers(); });
    $("[data-add]", c).onclick = () => { const last = t.antennas[t.antennas.length - 1]; t.antennas.push({ h: last ? last.h + 30 : 60, el: last ? { ...last.el } : { "20": 4, "15": 4, "10": 4 }, turning_radius: last?.turning_radius ?? null, droop: last?.droop ?? null }); save(); rTowers(); };
    $("[data-del]", c).onclick = () => { p.towers.splice(i, 1); save(true).then(rTowers); };
    $("[data-copy]", c).onclick = () => copyTowerDialog(t, i);
    wireGuys(c, t);
    box.appendChild(c);
  });
  compCard();
  $("#addTw").onclick = () => { p.towers.push({ id: uid("w"), name: `Tower ${p.towers.length + 1}`, switching: "stackmatch", height_ft: 100, antennas: [{ h: 60, el: { "20": 4, "15": 4, "10": 4 }, turning_radius: null, droop: null }], guys: { levels: [], ice_in: 1.0, margin_ft: 2.0 } }); save(true).then(rTowers); };
  scanCard();
}
function spacingCard() {
  const r = P().settings.spacing = { ...META.spacing_defaults, ...(P().settings.spacing || {}) };
  $("#spcCard").innerHTML = `<div class="card"><h2>Spacing warnings <span class="chip">not part of HFTA</span></h2>
  <p class="small mute">HFTA has no mutual coupling: it gives a stack its full stacking gain at any spacing. Close antennas lose part of it.
  NEC-2 check on 40 m: 0.22 wavelength lost 2.2 dB, 0.43 wavelength lost 0.7 dB. HFTA also ignores interaction between antennas on different bands.
  Warnings never change a number.</p>
  <div class="row"><label>Stack: too close below (wavelength)<input type="number" step="0.05" data-sr="red_wl" value="${r.red_wl}"></label>
  <label>Stack: close below (wavelength)<input type="number" step="0.05" data-sr="amber_wl" value="${r.amber_wl}"></label>
  <label>Other bands: too close below (ft)<input type="number" step="1" data-sr="gap_red_ft" value="${r.gap_red_ft}"></label>
  <label>Other bands: close below (ft)<input type="number" step="1" data-sr="gap_amber_ft" value="${r.gap_amber_ft}"></label>
  <span class="small mute">Wavelength on 40 m ≈ ${(983.571 / META.band_freq["40"]).toFixed(0)} ft, 20 m ≈ ${(983.571 / META.band_freq["20"]).toFixed(0)} ft.</span></div></div>`;
  $$("[data-sr]").forEach(inp => inp.onchange = () => { r[inp.dataset.sr] = Number(inp.value); save(); rTowers(); });
}
function copyTowerDialog(t, i) {
  /* Like HFTA's copy: the same stack at another site, as a separate tower you can then change on its own. */
  const p = P(), sites = p.sites.filter(s => s.id !== t.site);
  modal(`<h2>Copy "${esc(t.name)}" to another site</h2>
  <p class="small mute">The copy has the same antennas, guys and targets. It is a separate tower: change heights or antennas on either one without affecting the other.
  To try one tower design at every site without copies, set its Location to "Every site" instead.</p>
  <form id="cpForm" class="row">
    <label>Site<select name="site">${sites.map(s => `<option value="${s.id}">${esc(s.name)}${(S.site_files[s.id] || {}).n ? "" : " (no terrain)"}</option>`).join("")}
      <option value="">Every site (compare sites)</option></select></label>
    <label style="flex:1">Name of the copy<input name="name" style="width:100%"></label>
    <div style="width:100%;display:flex;gap:8px;margin-top:8px"><button type="submit">Copy</button><button type="button" class="ghost" id="cpCancel">Cancel</button></div></form>`);
  $("#cpCancel").onclick = closeModal;
  const sel = $("#cpForm [name=site]"), nm = $("#cpForm [name=name]");
  const auto = () => { const s = p.sites.find(x => x.id === sel.value); nm.value = s ? `${t.name} at ${s.name}` : `${t.name} (every site)`; }; sel.onchange = auto; auto();
  $("#cpForm").onsubmit = e => {
    e.preventDefault();
    const copy = JSON.parse(JSON.stringify(t)); copy.id = uid("w"); copy.site = sel.value || null; copy.name = nm.value.trim() || `${t.name} copy`;
    p.towers.splice(i + 1, 0, copy); closeModal(); save(true).then(rTowers);
  };
}
function guyBlock(t) {
  const g = t.guys, wires = Object.keys(META.wires);
  return `<div class="card" style="margin-top:12px;background:var(--soft)"><h2>Guy and ice check <span class="chip">not part of HFTA</span></h2>
    <p class="small mute">For antennas that turn: each sweeps a circle of its turning radius. Guys sag under ice; elements droop. Negative clearance = contact. Leave empty if not needed.</p>
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
    <label>Antenna type<select id="scEl">${META.elements.map(k => `<option value="${k}" ${k === 4 ? "selected" : ""}>${elName(k)}</option>`).join("")}</select></label>
    <label>Band<select id="scBand">${META.bands.map(b => `<option ${b === "20" ? "selected" : ""}>${b}</option>`).join("")}</select></label>
    <label>From (ft)<input type="number" id="scLo" value="30"></label><label>To (ft)<input type="number" id="scHi" value="150"></label><label>Step (ft)<input type="number" id="scSt" value="5"></label>
    <button id="scGo">Scan</button></div><div class="prog" hidden id="scProg"><i></i></div><div id="scPlot" class="plot" hidden></div></div>`;
  $("#scGo").onclick = async () => {
    const body = { site: $("#scSite").value, target: $("#scTg").value, elements: Number($("#scEl").value), band: $("#scBand").value, lo: $("#scLo").value, hi: $("#scHi").value, step: $("#scSt").value };
    const { job } = await api("POST", `/api/v2/p/${SLUG}/scan`, body); const r = await poll(job, $("#scProg"));
    if (!r) return; $("#scPlot").hidden = false;
    Plotly.react("scPlot", [{ x: r.rows.map(x => x.h), y: r.rows.map(x => x.fom), mode: "lines+markers", line: { color: PAL[0] } }],
      plotLayout({ title: { text: `${r.type}, ${body.band} m, ${$("#scTg").selectedOptions[0].text}`, font: { size: 13 } }, xaxis: { title: "height (ft)", gridcolor: css("--line") }, yaxis: { title: "FOM (dB)", gridcolor: css("--line") } }), { displaylogo: false, responsive: true });
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
  const p = P(), el = $("#p-compare"); status();
  el.innerHTML = `<h1>Compare</h1><p class="lead">Every value is an HFTA Figure of Merit (dB, higher is better). Click a value to see the HFTA runs behind it and how to reproduce it.
    Differences of 0.3 dB or less are not significant.</p>
  <div class="grid2"><div class="card"><h2>Run</h2><p class="small mute" id="runInfo">${S.has_results ? "Last run " + esc(S.results_stamp) + "." : "Not run yet."}
    Runs already computed with the same inputs are reused.</p><div class="row"><button id="evalBtn">Evaluate</button></div><div class="prog" hidden id="evProg"><i></i></div></div>
  <div class="card"><h2>Spacing warnings <span class="chip">not part of HFTA</span></h2>
    <p class="small">A <span class="sp red">&#9888;</span> or <span class="sp amber">&#9888;</span> beside a value: the antennas on that band are too close or close
    (set the limits in step 3). HFTA has no mutual coupling, so the value is probably optimistic. The value itself is still the pure HFTA result.</p></div></div>
  <div class="card"><div class="row" id="cmpCtl"></div><div class="tbl" style="margin-top:10px"><table id="cmpTbl"></table></div><div id="cmpPlot" class="plot"></div></div>`;
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
  const p = P();
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
  const val = c => c ? c.hfta : null;
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
      let sub = c.spacing ? ` <span class="sp ${c.spacing}" title="${esc(c.spacing_text.join("\n"))}">&#9888;</span>` : "";
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
    <p><b>HFTA FOM ${fmt(c.hfta_fom)} dB</b> with antennas at ${best.heights.join(" / ")} ft. </p>
    ${(c.spacing || []).length ? `<h3>Spacing warnings</h3>${warnList(c.spacing)}<p class="small mute">HFTA has no mutual coupling. The FOM above is the pure HFTA value and is probably optimistic.</p>` : ""}
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
  const p = P();
  const ex = (k, t, d) => `<div class="card"><h2>${t}</h2><p class="small">${d}</p><button data-ex="${k}" ${!S.has_results && !["project", "bundle"].includes(k) ? "disabled" : ""}>Download</button></div>`;
  $("#p-report").innerHTML = `<h1>Report and export</h1><p class="lead">Every exported number is a pure HFTA result. Spacing warnings and the guy check are included as notes; they never change a number.</p>
  ${S.has_results ? "" : `<div class="note">Run the evaluation in step 4 first.</div>`}
  <p class="small mute">Calculations by OpenHFTA (RioDXGroup, github.com/RioDXGroup/openhfta), used unchanged. HFTA by R. Dean Straw, N6BV, published with
  <i>The ARRL Antenna Book</i>. ARRL elevation-angle files are copyright ARRL and are supplied by the user. Not affiliated with or endorsed by ARRL or the OpenHFTA authors.</p>
  <div class="exports">
    ${ex("html", "Report (HTML)", "One self-contained page to read, print or send: inputs, comparison tables, charts, guy check, and how to reproduce.")}
    ${ex("xlsx", "Workbook (Excel)", "Results, every HFTA run, and the combination of runs as live formulas, so each number can be traced.")}
    ${ex("replay", "HFTA replay pack (zip)", "Every terrain and .PRN file used, each run with its exact HFTA inputs and FOM, expected patterns in OUT.PRN layout, and step-by-step instructions.")}
    ${ex("csv", "Results (CSV)", "One row per site, tower, target and band, for your own spreadsheet.")}
    ${ex("bundle", "Project with files (zip)", "The project with its terrain and .PRN files. Open it on another computer or on a hosted copy with “Open project zip”. Results are recomputed there.")}
    ${ex("project", "Project file (settings only)", "The project settings without terrain or .PRN files.")}
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
  $("#openProj").onclick = () => $("#openProjIn").click();
  $("#openProjIn").onchange = async () => {
    const f = $("#openProjIn").files[0]; if (!f) return; const fd = new FormData(); fd.append("file", f);
    try { const r = await api("POST", "/api/v2/projects/import", fd, true); META.projects.push(r.slug); SLUG = r.slug; fill(); await openProject(r.slug); go("sites"); toast(`Opened as “${r.slug}”`); }
    catch (e) { toast(e.message, 5000); }
    $("#openProjIn").value = "";
  };
  $$(".step").forEach(b => b.onclick = () => go(b.dataset.step));
  $("#drawerX").onclick = () => $("#drawer").hidden = true;
  document.addEventListener("keydown", e => { if (e.key === "Escape") { $("#drawer").hidden = true; closeModal(); } });
  await openProject(SLUG);
}
init().catch(e => { document.body.innerHTML = `<p style="padding:20px">Could not start: ${esc(e.message)}</p>`; });

/* ---------------------------------------------------------------- one-tower compromise */
function compForm() {
  const p = P();
  p.settings.compromise = p.settings.compromise || { site: p.sites[0]?.id, weights: {}, switching: "stackmatch", min_gap: 15, max_height: 160, guys_from_tower: "",
    groups: [{ name: "Tribander", el: { "20": 4, "15": 4, "10": 4 }, count: 3, lo: 20, hi: 130, step: 5, min_spacing: 30, equal_tol: 10, turning_radius: null, droop: null },
             { name: "40 m Yagi", el: { "40": 3 }, count: 2, lo: 40, hi: 160, step: 5, min_spacing: 60, equal_tol: "", turning_radius: null, droop: null }] };
  return p.settings.compromise;
}
function compCard() {
  const p = P(), f = compForm(), tb = towerBands(f.groups); if (!p.sites.length || !p.targets.length) { $("#compCard").innerHTML = ""; return; }
  const guyTowers = p.towers.filter(t => (t.guys?.levels || []).length);
  $("#compCard").innerHTML = `<div class="card" style="margin-top:14px"><h2>Best compromise for one tower <span class="chip good">HFTA</span></h2>
  <p class="small mute">Searches the heights of one tower for the best result over all ticked targets together. For each target and band the best stack-switch setting is used,
  as in Compare. Score per target = mean over bands; overall = weighted mean over targets. Every number is HFTA runs plus this arithmetic.</p>
  <div class="row"><label>Site<select id="cmSite">${p.sites.map(x => `<option value="${x.id}" ${x.id === f.site ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></label>
    <label>Switching<select id="cmSw"><option value="stackmatch" ${f.switching === "stackmatch" ? "selected" : ""}>Stack switch: all, pairs, singles</option><option value="full" ${f.switching === "full" ? "selected" : ""}>Whole stack only</option><option value="all" ${f.switching === "all" ? "selected" : ""}>Every combination</option></select></label>
    <label>Max height (ft)<input type="number" id="cmMax" value="${f.max_height}" title="Upper limit for every group; a group's own To (ft) cannot go above it"></label>
    <label>Min gap between groups (ft)<input type="number" id="cmGap" value="${f.min_gap}"></label>
    <label>Group order<select id="cmOrder" title="Which group is above which. The list order of the groups below is used.">
      <option value="any" ${(f.order || "any") === "any" ? "selected" : ""}>Any (HFTA decides)</option>
      <option value="first_top" ${f.order === "first_top" ? "selected" : ""}>As listed, first group on top</option>
      <option value="first_bottom" ${f.order === "first_bottom" ? "selected" : ""}>As listed, first group at the bottom</option></select></label>
    <label>Respect guys of<select id="cmGuy"><option value="">no guy check</option>${guyTowers.map(t => `<option value="${t.id}" ${t.id === f.guys_from_tower ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select></label></div>
  <h3 class="small" style="margin:12px 0 4px">Targets and weights</h3>
  <div class="row">${p.targets.map(t => `<label style="flex-direction:row;align-items:center;gap:4px"><input type="checkbox" data-ct="${t.id}" ${f.weights[t.id] !== 0 ? "checked" : ""}>${esc(t.name)}
    <input type="number" class="s" step="0.5" min="0" data-cw="${t.id}" value="${f.weights[t.id] ?? 1}" title="Weight"></label>`).join("")}</div>
  <h3 class="small" style="margin:12px 0 4px">Antenna groups (each group has its own bands)</h3>
  <div class="tbl"><table><tr><th>Name</th>${tb.map(b => `<th>${b} m</th>`).join("")}<th class="n">Count</th><th class="n">From (ft)</th><th class="n" title="Highest height searched for this group (also capped by Max height above)">To (ft)</th><th class="n">Step</th><th class="n">Min spacing (ft)</th><th class="n">Equal ± (ft)</th><th class="n">Turning radius (ft)</th><th class="n">Droop (ft)</th><th></th></tr>
  ${f.groups.map((g, j) => `<tr><td><input class="w" style="width:110px" data-gn="${j}" value="${esc(g.name || "")}"></td>
    ${tb.map(b => `<td>${elSelect(`data-ge="${j}" data-band="${b}"`, b, (g.el || {})[b])}</td>`).join("")}
    ${["count", "lo", "hi", "step", "min_spacing", "equal_tol", "turning_radius", "droop"].map(k => `<td class="n"><input type="number" class="s" data-gf="${j}" data-key="${k}" value="${g[k] ?? ""}" ${k === "equal_tol" ? 'placeholder="any"' : ["turning_radius", "droop"].includes(k) ? 'placeholder="–"' : ""}></td>`).join("")}
    <td><button class="danger small" data-gx="${j}">Remove</button></td></tr>`).join("")}</table></div>
  <p class="small mute" style="margin:4px 0 0">Elements per band as in HFTA. Turning radius and droop are needed only with the guy check.</p>
  ${warnList(compFormWarnings(f), "Spacing rules: no warnings.")}
  <div class="row" style="margin-top:8px"><button class="ghost small" id="cmAddG">Add group</button><button id="cmGo">Find best compromise</button></div>
  <div class="prog" hidden id="cmProg"><i></i></div><div id="cmOut"></div></div>`;
  const sv = () => save();
  $("#cmSite").onchange = e => { f.site = e.target.value; sv(); }; $("#cmSw").onchange = e => { f.switching = e.target.value; sv(); };
  $("#cmMax").onchange = e => { f.max_height = Number(e.target.value); sv(); compCard(); }; $("#cmGap").onchange = e => { f.min_gap = Number(e.target.value); sv(); compCard(); };
  $("#cmGuy").onchange = e => { f.guys_from_tower = e.target.value; sv(); };
  $("#cmOrder").onchange = e => { f.order = e.target.value; sv(); };
  $$("[data-ct]").forEach(cb => cb.onchange = () => { f.weights[cb.dataset.ct] = cb.checked ? Number($(`[data-cw="${cb.dataset.ct}"]`).value || 1) : 0; sv(); });
  $$("[data-cw]").forEach(inp => inp.onchange = () => { f.weights[inp.dataset.cw] = Number(inp.value); $(`[data-ct="${inp.dataset.cw}"]`).checked = Number(inp.value) > 0; sv(); });
  $$("[data-gn]").forEach(inp => inp.onchange = () => { f.groups[inp.dataset.gn].name = inp.value; sv(); });
  $$("[data-ge]").forEach(sel => sel.onchange = () => { const g = f.groups[sel.dataset.ge]; g.el = g.el || {}; if (sel.value) g.el[sel.dataset.band] = Number(sel.value); else delete g.el[sel.dataset.band]; sv(); compCard(); });
  $$("[data-gf]").forEach(inp => inp.onchange = () => { f.groups[inp.dataset.gf][inp.dataset.key] = inp.value === "" ? (["turning_radius", "droop"].includes(inp.dataset.key) ? null : "") : Number(inp.value); sv(); compCard(); });
  $$("[data-gx]").forEach(b => b.onclick = () => { f.groups.splice(Number(b.dataset.gx), 1); sv(); compCard(); });
  $("#cmAddG").onclick = () => { f.groups.push({ name: "", el: {}, count: 1, lo: 30, hi: 120, step: 5, min_spacing: 30, equal_tol: "", turning_radius: null, droop: null }); sv(); compCard(); };
  $("#cmGo").onclick = async () => {
    await save(true);
    const targets = p.targets.filter(t => f.weights[t.id] !== 0).map(t => t.id);
    if (!targets.length) return toast("Tick at least one target");
    const body = { site: f.site, targets, weights: Object.fromEntries(targets.map(t => [t, f.weights[t] ?? 1])), groups: f.groups, switching: f.switching,
      min_gap: f.min_gap, max_height: f.max_height, guys_from_tower: f.guys_from_tower || null, order: f.order || "any", min_spacing: 30, top: 25 };
    const { job } = await api("POST", `/api/v2/p/${SLUG}/compromise`, body); const r = await poll(job, $("#cmProg")); if (r) compResult(r);
  };
  api("GET", `/api/v2/p/${SLUG}/compromise`).then(r => { if (r && r.rows) compResult(r); });
}
function compFormWarnings(f) {
  const r = P().settings.spacing || META.spacing_defaults, out = [];
  for (const g of f.groups) {
    const bs = bandsOf(g); if (!bs.length || Number(g.count) < 2 || g.min_spacing === "") continue;
    const b = bs[0], lam = 983.571 / (Number(P().settings.band_freq?.[b]) || META.band_freq[b]), wl = Number(g.min_spacing) / lam;
    const lvl = wl < r.red_wl ? "red" : wl < r.amber_wl ? "amber" : null;
    if (lvl) out.push({ level: lvl, text: `${g.name || describe(g)}: minimum spacing ${g.min_spacing} ft = ${wl.toFixed(2)} wavelength on ${b} m. The search may pick stacks that are ${lvl === "red" ? "too close" : "close"}; HFTA will overstate their stacking gain. Raise it to ${Math.ceil(r.amber_wl * lam)} ft or more to avoid this.` });
  }
  for (const g of f.groups) if (Number(g.hi) > Number(f.max_height)) out.push({ level: "amber", text: `${g.name || describe(g)}: "To" is ${g.hi} ft but Max height is ${f.max_height} ft, so the search stops at ${f.max_height} ft. Raise Max height to search higher.` });
  if (f.groups.length > 1 && Number(f.min_gap) < r.gap_amber_ft) out.push({ level: Number(f.min_gap) < r.gap_red_ft ? "red" : "amber", text: `Minimum gap between groups ${f.min_gap} ft is below ${r.gap_amber_ft} ft: antennas on different bands may interact; HFTA does not model this.` });
  return out;
}
function compResult(r) {
  const p = P(), lay = l => l.map((g, i) => `${r.groups[i].name || r.groups[i].model} ${g.join(" / ")}`).join("; ");
  $("#cmOut").innerHTML = `<p class="small mute" style="margin-top:10px">Spacing column: hover a chip for details. Rows are ranked by HFTA only; a warning means HFTA is probably optimistic for that layout.
    ${r.evaluated} layouts compared from ${r.runs} HFTA runs (${esc(r.stamp || "")}).
    Loss = difference from the best possible for that target alone (shown in the last row). Heights in ft.</p>
  <div class="tbl"><table><tr><th>#</th><th>Layout</th><th>Spacing</th><th class="n">Overall</th>${r.targets.map(t => `<th class="n">${esc(t.name)} <span class="mute">(w ${r.weights[t.id]})</span></th>`).join("")}<th></th></tr>
  ${r.rows.map((x, k) => { const sw = worstOf(x.spacing || []); return `<tr><td>${k + 1}</td><td>${esc(lay(x.layout))}</td>
    <td>${sw ? `<span class="chip ${sw === "red" ? "bad" : "warn"}" title="${esc((x.spacing || []).map(w => w.text).join("\n"))}">${sw === "red" ? "Too close" : "Close"}</span>` : `<span class="small mute">OK</span>`}</td>
    <td class="n"><b>${fmt(x.overall)}</b></td>
    ${r.targets.map(t => `<td class="n">${fmt(x.targets[t.id])}<br><span class="small ${x.loss[t.id] < -1 ? "neg" : x.loss[t.id] < -0.3 ? "amb" : "mute"}">${x.loss[t.id] >= 0 ? "best" : fmt(x.loss[t.id])}</span></td>`).join("")}
    <td><button class="ghost small" data-apply="${k}">Use as tower</button></td></tr>`; }).join("")}
  <tr><td></td><td class="mute">Best for each target alone</td><td></td><td></td>${r.targets.map(t => `<td class="n mute">${fmt(r.own_best[t.id])}<br><span class="small">${esc(lay(r.own_layout[t.id]))}</span></td>`).join("")}<td></td></tr></table></div>
  ${r.curves?.length ? `<h3 class="small" style="margin:14px 0 4px">Score against height, by group</h3>
  <p class="small mute" style="margin:0 0 6px">Why a height was chosen. Solid line = overall (weighted over targets); thin lines = each target. For a stack, the best layout with its top antenna at that height.
  Rules between groups (gap, order, guys) can move the chosen height away from a group's own peak.</p>
  <p class="small" style="margin:0 0 6px"><b>Heights searched:</b> ${r.curves.map(c => `${esc(c.name)} ${Math.min(...c.heights)}–${Math.max(...c.heights)} ft`).join("; ")}.
  The limit for each group is its own To (ft), capped by Max height. Heights outside this range were not calculated.</p>
  <div class="row" style="align-items:center"><label>Group<select id="cmCurveSel">${r.curves.map((c, i) => `<option value="${i}">${esc(c.name)}</option>`).join("")}</select></label></div>
  <div id="cmCurve" class="plot sm"></div>` : ""}`;
  if (r.curves?.length) {
    const draw = () => {
      const c = r.curves[Number($("#cmCurveSel").value)];
      const tr = [{ x: c.heights, y: c.overall, name: "Overall", mode: "lines+markers", line: { color: css("--ink"), width: 3 } }];
      r.targets.forEach((t, i) => tr.push({ x: c.heights, y: c.targets[t.id], name: t.name, mode: "lines", line: { color: PAL[i % 8], width: 1 } }));
      Plotly.react("cmCurve", tr, plotLayout({ title: { text: `${c.name}: HFTA score (FOM) against height`, font: { size: 13 } }, margin: { l: 50, r: 16, t: 28, b: 80 }, legend: { orientation: "h", y: -0.4 },
        xaxis: { title: { text: "height of the (top) antenna, ft", standoff: 6 }, gridcolor: css("--line") }, yaxis: { title: "FOM", gridcolor: css("--line") } }), { displaylogo: false, responsive: true });
    };
    $("#cmCurveSel").onchange = draw; draw();
  }
  $$("[data-apply]").forEach(b => b.onclick = async () => {
    const x = r.rows[Number(b.dataset.apply)], f = compForm();
    const ants = x.layout.flatMap((hs, i) => hs.map(h => ({ h, el: { ...r.groups[i].el }, turning_radius: r.groups[i].turning_radius ?? null, droop: r.groups[i].droop ?? null })));
    const g = p.towers.find(t => t.id === f.guys_from_tower);
    p.towers.push({ id: uid("w"), name: `Compromise ${lay(x.layout)}`.slice(0, 60), switching: f.switching, height_ft: f.max_height, targets: r.targets.map(t => t.id),
      antennas: ants, guys: g ? JSON.parse(JSON.stringify(g.guys)) : { levels: [], ice_in: 1.0, margin_ft: 2.0 } });
    await save(true); toast("Added as a new tower. Run Compare to see the HFTA runs behind it."); rTowers();
  });
}
