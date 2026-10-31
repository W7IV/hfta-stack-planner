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
  if (r.status === 401 && j.login) { location.href = "/login?next=" + encodeURIComponent(location.pathname); throw new Error("Please log in"); }
  if (!r.ok) { const e = new Error(j.error || r.statusText); e.status = r.status; e.body = j; throw e; } return j;
}
function toast(msg, ms = 2600) { const t = $("#toast"); t.textContent = msg; t.hidden = false; clearTimeout(t._h); t._h = setTimeout(() => t.hidden = true, ms); }
/* Saving. Each save is tied to the project it was made for (a project switch within the 500 ms delay still saves
   the edited project, not the new one). Saves run one after another, never out of order. save(true) returns a promise
   that fails when the server refuses or cannot be reached, so actions that need the saved project stop there. */
let saveChain = Promise.resolve(), pendingSave = null;
function saveState(text, cls) { const e = $("#saveState"); e.textContent = text; e.className = cls || "mute"; }
function save(now) {
  saveState("Saving…"); clearTimeout(saveTimer);
  const slug = SLUG, proj = P();
  const go = () => {
    pendingSave = null;
    const run = saveChain.then(async () => {
      const r = await api("PUT", `/api/v2/p/${slug}`, proj);
      /* Keep the same project object after saving: the page's inputs hold references into it. Only the file and
         result status come from the server. */
      if (slug === SLUG && r.slug === SLUG) { const rev = r.project.rev; r.project = P(); P().rev = rev; S = r; saveState("Saved ✓", "ok"); status(); }
    }).catch(e => {
      saveState("Not saved: " + e.message, "bad");
      if (e.status === 409) conflictBanner(); else toast("Not saved: " + e.message, 7000);
      throw e;
    });
    saveChain = run.catch(() => {});
    return run;
  };
  if (now) return go();
  pendingSave = go; saveTimer = setTimeout(go, 500);
  return Promise.resolve();
}
/* Another window saved this project after this page loaded. Editing continues locally but nothing more is saved until
   the page is reloaded, so the two versions cannot overwrite each other in turns. */
function conflictBanner() {
  if ($("#conflict")) return;
  const d = document.createElement("div"); d.id = "conflict"; d.className = "note"; d.style.cssText = "position:fixed;top:56px;left:50%;transform:translateX(-50%);z-index:60;max-width:640px;border-left-color:#b33a3a";
  d.innerHTML = `<b>This project was changed in another window or on another device.</b> Your last change was not saved. Reload to see the latest version
    (your unsaved edits here will be lost), or copy them first. <button id="conflictReload" style="margin-left:8px">Reload</button>`;
  document.body.appendChild(d); $("#conflictReload").onclick = () => location.reload();
}
/* Finish any waiting save now (before switching project or leaving the page). */
function flushSave() { clearTimeout(saveTimer); return pendingSave ? pendingSave().catch(() => {}) : saveChain; }
window.addEventListener("beforeunload", e => { if (pendingSave) { flushSave(); e.preventDefault(); } });
function bind(el, obj, key, after, num) {
  el.addEventListener("change", () => { obj[key] = num ? (el.value === "" ? null : Number(el.value)) : (el.type === "checkbox" ? el.checked : el.value); save(); after && after(); });
}
function status() {
  const p = P(), b = $("#hftaBadge"); b.className = "badge pure"; b.textContent = "OpenHFTA";
  b.title = "Every number shown can be reproduced in the original HFTA";
  const ready = p.sites.filter(s => (S.site_files[s.id] || {}).n).length;
  $("#st-sites").textContent = `${ready}/${p.sites.length} with terrain`;
  $("#st-targets").textContent = `${p.targets.length} targets, ${S.prns.length} .PRN`;
  $("#st-towers").textContent = `${p.towers.length} towers`;
  $("#st-compare").textContent = S.has_results ? "results " + (S.results_stamp || "").slice(5, 16) : "not run";
  const done = { sites: ready > 0, targets: p.targets.some(t => t.prn), towers: p.towers.length > 0, compare: !!S.has_results, report: !!S.has_results };
  $$(".step").forEach(b => b.classList.toggle("done", !!done[b.dataset.step]));
}
function go(step) {
  STEP = step; $$(".step").forEach(b => b.classList.toggle("on", b.dataset.step === step));
  $$(".page").forEach(p => p.hidden = p.id !== "p-" + step); render();
}
function render() { status(); ({ sites: rSites, targets: rTargets, towers: rTowers, compare: rCompare, report: rReport })[STEP](); clampLeads(); }
new MutationObserver(() => clampLeads()).observe(document.querySelector("main") || document.body, { childList: true, subtree: true });
/* Page introductions show two lines; "More" opens the rest. A reader who knows the page is not made to scroll past it. */
function clampLeads() {
  $$(".page:not([hidden]) p.lead").forEach(p => {
    if (p.dataset.clamped) return;
    p.classList.add("clamp");
    if (p.scrollHeight <= p.clientHeight + 2) { p.classList.remove("clamp"); p.dataset.clamped = "1"; return; }
    const a = document.createElement("a"); a.href = "#"; a.className = "more"; a.textContent = "More";
    a.onclick = e => { e.preventDefault(); const open = p.classList.toggle("clamp"); a.textContent = open ? "More" : "Less"; };
    p.insertAdjacentElement("afterend", a); p.dataset.clamped = "1";
  });
}
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
  <div class="row"><button id="addSite">Add site</button><button class="ghost" id="libSite" title="Add a site saved from another project, with its terrain">Add from library…</button></div>
  <div id="siteCompare"></div>`;
  $("#soil").onchange = e => { const [s, k] = META.soils[e.target.value]; Object.assign(st, { soil: e.target.value, sigma: s, epsr: k }); save(); rSites(); };
  bind($("#epsr"), st, "epsr", null, true); bind($("#sigma"), st, "sigma", null, true); bind($("#diff"), st, "diffraction");
  $("#libSite").onclick = () => libAddDialog("sites");
  $("#addSite").onclick = () => { p.sites.push({ id: uid("s"), name: `Site ${p.sites.length + 1}`, lat: null, lon: null, notes: "", terrain: { source: "" } }); save(true).then(rSites); };
  const box = $("#siteCards");
  p.sites.forEach((s, i) => {
    const f = S.site_files[s.id] || { n: 0 }, c = document.createElement("div"); c.className = "card";
    const fh = s.terrain?.far_horizon, fhChip = fh && fh.max_deg != null ? ` <span class="chip ${fh.max_deg >= 1 ? "warn" : ""}" title="Ground between ${(fh.start_m / 1000).toFixed(1)} and ${(fh.end_m / 1000).toFixed(0)} km, which the HFTA profiles do not include, seen from ${Math.round(fh.antenna_m * 3.28)} ft up the tower. Above about 1° it can block the lowest arrival angles; HFTA cannot show that. Highest at ${fh.max_az}°">far horizon ${fh.max_deg.toFixed(1)}° at ${fh.max_az}°</span>` : "";
    const dup = f.dup, dupBox = dup ? `<div class="warnbox" data-dup><b>Two files for ${dup.headings} heading${dup.headings > 1 ? "s" : ""}.</b> Using the newer set
        (${esc(dup.used.map(u => `${u.example}, ${u.n} file${u.n > 1 ? "s" : ""}, ${u.newest} UTC`).join("; "))}); not used: ${esc(dup.unused.map(u => `${u.example}, ${u.n} file${u.n > 1 ? "s" : ""}, ${u.newest} UTC`).join("; "))}.
        Older imports did not replace files of the same heading. Keep one set so the terrain in use is clear.
        <button class="ghost small" data-act="dup-newer">Keep the newer set</button> <button class="ghost small" data-act="dup-older">Keep the older set instead</button></div>` : "";
    const tchip = f.n ? `<span class="chip good">${f.n} profiles${f.step ? `, every ${f.step}°` : ""}${s.terrain?.length_m && s.terrain.length_m > 5000 ? `, ${(s.terrain.length_m / 1000).toFixed(0)} km` : ""}</span>${s.terrain?.source ? ` <span class="chip">${esc(s.terrain.source)}</span>` : ""}${fhChip}`
                      : `<span class="chip warn">No terrain yet</span>`;
    c.innerHTML = `<h2><input class="w" value="${esc(s.name)}" data-k="name" aria-label="Site name"> ${tchip}</h2>
      <div class="row"><label>Latitude<input type="number" step="0.00001" data-k="lat" value="${s.lat ?? ""}"></label>
      <label>Longitude<input type="number" step="0.00001" data-k="lon" value="${s.lon ?? ""}"></label>
      <label style="flex:1">Notes<input data-k="notes" value="${esc(s.notes || "")}" style="width:100%"></label></div>
      <div class="groups" style="margin-top:12px">
        <div class="group"><div class="gcap">Terrain from your own files</div><div class="row"><label>Source of the files you import<select data-src><option>MicroDEM .PRO</option><option>K6TU terrain set</option><option>Other .PRO files</option></select></label>
        <button data-act="import">Import .PRO or .zip</button><input type="file" multiple accept=".pro,.PRO,.zip" hidden data-file>
        <button class="ghost" data-act="dem">Generate from DEM file</button>
        </div></div>
        <div class="group"><div class="gcap">Terrain made here</div><div class="row"><button class="ghost" data-act="auto" title="Downloads elevation data for this position and writes one profile per degree. Inside the United States: USGS 3DEP (1 m). Elsewhere: AWS Terrain Tiles (30 m, worldwide)">Fetch terrain online</button>
        <select data-autosrc title="Where the elevation data comes from"><option value="auto">source by position</option><option value="3dep">USGS 3DEP (US, 1 m)</option><option value="tiles">Terrain Tiles (worldwide, 30 m)</option></select>
        <select data-autolen title="HFTA profiles hold at most 148 points. 4.4 km at 30 m is the HFTA standard. 10 km needs 68 m spacing, which changes results on rough ground by about 1 dB; use it only to see the effect of a distant ridge, and compare like with like"><option value="std">4.4 km, 30 m (HFTA standard)</option><option value="long">10 km, 68 m (coarser)</option></select>
        <button class="ghost" data-act="flat">Flat ground</button>
        </div></div>
        <div class="group"><div class="gcap">This site</div><div class="row">${f.n ? `<button class="ghost" data-act="download">Download .PRO files</button>` : ""}
        ${f.n ? `<button class="ghost" data-act="clear">Remove profiles</button>` : ""}
        <button class="ghost" data-act="lib" title="Save this site, with its position and terrain files, to the library shared by all your projects">Save to library</button>
        <button class="ghost" data-act="move" title="New site at a distance and bearing from this one, to test how sensitive the result is to the exact position (as HFTA's move-the-tower check)">Copy, moved…</button>
        <button class="danger" data-act="del">Delete site</button></div></div>
      </div>
      <p class="small mute" style="margin:8px 0 0">K6TU sells HFTA-ready one-degree terrain sets: <a href="https://www.k6tu.net" target="_blank" rel="noopener">k6tu.net</a>.
      MicroDEM makes .PRO files from free elevation data. A DEM file is processed on this computer only.</p>${dupBox}`;
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
    for (const keep of ["newer", "older"]) { const b = $(`[data-act=dup-${keep}]`, c); if (b) b.onclick = async () => {
      if (!confirm(`Delete the ${keep === "newer" ? "older" : "newer"} file of every heading that has two? The other set stays.`)) return;
      const r = await api("DELETE", `/api/v2/p/${SLUG}/sites/${s.id}/duplicates?keep=${keep}`); toast(`${r.deleted} files deleted`); await save(true); rSites(); }; }
    const clr = $("[data-act=clear]", c); if (clr) clr.onclick = async () => { await api("DELETE", `/api/v2/p/${SLUG}/sites/${s.id}/files`); s.terrain = { source: "" }; await save(true); rSites(); };
    $("[data-act=del]", c).onclick = async () => { p.sites.splice(i, 1); await save(true); rSites(); };
    $("[data-act=dem]", c).onclick = () => demDialog(s);
    $("[data-act=move]", c).onclick = () => moveDialog(s);
    $("[data-act=lib]", c).onclick = () => libSaveDialog("sites", s);
    const autoBtn = $("[data-act=auto]", c);
    if (autoBtn) autoBtn.onclick = async () => {
      /* Read the inputs directly: a value typed but not yet committed (no change event) is still used. */
      const lat = Number($("[data-k=lat]", c).value), lon = Number($("[data-k=lon]", c).value);
      if (!$("[data-k=lat]", c).value || !$("[data-k=lon]", c).value) { toast("Enter latitude and longitude for this site first.", 4000); return; }
      s.lat = lat; s.lon = lon;
      // Remove the previous warning only when the user explicitly retries.
      c.querySelector("[data-terrain-fetch-error]")?.remove();
      autoBtn.disabled = true; autoBtn.textContent = "Fetching…";
      try {
        const r = await api("POST", `/api/v2/p/${SLUG}/sites/${s.id}/auto`,
          { lat, lon, prefix: s.name, az_step: 1, ...($("[data-autolen]", c).value === "long" ? { spacing_m: 68, length_m: 10000 } : { spacing_m: 30, length_m: 4410 }), source: $("[data-autosrc]", c).value });
        s.terrain = { source: r.source || "USGS 3DEP (online)", length_m: r.length_m, spacing_m: r.spacing_m, far_horizon: r.far_horizon || null };
        toast(`${r.written} profiles written from ${r.source}. Ground ${r.ground_elevation_m} m.${r.resolution_m ? ` Data spacing ${r.resolution_m} m.` : ""}${r.short_azimuths?.length ? ` ${r.short_azimuths.length} cut short at the data edge.` : ""}`, 7000);
        await save(true); rSites();
      } catch (e) {
        const retryable = e.body?.retryable === true || e.status === 503 || e.status === 429;
        const notice = document.createElement("div");
        notice.className = "warnbox"; notice.dataset.terrainFetchError = ""; notice.setAttribute("role", "alert");
        const msg = document.createElement("span");
        msg.textContent = retryable
          ? `Terrain service temporarily unavailable. ${e.message} Existing profiles are unchanged. Please try again shortly.`
          : `Terrain fetch failed: ${e.message} Check the position and selected source before trying again.`;
        const retry = document.createElement("button");
        retry.className = "ghost small"; retry.type = "button";
        retry.textContent = retryable ? "Retry terrain fetch" : "Try fetch again";
        retry.onclick = () => autoBtn.click();
        notice.append(msg, retry);
        autoBtn.closest(".group").appendChild(notice);
        autoBtn.disabled = false; autoBtn.textContent = "Fetch terrain online";
      }
    };
    box.appendChild(c);
  });
  siteCompare();
}
/* ---------------------------------------------------------------- library shared by all projects */
function libSaveDialog(kind, item) {
  const what = kind === "sites" ? "site" : "tower", url = `/api/v2/p/${SLUG}/${kind}/${item.id}/to-library`;
  modal(`<h2>Save ${what} to the library</h2>
  <p class="small mute">The library is shared by all your projects on this computer. ${kind === "sites" ? "The position and the terrain files are saved." : "Antennas, guys and switching are saved. The location is not: you choose the site when you add it to a project."}
  Later changes here do not change the saved copy.</p>
  <form id="libForm" class="row"><label style="flex:1">Name<input name="name" value="${esc(item.name)}" style="width:100%" required></label>
  <div style="width:100%;display:flex;gap:8px;margin-top:8px"><button type="submit">Save</button><button type="button" class="ghost" id="libCancel">Cancel</button></div>
  <p class="small neg" id="libMsg" style="width:100%"></p></form>`);
  $("#libCancel").onclick = closeModal;
  let replace = false;
  $("#libForm").onsubmit = async e => {
    e.preventDefault(); const name = e.target.name.value.trim();
    try { await api("POST", url, { name, replace }); closeModal(); toast(`Saved to the library as "${name}".`); }
    catch (err) {
      if (err.message !== "exists") return ($("#libMsg").textContent = err.message);
      replace = true; $("#libMsg").textContent = `The library already has a ${what} called "${name}". Press Save again to replace it, or change the name.`;
      e.target.name.oninput = () => { replace = false; $("#libMsg").textContent = ""; };
    }
  };
}
async function libAddDialog(kind) {
  const L = await api("GET", "/api/v2/library"), items = L[kind], what = kind === "sites" ? "site" : "tower";
  const line = x => kind === "sites"
    ? `${x.lat ?? "–"}, ${x.lon ?? "–"} · ${x.n_profiles} profiles${x.terrain?.source ? " · " + esc(x.terrain.source) : ""}`
    : `${(x.antennas || []).map(a => `${a.h} ft ${describe(a)}`).join("; ")}${(x.guys?.levels || []).length ? ` · ${x.guys.levels.length} guy levels` : ""}`;
  modal(`<h2>Add a ${what} from the library</h2>
  <p class="small mute">The ${what} is copied into this project. ${kind === "towers" ? "Set its Location on the tower card afterwards." : ""}</p>
  ${items.length ? `<div class="tbl"><table><tr><th>Name</th><th>Details</th><th>Saved</th><th></th></tr>
    ${items.map(x => `<tr><td><b>${esc(x.name)}</b></td><td class="small">${line(x)}</td><td class="small mute">${esc(x.saved || "")}</td>
      <td style="white-space:nowrap"><button class="small" data-libadd="${x.id}">Add</button> <button class="danger small" data-libdel="${x.id}" title="Remove from the library. Projects that already use it keep their copy">Remove</button></td></tr>`).join("")}</table></div>`
    : `<p class="mute">The library has no ${what}s yet. Use "Save to library" on a ${what} card.</p>`}
  <div style="margin-top:10px"><button class="ghost" id="libClose">Close</button></div>`);
  $("#libClose").onclick = closeModal;
  $$("[data-libadd]").forEach(b => b.onclick = async () => {
    const r = await api("POST", `/api/v2/p/${SLUG}/library/${kind}/${b.dataset.libadd}`); S = r; closeModal();
    toast(`Added "${items.find(x => x.id === b.dataset.libadd).name}".`); render();
  });
  $$("[data-libdel]").forEach(b => b.onclick = async () => {
    if (b.dataset.armed) { await api("DELETE", `/api/v2/library/${kind}/${b.dataset.libdel}`); libAddDialog(kind); return; }
    b.dataset.armed = "1"; b.textContent = "Press again to remove";
  });
}
function moveDialog(s) {
  if (s.lat == null || s.lon == null) { toast("Enter latitude and longitude for this site first.", 4000); return; }
  modal(`<h2>Copy site, moved</h2>
  <p class="small mute">Makes a new site at the given distance and bearing from "${esc(s.name)}", then fetches its terrain online (USGS inside the United States, Terrain Tiles elsewhere).
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
    $("#siteSlopeTbl").innerHTML = `<tr><th>Site</th>${tg.map(t => `<th class="n">${esc(t.name)} ${t.heading}°<br><span class="mute">slope 1 km / horizon / far horizon</span></th>`).join("")}</tr>` +
      sums.map((sm, i) => `<tr><td>${esc(ready[i].name)}</td>${tg.map(t => { const r = near(sm.rows, t.heading), fh = ready[i].terrain?.far_horizon, fv = fh && fh.deg ? fh.deg[Math.round(((t.heading % 360) / fh.step)) % fh.deg.length] : null;
        return `<td class="n">${fmt(r.slope1000, 1)} % / ${fmt(r.horizon_deg, 1)}°${fv != null ? ` <span class="small ${fv >= 1 ? "amb" : "mute"}" title="Far horizon: ground 4.4–15 km out, not in the HFTA profile">far ${fv.toFixed(1)}°</span>` : ""}</td>`; }).join("")}</tr>`).join("");
  }
}

/* ---------------------------------------------------------------- 2. Targets */
/* Region from an ARRL file name: W1-MA-EU.PRN -> Europe. Null for other names. */
const REGION = { AF: "Africa", AS: "Asia", EU: "Europe", JA: "Japan", OC: "Oceania", SA: "South America", US: "USA" };
/* Reference point for each ARRL region: the great-circle bearing is taken from the site to this point.
   The exact points N6BV used are not published in the files; these are central cities of each region. */
const REGION_POINT = {
  AF: { lat: -26.2, lon: 28.0, where: "Johannesburg (southern Africa)" },
  AS: { lat: 13.8, lon: 100.5, where: "Bangkok, between India and China", spread: 16 },   // wide region: judged over ±16°
  EU: { lat: 50.0, lon: 10.0, where: "central Germany" }, JA: { lat: 35.7, lon: 139.7, where: "Tokyo" },
  OC: { lat: -33.9, lon: 151.2, where: "Sydney" }, SA: { lat: -54.8, lon: -68.3, where: "Ushuaia (long axis of South America)" },
  US: { lat: 39.0, lon: -98.0, where: "central USA" } };
function regionCode(file) { const m = /-([A-Z]{2})(?:-VOACAP)?\.PRN$/i.exec(file || ""); return m && REGION_POINT[m[1].toUpperCase()] ? m[1].toUpperCase() : null; }
function bearingTo(la1, lo1, la2, lo2) {
  const r = Math.PI / 180, p1 = la1 * r, p2 = la2 * r, dl = (lo2 - lo1) * r;
  const b = Math.atan2(Math.sin(dl) * Math.cos(p2), Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl)) / r;
  return Math.round((b + 360) % 360);
}
/* Site used for bearings: the first site with a position. Sites on one property are a few km apart at most, which changes no bearing. */
function homeSite() { return P().sites.find(s => s.lat != null && s.lon != null && s.lat !== "" && s.lon !== ""); }
function computedBearing(t) {
  const c = regionCode(t.prn), h = homeSite(); if (!c || !h) return null;
  const q = REGION_POINT[c]; return { deg: bearingTo(Number(h.lat), Number(h.lon), q.lat, q.lon), where: q.where, site: h.name };
}
function regionOf(file) { const m = /-([A-Z]{2})(?:-VOACAP)?\.PRN$/i.exec(file || ""); return m ? REGION[m[1].toUpperCase()] || null : null; }
function offsetsFrom(spread, step) {
  if (!spread || !step) return [0]; const o = []; for (let x = -spread; x <= spread + 1e-9; x += step) o.push(Math.round(x * 100) / 100); return o;
}
/* Add region targets for an existing set of VOACAP files or immediately after batch generation.
   Never overwrite configured targets; matched region/file means do not duplicate it. */
async function addMissingVOACAPTargets(files, origin = null) {
  const p = P(), previousIds = p.targets.map(t => t.id);
  const known = files.map(x => typeof x === "string" ? { file: x } : x);
  let added = 0, already = 0;
  const loc = origin && Number.isFinite(Number(origin.lat)) && Number.isFinite(Number(origin.lon))
    ? origin : homeSite();
  for (const record of known) {
    const filename = record.file || "";
    const code = record.region || regionCode(filename);
    if (!code || !REGION_POINT[code] || !/-VOACAP\.PRN$/i.test(filename)) continue;
    const label = REGION[code];
    const exists = p.targets.some(t =>
      t.prn?.toLowerCase() === filename.toLowerCase() ||
      regionCode(t.prn) === code ||
      String(t.name || "").toLowerCase() === label.toLowerCase()
    );
    if (exists) { already++; continue; }
    let available = record.bands;
    if (!Array.isArray(available)) {
      // Old files from previous sessions have no batch metadata; read the table's band coverage.
      try {
        const detail = await api("GET", `/api/v2/p/${SLUG}/prn/${encodeURIComponent(filename)}`);
        available = Object.entries(detail.coverage || {})
          .filter(([, fraction]) => fraction != null && fraction >= 0.5)
          .map(([band]) => band.endsWith("m") ? band.slice(0, -1) : band);
      } catch (_) { available = ["40", "20", "15", "10"]; }
    }
    const preferred = ["40", "20", "15", "10"];
    const recommended = preferred.filter(b => available.includes(b));
    const bands = recommended.length ? recommended : (available.includes("80") ? ["80"] : preferred);
    const spread = REGION_POINT[code].spread || 8;
    const offsets = offsetsFrom(spread, 8);
    const point = REGION_POINT[code];
    const heading = loc ? bearingTo(Number(loc.lat), Number(loc.lon), point.lat, point.lon) : 0;
    p.targets.push({
      id: uid("t"), name: label, prn: filename, heading,
      offsets, weights: offsets.map(() => 1), bands
    });
    added++;
  }
  if (added) {
    // A tower explicitly serving every previous target should continue serving every target.
    // An intentionally limited tower is left unchanged.
    const newIds = p.targets.slice(previousIds.length).map(t => t.id);
    for (const tower of p.towers) {
      const serves = tower.targets;
      if (Array.isArray(serves) && previousIds.length &&
          previousIds.every(id => serves.includes(id)) &&
          serves.every(id => previousIds.includes(id))) {
        tower.targets = [...serves, ...newIds];
      }
    }
    await save(true);
  }
  return { added, already };
}
function showVOACAPTargetNotice(text) {
  const node = $("#tgAutoNotice");
  if (node) { node.textContent = text; node.hidden = false; }
}

/* Dialog: make a .PRN table with VOACAP for a site of this project (or typed coordinates) and a region. */
function prnGenDialog() {
  const p = P(), sites = p.sites.filter(s => s.lat != null && s.lon != null), home = homeSite() || sites[0];
  const regions = Object.entries(META.regions || {});
  const mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  modal(`<h2>Generate an elevation-angle table with VOACAP</h2>
  <p class="small mute">VOACAP is run for every chosen month, hour and solar level, to several points in the region; every propagation mode counts its
  elevation angle, weighted by its reliability. For the W1 (Boston) origin this agrees with the ARRL files within about 1 dB of FOM on most bands
  (details in Help). Files made here are marked "VOACAP-generated".</p>
  <form id="genForm">
  <div class="row"><label>Origin<select name="site">${sites.map(s => `<option value="${s.id}" ${s === home ? "selected" : ""}>${esc(s.name)} (${s.lat}, ${s.lon})</option>`).join("")}<option value="">typed position…</option></select></label>
    <label>Latitude<input name="lat" type="number" step="0.0001" value="${home ? home.lat : ""}" style="width:110px"></label>
    <label>Longitude<input name="lon" type="number" step="0.0001" value="${home ? home.lon : ""}" style="width:110px"></label></div>
  <fieldset style="border:1px solid var(--line);border-radius:6px;padding:10px;margin:10px 0"><legend><b>Regions: select any or all</b></legend>
    <div class="row">${regions.map(([code, label], i) => `<label style="flex-direction:row;align-items:center;gap:4px"><input type="checkbox" name="region" value="${code}" ${i === 0 ? "checked" : ""}>${esc(label)} (${code})</label>`).join("")}</div>
    <div class="row" style="margin-top:8px"><button type="button" class="ghost small" id="genAll">Select all regions</button><button type="button" class="ghost small" id="genNone">Clear selection</button></div>
  </fieldset>
  <div class="row"><label style="flex-direction:row;align-items:center;gap:4px"><input name="customMode" type="checkbox"> Custom receive points instead of standard regions</label></div>
  <div class="row" id="genCustomFields" hidden><label style="flex:1">Custom points, one "lat, lon" per line<textarea name="points" rows="3" style="width:100%" placeholder="e.g. 51.5, -0.1"></textarea></label>
    <label>Custom file name<input name="name" style="width:220px"></label></div>
  <div class="row" id="genPrefixFields"><label>Output file prefix<input name="prefix" style="width:220px"></label><span class="small mute">Each region gets its own file, e.g. My-station-EU-VOACAP.PRN.</span></div>
  <div class="row"><span class="small mute" style="align-self:center">Months:</span>${mon.map((m, i) => `<label style="flex-direction:row;align-items:center;gap:3px"><input type="checkbox" name="m" value="${i + 1}" checked>${m}</label>`).join("")}</div>
  <div class="row"><label>Hours (UTC)<select name="hours"><option value="">all 24 hours</option><option value="0-12">00–12 (evening and night in the Americas)</option><option value="12-24">12–24</option><option value="custom">from–to below</option></select></label>
    <label>From<input name="h1" type="number" min="0" max="23" value="0" style="width:70px"></label><label>To<input name="h2" type="number" min="1" max="24" value="24" style="width:70px"></label></div>
  <div class="row"><span class="small mute" style="align-self:center">Solar activity (sunspot number):</span>${(META.ssn_levels || []).map(([k, v]) => `<label style="flex-direction:row;align-items:center;gap:3px"><input type="checkbox" name="ssn" value="${v}" checked>${k} (${v})</label>`).join("")}</div>
  <p class="small mute">All months, all hours and all three solar levels give tables like the ARRL files. Fewer months or hours give a table for that season or time of day; one solar level gives a table for that part of the cycle. Each checked region produces a separate file; a batch of all regions may take several minutes. Progress and Cancel appear in the Targets page.</p>
  <div class="row"><button type="submit">Generate</button><button type="button" class="ghost" id="genCancel">Cancel</button></div></form>`);
  const f = $("#genForm");
  const regionChecks = () => [...f.querySelectorAll('[name=region]')];
  const checkedRegions = () => regionChecks().filter(x => x.checked).map(x => x.value);
  const customMode = f.querySelector('[name=customMode]');
  const setDefaults = () => {
    const site = sites.find(x => x.id === f.site.value);
    const prefix = (site ? site.name : "origin").replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || "origin";
    f.prefix.value = prefix;
    f.name.value = `${prefix}-custom-VOACAP.PRN`;
  };
  f.site.onchange = () => { const site = sites.find(x => x.id === f.site.value); if (site) { f.lat.value = site.lat; f.lon.value = site.lon; } setDefaults(); };
  const updateMode = () => {
    const custom = customMode.checked;
    $("#genCustomFields").hidden = !custom;
    $("#genPrefixFields").hidden = custom;
    regionChecks().forEach(x => { x.disabled = custom; });
  };
  customMode.onchange = updateMode;
  $("#genAll").onclick = () => { customMode.checked = false; updateMode(); regionChecks().forEach(x => { x.checked = true; }); };
  $("#genNone").onclick = () => { customMode.checked = false; updateMode(); regionChecks().forEach(x => { x.checked = false; }); };
  setDefaults(); updateMode();
  $("#genCancel").onclick = closeModal;
  f.onsubmit = async e => {
    e.preventDefault();
    const body = { lat: Number(f.lat.value), lon: Number(f.lon.value),
      origin_name: (sites.find(x => x.id === f.site.value) || {}).name || "",
      months: [...f.querySelectorAll("[name=m]:checked")].map(x => Number(x.value)),
      ssn: [...f.querySelectorAll("[name=ssn]:checked")].map(x => Number(x.value)) };
    if (customMode.checked) {
      body.region = "custom";
      body.name = f.name.value.trim();
      body.points = f.points.value.split("\n").map(l => l.split(",").map(Number)).filter(a => a.length === 2 && a.every(Number.isFinite));
      if (!body.points.length) return toast("Enter at least one valid custom receive point, as latitude, longitude.", 5000);
    } else {
      body.regions = checkedRegions();
      body.prefix = f.prefix.value.trim();
      if (!body.regions.length) return toast("Select at least one region.", 5000);
    }
    const hv = f.hours.value; if (hv === "custom") { const a = Number(f.h1.value), b = Number(f.h2.value); body.hours = [...Array(24).keys()].filter(h => a <= b ? (h >= a && h < b) : (h >= a || h < b)); }
    else if (hv) { const [a, b] = hv.split("-").map(Number); body.hours = [...Array(24).keys()].filter(h => h >= a && h < b); }
    if (!body.months.length || !body.ssn.length) return toast("Choose at least one month and one solar level");
    if (customMode.checked && !/\.prn$/i.test(body.name)) body.name += ".PRN";
    closeModal();
    try {
      const { job } = await api("POST", `/api/v2/p/${SLUG}/prn/generate`, body); const r = await poll(job, $("#genProg"));
      if (!r) return;
      S = await api("GET", `/api/v2/p/${SLUG}`);
      if (r.files) {
        const summary = await addMissingVOACAPTargets(r.files, { lat: body.lat, lon: body.lon });
        rTargets();
        showVOACAPTargetNotice(`Generated ${r.files.length} VOACAP tables and created ${summary.added} matching targets (${summary.already} already configured). You can now evaluate the tower without adding targets manually.`);
        toast(`Generated ${r.files.length} tables; ${summary.added} targets added.`, 8000);
      } else {
        rTargets();
        toast(`${r.file} made (${r.describe})${r.empty_bands.length ? `. No openings found on ${r.empty_bands.join("/")} m` : ""}. Choose it in a target\'s file list.`, 8000);
      }
    } catch (err) { toast(err.message, 6000); }
  };
}
function rTargets() {
  const p = P(), el = $("#p-targets");

  el.innerHTML = `<h1>Targets</h1><p class="lead">A target is a path you want to work, for example Europe at 52°. Each target uses one elevation-angle file (.PRN: an ARRL file,
  or one generated with VOACAP) and one or more headings around its bearing. The result is the weighted mean of the FOM at those headings, exactly as you would average several HFTA runs.</p>
  <div class="card"><h2>Elevation-angle files (.PRN)</h2>
    <p class="small mute">The ARRL files come with the ARRL Antenna Book (e.g. W1-MA-EU.PRN). They are not included in the program; add your own copies once and save them to the library.</p>
    <div class="row"><button id="prnBtn">Add .PRN files</button><input type="file" id="prnIn" multiple accept=".prn,.PRN" hidden>
      <button class="ghost" id="prnToLib" title="Keep a copy of these files in your library. Every new project then starts with them" ${S.prns.length ? "" : "disabled"}>Save to library</button>
      <button class="ghost" id="prnFromLib" title="Add the library's .PRN files to this project">Add from library</button>
      ${META.voacap ? `<button class="ghost" id="prnGen" title="Make an elevation-angle table with VOACAP for any origin in the world: the method of the ARRL files, with your own choice of months, hours and solar activity">Generate with VOACAP…</button>` : ""}</div>
    <p class="small mute" id="prnLibInfo" style="margin:6px 0 0"></p>
    ${META.voacap ? `<p class="small mute" style="margin:6px 0 0">No ARRL files? <b>Generate with VOACAP</b> makes a table for your own position and any region (checked against the ARRL W1 files; see Help). Such files are marked "VOACAP-generated".</p>` : ""}
    <div class="prog" id="genProg" hidden><i></i></div>
    <div class="split" style="margin-top:10px"><div class="tbl"><table><tr><th>File</th><th></th></tr>
      ${S.prns.map(f => `<tr><td>${esc(f)}</td><td><button class="ghost small" data-prv="${esc(f)}">View</button></td></tr>`).join("") || `<tr><td class="mute">No files yet.</td><td></td></tr>`}</table></div>
      <div><div id="prnPlot" class="plot sm"></div></div></div></div>
  <div class="card"><h2>Targets</h2><div class="tbl"><table id="tgTbl"></table></div>
    <div class="row" style="margin-top:10px"><button id="addTg">Add target</button>
      <button class="ghost" id="tgVoacapFill" title="Create missing regional targets from VOACAP tables already generated in this project">Add missing targets from VOACAP files</button>
      <button class="ghost" id="tgBrg" title="Set every target's bearing from the site position to the reference point of its ARRL region">Bearings from site position</button></div>
    <p class="small mute" style="margin:6px 0 0">${homeSite() ? `Bearings are computed from <b>${esc(homeSite().name)}</b> (${homeSite().lat}, ${homeSite().lon}) to a reference point in each region (shown under the bearing).
      Choosing a .PRN file sets the bearing; you can still type your own.` : "Enter a latitude and longitude on the Sites page and the bearings can be computed for you."}</p>
    <div class="note" role="status" id="tgAutoNotice" hidden></div>
    <p class="small mute">Headings: the bearing ± spread in steps (e.g. ±8° in 8° steps gives three headings). Weights are equal unless you type them, e.g. "1, 2, 1".
    Weights from contest logs are not part of this release.</p></div>
  <div class="card"><h2>Map of targets <span class="chip">great-circle map centred on your site</span></h2><div id="azMap"></div></div>`;
  $("#tgVoacapFill").onclick = async () => {
    try {
      await flushSave();
      S = await api("GET", `/api/v2/p/${SLUG}`);
      const candidates = S.prns.filter(file => regionCode(file) && /-VOACAP\.PRN$/i.test(file));
      const summary = await addMissingVOACAPTargets(candidates);
      rTargets();
      showVOACAPTargetNotice(candidates.length
        ? `Found ${candidates.length} VOACAP regional files; created ${summary.added} missing targets, ${summary.already} already existed.`
        : "No standard VOACAP regional files found. Generate tables first.");
    } catch (error) { showVOACAPTargetNotice("Could not add targets: " + error.message); }
  };
  $("#prnBtn").onclick = () => $("#prnIn").click();
  api("GET", "/api/v2/library").then(L => {
    const el = $("#prnLibInfo"); if (!el) return;
    el.innerHTML = L.prns.length ? `Library: ${L.prns.length} files (${L.prns.map(esc).join(", ")}). They are copied into every new project.`
      : `Your library has no .PRN files yet. "Save to library" keeps these files for every new project. They stay on this computer and are not part of the program.`;
  });
  if ($("#prnGen")) $("#prnGen").onclick = () => prnGenDialog();
  $("#prnToLib").onclick = async () => { const r = await api("POST", `/api/v2/p/${SLUG}/prn/to-library`); toast(`${r.saved.length} files saved to the library. New projects will start with them.`, 5000); rTargets(); };
  $("#prnFromLib").onclick = async () => { const r = await api("POST", `/api/v2/p/${SLUG}/library/prn`); const proj = P(); proj.rev = r.project.rev; S = r; S.project = proj;
    toast(r.added.length ? `${r.added.length} files added from the library.` : "Nothing to add: the project already has every library file.", 4000); rTargets(); };
  $("#prnIn").onchange = async () => { const fd = new FormData(); [...$("#prnIn").files].forEach(x => fd.append("files", x));
    const r = await api("POST", `/api/v2/p/${SLUG}/prn`, fd, true); const bad = r.filter(x => x.error); toast(`${r.length - bad.length} added${bad.length ? `, ${bad.length} rejected: ${bad[0].error}` : ""}`, 4000);
    S = await api("GET", `/api/v2/p/${SLUG}`); rTargets(); };
  $$("[data-prv]").forEach(b => b.onclick = async () => {
    const d = await api("GET", `/api/v2/p/${SLUG}/prn/${encodeURIComponent(b.dataset.prv)}`);
    const tr = d.columns.slice(1).map((c, j) => ({ x: d.rows.map(r => r[0]), y: d.rows.map(r => r[j + 1]), name: c, mode: "lines", line: { color: PAL[j % 8] } }));
    /* Title: region from the ARRL file name (W1-MA-EU.PRN -> Europe). Files that do not follow that pattern show their own first line. */
    const region = regionOf(b.dataset.prv);
    /* HFTA computes 1° to 35°: weight above that line is not counted in any FOM. Bands with much of their weight above it are named. */
    const low = Object.entries(d.coverage || {}).filter(([, v]) => v != null && v < 0.9).map(([c, v]) => `${c} ${Math.round(100 * v)}%`);
    const sub = low.length ? ` · inside HFTA's range: ${low.join(", ")}` : "";
    Plotly.react("prnPlot", tr, plotLayout({ title: { text: (region ? `${region} (${esc(b.dataset.prv)})` : esc(d.title)) + sub, font: { size: 13 } },
      margin: { l: 50, r: 16, t: 28, b: 80 }, legend: { orientation: "h", y: -0.4 },
      shapes: [{ type: "line", x0: d.max_angle, x1: d.max_angle, y0: 0, y1: 1, yref: "paper", line: { color: css("--warn"), width: 1, dash: "dot" } }],
      annotations: [{ x: d.max_angle, y: 1, yref: "paper", text: "HFTA range ends 35°", showarrow: false, xanchor: "left", yanchor: "top", font: { size: 11, color: css("--warn") } }],
      xaxis: { title: { text: "Elevation angle (°)", standoff: 6 }, gridcolor: css("--line") }, yaxis: { title: "% of openings", gridcolor: css("--line") } }), { displaylogo: false, responsive: true });
  });
  const tb = $("#tgTbl");
  tb.innerHTML = `<tr><th>Name</th><th>.PRN file</th><th class="n">Bearing (°)</th><th class="n">± spread (°)</th><th class="n">Step (°)</th><th>Weights</th><th>Bands</th><th></th></tr>`;
  p.targets.forEach((t, i) => {
    const tr = document.createElement("tr");
    const spread = t.offsets.length > 1 ? Math.max(...t.offsets) : 0, step = t.offsets.length > 1 ? Math.abs(t.offsets[1] - t.offsets[0]) : 0;
    tr.innerHTML = `<td><input class="w" data-k="name" value="${esc(t.name)}"></td>
      <td><select data-k="prn">${["", ...S.prns].map(f => `<option ${f === t.prn ? "selected" : ""}>${esc(f)}</option>`).join("")}</select></td>
      <td class="n"><input type="number" data-k="heading" value="${t.heading}" min="0" max="359">${(() => { const c = computedBearing(t); return c ? `<br><span class="small ${c.deg === Number(t.heading) ? "mute" : "amb"}" title="Great-circle bearing from ${esc(c.site)} to ${esc(c.where)}">${c.deg === Number(t.heading) ? "to " + esc(c.where) : `computed ${c.deg}° (${esc(c.where)})`}</span>` : ""; })()}</td>
      <td class="n"><input type="number" class="s" data-sp value="${spread}" min="0"></td><td class="n"><input type="number" class="s" data-st value="${step}" min="0"></td>
      <td><input class="s" style="width:110px" data-w value="${t.weights.every(w => w === t.weights[0]) ? "" : t.weights.join(", ")}" placeholder="equal"></td>
      <td><div class="bandbox">${META.bands.filter(b => b !== "6").map(b => `<label><input type="checkbox" data-b="${b}" ${t.bands.includes(b) ? "checked" : ""}>${b}</label>`).join("")}</div></td>
      <td><button class="danger small" data-del>Delete</button></td>`;
    let prevPrn = t.prn;   // a name the planner gave from the file name follows the file when the file changes
    $$("[data-k]", tr).forEach(inp => bind(inp, t, inp.dataset.k, inp.dataset.k === "prn" ? () => {
      const r = regionOf(t.prn); if (r && (t.name === "New target" || !t.name || t.name === regionOf(prevPrn))) t.name = r;
      prevPrn = t.prn;
      const c = computedBearing(t); if (c) t.heading = c.deg;
      const sp = REGION_POINT[regionCode(t.prn)]?.spread; if (sp) { t.offsets = offsetsFrom(sp, 8); t.weights = t.offsets.map(() => 1); }
      save(); rTargets();
    } : null, inp.type === "number"));
    const reoff = () => { t.offsets = offsetsFrom(Number($("[data-sp]", tr).value), Number($("[data-st]", tr).value)); rew(); save(); };
    const rew = () => { const v = $("[data-w]", tr).value.trim(); const w = v ? v.split(/[ ,;]+/).map(Number) : [];
      t.weights = w.length === t.offsets.length ? w : t.offsets.map(() => 1); };
    $("[data-sp]", tr).onchange = reoff; $("[data-st]", tr).onchange = reoff; $("[data-w]", tr).onchange = () => { rew(); save(); };
    $$("[data-b]", tr).forEach(cb => cb.onchange = () => { t.bands = META.bands.filter(b => $(`[data-b="${b}"]`, tr)?.checked); save(); });
    $("[data-del]", tr).onclick = () => { p.targets.splice(i, 1); save(true).then(rTargets); };
    tb.appendChild(tr);
  });
  const first = $("[data-prv]"); if (first) first.click();
  azMap();
  $("#tgBrg").onclick = () => {
    const ch = [];
    p.targets.forEach(t => {
      /* A target still carrying the region name of another file (named before its file was chosen) takes its own file's region. */
      const r = regionOf(t.prn); if (r && t.name !== r && Object.values(REGION).includes(t.name)) { ch.push(`${t.name} → ${r}`); t.name = r; }
      const c = computedBearing(t); if (c && c.deg !== Number(t.heading)) { ch.push(`${t.name} ${t.heading}° → ${c.deg}°`); t.heading = c.deg; }
      const sp = REGION_POINT[regionCode(t.prn)]?.spread, cur = Math.max(...(t.offsets || [0]).map(Math.abs));
      if (sp && cur < sp) { t.offsets = offsetsFrom(sp, 8); t.weights = t.offsets.map(() => 1); ch.push(`${t.name} spread ±${cur}° → ±${sp}°`); }
    });
    if (!homeSite()) return toast("Enter the site's latitude and longitude first (Sites page).", 5000);
    save(); rTargets(); toast(ch.length ? `Bearings changed: ${ch.join("; ")}. Run Evaluate again.` : "All bearings already match.", 8000);
  };
  $("#addTg").onclick = () => {
    /* Default bands: 40 to 10 m, the range HFTA is validated for; 80 m can be ticked. */
    const id = uid("t"), nt = { id, name: "New target", prn: S.prns[0] || "", heading: 0, offsets: [-8, 0, 8], weights: [1, 1, 1], bands: ["40", "20", "15", "10"] };
    nt.name = regionOf(nt.prn) || nt.name; nt.heading = computedBearing(nt)?.deg ?? 0;
    const sp = REGION_POINT[regionCode(nt.prn)]?.spread; if (sp) { nt.offsets = offsetsFrom(sp, 8); nt.weights = nt.offsets.map(() => 1); }
    p.targets.push(nt);
    /* A new target is served by every tower and counts in the compromise search until the user unticks it. */
    p.towers.forEach(t => { if (Array.isArray(t.targets) && !t.targets.includes(id)) t.targets.push(id); });
    if (p.settings.compromise) p.settings.compromise.weights[id] = 1;
    save(true).then(rTargets);
  };
}

/* ---------------------------------------------------------------- great-circle map (azimuthal equidistant) */
/* Centred on the first site with a position. Straight lines from the centre are great circles: the bearing on the map is the
   true bearing, and the distance from the centre is the true distance. The outer circle is the antipode (20,015 km). */
let AZ = { sel: null };
function azMap() {
  const box = $("#azMap"); if (!box) return;
  const h = homeSite(), p = P();
  if (!h) { box.innerHTML = `<p class="mute">Enter a latitude and longitude on the Sites page to see the map.</p>`; return; }
  if (!p.targets.some(t => t.id === AZ.sel)) AZ.sel = p.targets[0]?.id || null;
  const R = 250, C = R + 34, S = 2 * C, d2r = Math.PI / 180, la0 = Number(h.lat) * d2r, lo0 = Number(h.lon) * d2r;
  const proj = (lat, lon) => {                                    // -> [x, y] in px, plus angular distance c
    const la = lat * d2r, dl = lon * d2r - lo0;
    const cc = Math.sin(la0) * Math.sin(la) + Math.cos(la0) * Math.cos(la) * Math.cos(dl), c = Math.acos(Math.max(-1, Math.min(1, cc)));
    const k = c < 1e-9 ? 1 : c / Math.sin(c);
    const x = k * Math.cos(la) * Math.sin(dl), y = k * (Math.cos(la0) * Math.sin(la) - Math.sin(la0) * Math.cos(la) * Math.cos(dl));
    return [C + R * x / Math.PI, C - R * y / Math.PI, c];
  };
  const polar = (brg, r) => [C + r * Math.sin(brg * d2r), C - r * Math.cos(brg * d2r)];
  // land: filled where the ring stays clear of the antipode; outline only (broken at jumps) where it wraps round the edge
  let fill = "", line = "";
  for (const ring of LAND110) {
    const pts = []; for (let i = 0; i < ring.length; i += 2) pts.push(proj(ring[i + 1], ring[i]));
    const jumps = pts.some((q, i) => i && Math.hypot(q[0] - pts[i - 1][0], q[1] - pts[i - 1][1]) > R * 0.25);
    if (!jumps) fill += "M" + pts.map(q => q[0].toFixed(1) + "," + q[1].toFixed(1)).join("L") + "Z";
    else pts.forEach((q, i) => { line += (i && Math.hypot(q[0] - pts[i - 1][0], q[1] - pts[i - 1][1]) <= R * 0.25 ? "L" : "M") + q[0].toFixed(1) + "," + q[1].toFixed(1); });
  }
  let svg = `<svg viewBox="0 0 ${S} ${S}" class="azmap" role="img" aria-label="Great-circle map centred on ${esc(h.name)}">
    <defs><clipPath id="azClip"><circle cx="${C}" cy="${C}" r="${R}"/></clipPath></defs>
    <circle cx="${C}" cy="${C}" r="${R}" fill="var(--soft)" stroke="${css("--line")}"/>
    <g clip-path="url(#azClip)"><path d="${fill}" fill="${css("--ink")}" fill-opacity="0.22" stroke="${css("--mute")}" stroke-width="0.4"/>
      <path d="${line}" fill="none" stroke="${css("--mute")}" stroke-width="0.6"/>`;
  for (const km of [5000, 10000, 15000]) svg += `<circle cx="${C}" cy="${C}" r="${R * km / 20015}" fill="none" stroke="${css("--mute")}" stroke-width="0.4" stroke-dasharray="2 3"/>
    <text x="${C + 3}" y="${C - R * km / 20015 - 2}" font-size="9" fill="${css("--mute")}">${km / 1000}k km</text>`;
  // target wedges: bearing ± spread, out to the edge (own group, so a drag redraws only this)
  const wedges = () => { let w = ""; p.targets.forEach((t, i) => {
    const sp = Math.max(0, ...(t.offsets || [0]).map(Math.abs)), b = Number(t.heading) || 0, col = PAL[i % 8], on = t.id === AZ.sel;
    const [x1, y1] = polar(b - sp, R), [x2, y2] = polar(b + sp, R);
    if (sp > 0) w += `<path d="M${C},${C}L${x1},${y1}A${R},${R} 0 ${2 * sp > 180 ? 1 : 0} 1 ${x2},${y2}Z" fill="${col}" fill-opacity="${on ? 0.32 : 0.14}" stroke="${col}" stroke-width="${on ? 1.5 : 0.6}"/>`;
    const [xe, ye] = polar(b, R);
    w += `<line x1="${C}" y1="${C}" x2="${xe}" y2="${ye}" stroke="${col}" stroke-width="${on ? 2.5 : 1.2}"/>`;
    const [xl, yl] = polar(b, R + 14);
    w += `<text x="${xl}" y="${yl + 4}" font-size="11" font-weight="${on ? 700 : 400}" text-anchor="middle" fill="${col}">${esc(t.name)}</text>`;
  }); return w; };
  // reference points of the ARRL regions
  for (const [code, q] of Object.entries(REGION_POINT)) {
    const [x, y, c] = proj(q.lat, q.lon); if (c > Math.PI * 0.995) continue;
    svg += `<circle cx="${x}" cy="${y}" r="2.5" fill="${css("--ink")}"><title>${code}: ${esc(q.where)}</title></circle>`;
  }
  svg += `</g><g id="azDyn">${wedges()}</g>`;
  for (let a = 0; a < 360; a += 10) { const [xa, ya] = polar(a, R), [xb, yb] = polar(a, R - (a % 30 ? 4 : 9)); svg += `<line x1="${xa}" y1="${ya}" x2="${xb}" y2="${yb}" stroke="${css("--ink")}" stroke-width="0.7"/>`; }
  for (let a = 0; a < 360; a += 30) { const [xt, yt] = polar(a, R + 26); svg += `<text x="${xt}" y="${yt + 3}" font-size="9" text-anchor="middle" fill="${css("--mute")}">${a}°</text>`; }
  svg += `<circle cx="${C}" cy="${C}" r="3" fill="${css("--ink")}"/></svg>`;
  const t = p.targets.find(x => x.id === AZ.sel), sp = t ? Math.max(0, ...(t.offsets || [0]).map(Math.abs)) : 0;
  const step = t && t.offsets?.length > 1 ? Math.abs(t.offsets[1] - t.offsets[0]) : 8;
  box.innerHTML = `<div class="split"><div style="flex:none;width:min(100%,${S}px)">${svg}<div class="small mute" id="azRead" style="min-height:1.2em">Centre: ${esc(h.name)}. Move the pointer over the map for bearing and distance.</div></div>
    <div><p class="small" style="margin-top:0">Choose a target, then click the map (or hold and drag) to set its bearing. Use the slider for the spread.</p>
      <div class="tgtabs">${p.targets.map((x, i) => `<button class="${x.id === AZ.sel ? "" : "ghost"}" data-azsel="${x.id}" style="${x.id === AZ.sel ? `background:${PAL[i % 8]};border-color:${PAL[i % 8]}` : `color:${PAL[i % 8]}`}">${esc(x.name)}</button>`).join("")}</div>
      ${t ? `<div class="row" style="margin-top:8px"><label>Bearing (°)<input type="number" id="azBrg" min="0" max="359" value="${t.heading}"></label>
        <label style="min-width:220px">Spread ± <b id="azSpV">${sp}</b>°<input type="range" id="azSp" min="0" max="60" step="${step || 8}" value="${sp}" style="width:100%"></label>
        <label>Step (°)<input type="number" id="azSt" min="1" max="30" value="${step || 8}"></label></div>
        <p class="small mute">Headings judged: ${(t.offsets || [0]).map(o => ((Number(t.heading) + o + 360) % 360)).join("°, ")}°.
        ${computedBearing(t) ? `Reference point of ${esc(regionOf(t.prn) || "")}: ${esc(computedBearing(t).where)}, ${computedBearing(t).deg}°.` : ""}</p>` : `<p class="mute">No targets yet.</p>`}
      <p class="small mute">Lines from the centre are great circles (short path). The ring marks are 5,000, 10,000 and 15,000 km; the outer circle is the far side of the Earth. Dots: ARRL region reference points.
      Changes here are the same as editing the table above; run Evaluate again afterwards.</p></div></div>`;
  $$("[data-azsel]", box).forEach(b => b.onclick = () => { AZ.sel = b.dataset.azsel; azMap(); });
  if (!t) return;
  const svgEl = $("svg.azmap", box), toMap = e => { const r = svgEl.getBoundingClientRect(); return [(e.clientX - r.left) * S / r.width, (e.clientY - r.top) * S / r.height]; };
  const brgAt = (x, y) => Math.round((Math.atan2(x - C, C - y) / d2r + 360) % 360), kmAt = (x, y) => Math.hypot(x - C, y - C) / R * 20015;
  const setBrg = b => { t.heading = b; save(); rTargets(); };
  let drag = false;
  svgEl.onpointerdown = e => { const [x, y] = toMap(e); if (Math.hypot(x - C, y - C) > R + 20) return; drag = true; svgEl.setPointerCapture(e.pointerId);
    t.heading = brgAt(x, y); $("#azDyn").innerHTML = wedges(); $("#azBrg").value = t.heading; };
  svgEl.onpointermove = e => {
    const [x, y] = toMap(e), km = kmAt(x, y);
    const rd = $("#azRead"); if (rd && km <= 20015) rd.textContent = `Bearing ${brgAt(x, y)}°, ${Math.round(km).toLocaleString()} km (${Math.round(km / 1.609).toLocaleString()} miles)`;
    if (drag) { t.heading = brgAt(x, y); $("#azDyn").innerHTML = wedges(); $("#azBrg").value = t.heading; }
  };
  svgEl.onpointerup = () => { if (drag) { drag = false; save(); rTargets(); } };
  $("#azBrg").onchange = e => setBrg(((Number(e.target.value) % 360) + 360) % 360);
  const reoff = (spv, stv) => { t.offsets = offsetsFrom(spv, stv); t.weights = t.offsets.map(() => 1); };
  $("#azSp").oninput = e => { $("#azSpV").textContent = e.target.value; };
  $("#azSp").onchange = e => { reoff(Number(e.target.value), Number($("#azSt").value) || 8); save(); rTargets(); };
  $("#azSt").onchange = e => { reoff(Number($("#azSp").value), Number(e.target.value) || 8); save(); rTargets(); };
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
function towerBands(extra = [], withSix = false) {
  /* The HF bands the ARRL elevation-angle files cover (80 to 10 m), plus 160/6 m if any antenna already uses them.
     Tower cards always show 6 m, so the whole tower can be laid out; 6 m is never scored (HFTA stops at 30 MHz). */
  const used = new Set(extra.flatMap(a => bandsOf(a)));
  return META.bands.filter(b => (b !== "160" && b !== "6") || used.has(b) || (withSix && b === "6"));
}
const SIX_NOTE = "6 m: position only. HFTA stops at 30 MHz, so a 6 m antenna is drawn on the tower, included in the spacing and guy checks, and never given a FOM.";
/* Common band sets for one antenna on one boom. Choosing one fills the element boxes of that row; adjust counts after. */
const BANDSETS = [
  ["", "Band set…"], ["6", "Monobander 6 m (position only)"], ["40", "Monobander 40 m"], ["20", "Monobander 20 m"], ["15", "Monobander 15 m"], ["10", "Monobander 10 m"],
  ["20,15,10", "Tribander 20/15/10"], ["20,17,15,12,10", "5-band 20/17/15/12/10"], ["17,12", "Duobander 17/12"],
  ["40,30", "Duobander 40/30"], ["30,17,12", "WARC 30/17/12"], ["40,20,15,10", "4-band 40/20/15/10"]];
const bandSetSelect = attr => `<select class="s" ${attr} title="Fill this row's bands for a common antenna. One row = one antenna at one height">${BANDSETS.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select>`;
function applyBandSet(el, value) {
  if (!value) return el;
  const keep = Object.values(el || {})[0] || 4, out = {};
  for (const b of value.split(",")) out[b] = (el || {})[b] || keep;
  return out;
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
  A study can contain just one tower with one antenna; you do not need to create alternatives to evaluate it.
  HFTA treats the antennas as facing the azimuth of the terrain file. Tick the targets each tower serves: that choice sets the directions it is evaluated in.
  Location: pick the site (from the Sites page) where this tower stands, or leave "Every site" to try the tower at all sites and compare them.</p>
  <div id="spcCard"></div><div id="towerCards"></div><div class="row"><button id="addTw">Add tower</button><button class="ghost" id="libTw" title="Add a tower saved from another project">Add from library…</button></div><div id="compCard"></div><div id="scanCard"></div>`;
  const box = $("#towerCards");
  spacingCard();
  p.towers.forEach((t, i) => {
    t.guys = t.guys || { levels: [], ice_in: 1.0, margin_ft: 2.0 };
    const c = document.createElement("div"); c.className = "card"; const tb = towerBands(t.antennas, true);
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
      <div class="tbl" style="margin-top:8px"><table><tr><th class="n">Height (ft)</th><th></th>${tb.map(b => b === "6" ? `<th title="${SIX_NOTE}">6 m <span class="chip warn" style="font-size:10px;padding:0 5px">no FOM</span></th>` : `<th>${b} m</th>`).join("")}<th class="n" title="Turning radius of the antenna, in feet. Only for the guy check">Radius (ft)</th><th class="n" title="Element tip droop under ice, in feet. Only for the guy check">Droop (ft)</th><th></th></tr>
        ${t.antennas.map((a, j) => `<tr><td class="n"><input type="number" data-ah="${j}" value="${a.h}"></td><td>${bandSetSelect(`data-aset="${j}"`)}</td>
          ${tb.map(b => `<td>${elSelect(`data-ae="${j}" data-band="${b}"`, b, elOf(a)[b])}</td>`).join("")}
          <td class="n"><input type="number" class="s" step="0.5" data-atr="${j}" value="${a.turning_radius ?? ""}" placeholder="–"></td>
          <td class="n"><input type="number" class="s" step="0.5" data-adr="${j}" value="${a.droop ?? ""}" placeholder="–"></td>
          <td><button class="danger small" data-ad="${j}">Remove</button></td></tr>`).join("")}</table></div>
      ${t.design ? `<p class="small" style="margin:4px 0"><b>Made by the Stack Designer:</b> ${esc(t.design)}</p>` : ""}
      <p class="small mute" style="margin:4px 0 0">One row = one antenna at one height. Elements on several bands in one row = a tribander or multiband antenna; "Band set…" fills common ones. Choose the number of elements on each band, as in HFTA (Dipole, 2–6 or 8 elements). Turning radius and droop are used only by the guy check.
      ${t.antennas.some(a => bandsOf(a).includes("6")) ? `<br><b>6 m:</b> ${SIX_NOTE}` : ""}</p>
      ${warnList(spacingCheck(t.antennas))}
      <div class="row" style="margin-top:8px"><button class="ghost" data-add>Add antenna</button>${t.antennas.length ? `<button class="ghost" data-addsame>Add same as top</button>` : ""}
        <button class="ghost" data-copy title="Make a copy of this tower (same antennas, guys and targets) at another site">Copy to…</button>
        <button class="ghost" data-tlib title="Save this tower (antennas, guys, switching) to the library shared by all your projects">Save to library</button>
        <button class="danger" data-del>Delete tower</button></div>
      ${guyBlock(t)}</div></div>`;
    $$("[data-k]", c).forEach(inp => bind(inp, t, inp.dataset.k, () => rTowers(), inp.type === "number"));
    $$("[data-tg]", c).forEach(cb => cb.onchange = () => { t.targets = $$("[data-tg]", c).filter(x => x.checked).map(x => x.dataset.tg); save(); });
    $$("[data-aset]", c).forEach(s => s.onchange = () => { const a = t.antennas[s.dataset.aset]; a.el = applyBandSet(elOf(a), s.value); save(); rTowers(); });
    $$("[data-ae]", c).forEach(s => s.onchange = () => { const a = t.antennas[s.dataset.ae]; a.el = a.el || {}; if (s.value) a.el[s.dataset.band] = Number(s.value); else delete a.el[s.dataset.band]; save(); rTowers(); });
    $$("[data-atr]", c).forEach(s => s.onchange = () => { t.antennas[s.dataset.atr].turning_radius = s.value === "" ? null : Number(s.value); save(); });
    $$("[data-adr]", c).forEach(s => s.onchange = () => { t.antennas[s.dataset.adr].droop = s.value === "" ? null : Number(s.value); save(); });
    $$("[data-ah]", c).forEach(s => s.onchange = () => { t.antennas[s.dataset.ah].h = Number(s.value); save(); rTowers(); });
    $$("[data-ad]", c).forEach(b => b.onclick = () => { t.antennas.splice(Number(b.dataset.ad), 1); save(); rTowers(); });
    /* A new row is empty: height above the top one, no bands, no radius. "Band set…" or the element boxes fill it.
       "Add same" repeats the top antenna, for a stack. */
    $("[data-add]", c).onclick = () => { const last = t.antennas[t.antennas.length - 1]; t.antennas.push({ h: last ? last.h + 30 : 60, el: {}, turning_radius: null, droop: null }); save(); rTowers(); };
    const same = $("[data-addsame]", c); if (same) same.onclick = () => { const last = t.antennas[t.antennas.length - 1]; t.antennas.push({ h: last.h + 30, el: { ...last.el }, turning_radius: last.turning_radius ?? null, droop: last.droop ?? null }); save(); rTowers(); };
    $("[data-del]", c).onclick = () => { p.towers.splice(i, 1); save(true).then(rTowers); };
    $("[data-copy]", c).onclick = () => copyTowerDialog(t, i);
    $("[data-tlib]", c).onclick = () => libSaveDialog("towers", t);
    wireGuys(c, t);
    box.appendChild(c);
  });
  compCard();
  $("#libTw").onclick = () => libAddDialog("towers");
  $("#addTw").onclick = () => { p.towers.push({ id: uid("w"), name: `Tower ${p.towers.length + 1}`, switching: "stackmatch", height_ft: 100, antennas: [{ h: 60, el: { "20": 4, "15": 4, "10": 4 }, turning_radius: null, droop: null }], guys: { levels: [], ice_in: 1.0, margin_ft: 2.0 } }); save(true).then(rTowers); };
  scanCard();
}
function spacingCard() {
  const r = P().settings.spacing = { ...META.spacing_defaults, ...(P().settings.spacing || {}) };
  $("#spcCard").innerHTML = `<div class="card aux"><h2>Spacing warnings <span class="chip">not part of HFTA</span></h2>
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
  return `<div class="card aux"><h2>Guy and ice check <span class="chip">not part of HFTA</span></h2>
    <p class="small mute">For antennas that turn: each sweeps a circle of its turning radius. Guys sag under ice; elements droop. Negative clearance = contact. Leave empty if not needed.</p>
    <div class="tbl"><table><tr><th class="n">Guy height (ft)</th><th class="n">Anchor radius (ft)</th><th>Guy line</th><th class="n">Initial tension (lb)</th><th></th></tr>
    ${g.levels.map((l, j) => `<tr><td class="n"><input type="number" data-gh="${j}" value="${l.h}"></td><td class="n"><input type="number" data-gr="${j}" value="${l.r}"></td>
      <td><select data-gw="${j}">${wires.map(w => `<option ${w === l.wire ? "selected" : ""}>${esc(w)}</option>`).join("")}</select></td>
      <td class="n"><input type="number" data-gt="${j}" value="${l.tension ?? META.wires[l.wire].tension}"></td><td><button class="danger small" data-gd="${j}">Remove</button></td></tr>`).join("")}</table></div>
    <div class="row" style="margin-top:8px"><button class="ghost small" data-gadd>Add guy level</button><button class="ghost small" data-rohn>Rohn 65G 160 ft standard</button>
      <label>Radial ice (in)<select data-gi title="Radial ice thickness on guys and elements. Use the value your engineer gives for the site">
        ${[0, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2].map(v => `<option value="${v}" ${Number(g.ice_in ?? 1) === v ? "selected" : ""}>${v === 0 ? "none" : v + '"'}</option>`).join("")}</select></label><label>Hardware margin (ft)<input type="number" step="0.5" data-gm value="${g.margin_ft ?? 2}"></label>
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
  $("#scanCard").innerHTML = `<div class="card hfta" style="margin-top:14px"><h2>Height scan <span class="chip good">HFTA</span></h2>
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
/* Progress of a background job, with a Cancel link beside the bar. Cancel asks the server to stop the job at its next
   step; the job then ends with the error "Cancelled", which is reported like any other. */
async function poll(job, bar, onError = null) {
  bar.hidden = false; const i = $("i", bar);
  let stop = bar.nextElementSibling && bar.nextElementSibling.classList.contains("jobctl") ? bar.nextElementSibling : null;
  if (!stop) { stop = document.createElement("div"); stop.className = "jobctl small"; bar.insertAdjacentElement("afterend", stop); }
  stop.innerHTML = `<span class="mute" data-ph></span> <a href="#" data-cancel>Cancel</a>`; stop.hidden = false;
  $("[data-cancel]", stop).onclick = async e => { e.preventDefault(); $("[data-cancel]", stop).textContent = "Stopping…"; await api("POST", `/api/job/${job}/cancel`); };
  try {
    for (;;) {
      const j = await api("GET", `/api/job/${job}`);
      i.style.width = j.total ? `${100 * j.done / j.total}%` : "5%";
      $("[data-ph]", stop).textContent = j.total ? `${j.phase}: ${j.done} of ${j.total} runs` : (j.phase || "");
      if (j.state === "done") return j.result;
      if (j.state === "error") { if (onError) onError(j.error || "Calculation failed"); else toast(j.error, 6000); return null; }
      await new Promise(r => setTimeout(r, 600));
    }
  } finally { bar.hidden = true; stop.hidden = true; }
}

/* ---------------------------------------------------------------- 4. Compare */
let CMP = { target: null, ref: null, delta: false, hide: new Set(), sw: false, patternBand: null, patternOffset: 0, plotSeq: 0 };
async function rCompare() {
  const p = P(), el = $("#p-compare"); status();
  el.innerHTML = `<h1>Compare</h1><p class="lead">Every value is an HFTA Figure of Merit (dB, higher is better). Click a value to see the HFTA runs behind it and how to reproduce it.
    Differences of 0.3 dB or less are not significant.</p>
  <div class="grid2"><div class="card"><h2>Run</h2><p class="small mute" id="runInfo">${S.has_results ? "Last run " + esc(S.results_stamp) + "." : "Not run yet."}
    Runs already computed with the same inputs are reused. <b>One tower is sufficient</b>, including a tower with a single antenna.</p>
    <div id="evalNotice" class="note" role="status" hidden></div>
    <div class="row"><button id="evalBtn">Evaluate</button></div><div class="prog" hidden id="evProg"><i></i></div></div>
  <div class="card aux"><h2>Spacing warnings <span class="chip">not part of HFTA</span></h2>
    <p class="small">A <span class="sp red">&#9888;</span> or <span class="sp amber">&#9888;</span> beside a value: the antennas on that band are too close or close
    (set the limits in step 3). HFTA has no mutual coupling, so the value is probably optimistic. The value itself is still the plain HFTA-method result.</p></div></div>
  <div class="card"><div class="row" id="cmpCtl"></div><div class="tbl" style="margin-top:10px"><table id="cmpTbl"></table></div><div id="patternControls" class="row" style="margin-top:18px"></div><div id="cmpPlot" class="plot" style="height:460px"></div><p id="patternNote" class="small mute"></p></div>`;
  const evalNotice = $("#evalNotice");
  const showEvalNotice = (message) => {
    evalNotice.textContent = message; evalNotice.hidden = false; evalNotice.setAttribute("role", "alert");
  };
  const readiness = checkReady();
  if (readiness) showEvalNotice("Before evaluating: " + readiness);
  $("#evalBtn").onclick = async () => {
    try {
      await save(true);
      const bad = checkReady();
      if (bad) { showEvalNotice("Cannot evaluate: " + bad); return; }
      evalNotice.hidden = true;
      const { job } = await api("POST", `/api/v2/p/${SLUG}/evaluate`);
      const r = await poll(job, $("#evProg"), showEvalNotice);
      if (r) {
        if (r.cells === 0) showEvalNotice("No evaluable site/tower/target/band combinations. Check that your one tower serves at least one target, that its antennas use that target's bands, and that the target has an elevation-angle table.");
        else evalNotice.hidden = true;
        S = await api("GET", `/api/v2/p/${SLUG}`);
        // rCompare reconstructs the page; render the result before the notice so it remains visible.
        await rCompare();
        if (r.cells === 0) {
          const n = $("#evalNotice");
          n.textContent = "No evaluable combinations. Check the tower's Served targets, selected bands and target .PRN files.";
          n.hidden = false; n.setAttribute("role", "alert");
        }
      }
    } catch (err) { showEvalNotice("Evaluation failed: " + err.message); }
  };
  RES = await api("GET", `/api/v2/p/${SLUG}/results`);
  if (!RES.cells.length) { $("#cmpTbl").innerHTML = `<tr><td class="mute">No results yet. Press Evaluate.</td></tr>`; return; }
  /* The table shows the last evaluation. Say which towers it does not include, so a new tower is not silently missing. */
  const inRun = new Set(RES.cells.map(c => c.tower)), missing = p.towers.filter(t => !inRun.has(t.id));
  if (missing.length) $("#runInfo").insertAdjacentHTML("afterend", `<div class="note"><b>Not in the last run:</b> ${missing.map(t => esc(t.name)).join(", ")}.
    Press Evaluate to include ${missing.length > 1 ? "them" : "it"}. A tower is also left out if none of its bands is used by the targets it serves.</div>`);
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
  const tg = p.targets.filter(t => RES.cells.some(c => c.target === t.id));
  if (!CMP.target || (CMP.target !== WORLD && !tg.some(t => t.id === CMP.target))) CMP.target = tg[0]?.id;
  const site = id => p.sites.find(s => s.id === id)?.name ?? id, tower = id => p.towers.find(t => t.id === id)?.name ?? id;
  const cells = RES.cells.filter(c => c.target === CMP.target && !CMP.hide.has(c.tower));
  const bands = META.bands.filter(b => cells.some(c => c.band === b));
  const rows = [...new Set(cells.map(c => c.site + "|" + c.tower))];
  if (!CMP.ref || !rows.includes(CMP.ref)) CMP.ref = rows[0];
  $("#cmpCtl").innerHTML = `<div style="width:100%"><span class="small mute">Target shown:</span>
      <div class="tgtabs"><button class="${CMP.target === WORLD ? "" : "ghost"}" data-cmptg="${WORLD}" title="Every target together: weighted mean of the FOM over all targets, per band. For one tower that must work everywhere">Worldwide</button>${tg.map(t => `<button class="${t.id === CMP.target ? "" : "ghost"}" data-cmptg="${t.id}" title="Results for paths to ${esc(t.name)}, bearing ${t.heading}°">${esc(t.name)} <span class="small">${t.heading}°</span></button>`).join("")}</div></div>
    <label style="flex-direction:row;align-items:center;gap:6px"><input type="checkbox" id="cmpDelta" ${CMP.delta ? "checked" : ""}> Show differences from the reference row</label>
    <label style="flex-direction:row;align-items:center;gap:6px"><input type="checkbox" id="cmpSw" ${CMP.sw ? "checked" : ""}> Show switch settings (which antennas HFTA used)</label>
    <div style="width:100%"><span class="small mute">Towers shown:</span> ${[...new Set(RES.cells.map(c => c.tower))].map(id => `<label style="flex-direction:row;align-items:center;gap:4px;display:inline-flex;margin-right:10px">
      <input type="checkbox" data-cmpshow="${id}" ${CMP.hide.has(id) ? "" : "checked"} title="Show or hide this tower's rows. Hiding changes nothing in the project">${esc(tower(id))}</label>`).join("")}</div>`;
  $$("[data-cmpshow]").forEach(cb => cb.onchange = () => { cb.checked ? CMP.hide.delete(cb.dataset.cmpshow) : CMP.hide.add(cb.dataset.cmpshow); matrix(); });
  $$("[data-cmptg]").forEach(b => b.onclick = () => { CMP.target = b.dataset.cmptg; matrix(); });
  $("#cmpDelta").onchange = e => { CMP.delta = e.target.checked; matrix(); };
  $("#cmpSw").onchange = e => { CMP.sw = e.target.checked; matrix(); };
  if (CMP.target === WORLD) return worldwide(tg, site, tower);
  const val = c => c ? c.hfta : null;
  const get = (row, b) => cells.find(c => c.site + "|" + c.tower === row && c.band === b);
  const best = Object.fromEntries(bands.map(b => [b, Math.max(...rows.map(r => val(get(r, b)) ?? -1e9))]));
  /* Overall = mean over the bands, as in the Stack Designer. Only when the row has a value on every band. Rows ranked by it. */
  const overall = r => { const v = bands.map(b => { const c = get(r, b); return c && !c.issues.length ? val(c) : null; }); return v.every(x => x != null) ? v.reduce((a, b) => a + b, 0) / v.length : null; };
  rows.sort((a, b) => (overall(b) ?? -1e9) - (overall(a) ?? -1e9));
  const bestAll = Math.max(...rows.map(r => overall(r) ?? -1e9));
  let h = `<tr><th>Ref.</th><th>#</th><th>Site</th><th>Tower</th><th class="n" title="Mean over the bands. Rows are ranked by this value">Overall</th>${bands.map(b => `<th class="n">${b} m</th>${CMP.sw ? `<th class="small mute">switch (ft)</th>` : ""}`).join("")}</tr>`;
  for (const [k, r] of rows.entries()) {
    const [sid, tid] = r.split("|"), o = overall(r), ro = overall(CMP.ref);
    const oShown = o == null ? "–" : CMP.delta && r !== CMP.ref ? (ro == null ? "–" : (o - ro >= 0 ? "+" : "") + fmt(o - ro)) : fmt(o);
    h += `<tr><td><input type="radio" name="ref" value="${r}" ${r === CMP.ref ? "checked" : ""} aria-label="Reference row"></td><td class="mute">${k + 1}</td><td>${esc(site(sid))}</td><td>${esc(tower(tid))}</td>
      <td class="n${o != null && Math.abs(o - bestAll) < 0.005 ? " best" : ""}"><b>${oShown}</b></td>`;
    for (const b of bands) {
      const c = get(r, b), v = val(c);
      if (!c) { h += `<td class="mute">–</td>${CMP.sw ? "<td></td>" : ""}`; continue; }
      if (c.issues.length) { h += `<td class="small neg" colspan="${CMP.sw ? 2 : 1}">${esc(c.issues[0])}</td>`; continue; }
      let shown = fmt(v), cls = "n cell" + (Math.abs(v - best[b]) < 0.005 ? " best" : "");
      if (CMP.delta && r !== CMP.ref) { const rv = val(get(CMP.ref, b)); shown = rv === null ? "–" : (v - rv >= 0 ? "+" : "") + fmt(v - rv); }
      let sub = c.spacing ? ` <span class="sp ${c.spacing}" title="${esc(c.spacing_text.join("\n"))}">&#9888;</span>` : "";
      if ((c.notes || []).length) sub += ` <span class="small amb" title="${esc(c.notes.join("\n"))}">*</span>`;
      const use = (c.use || []).join(" / ");
      h += `<td class="${cls}" data-i="${c.i}" title="Show the HFTA runs${use ? `. Antennas in use: ${use} ft` : ""}">${shown}${sub}</td>${CMP.sw ? `<td class="small mute">${use}</td>` : ""}`;
    }
    h += "</tr>";
  }
  $("#cmpTbl").innerHTML = h;
  $$("input[name=ref]").forEach(x => x.onchange = () => { CMP.ref = x.value; matrix(); });
  $$("td.cell").forEach(td => td.onclick = () => cellDrawer(Number(td.dataset.i)));
  // OpenHFTA uses full elevation-pattern curves, not FOM bars: each gain null matters.
  // Each curve is a real OpenHFTA pattern for one selected heading; FOM remains in the table and legend.
  showElevationPatterns(cells, rows, site, tower);

}
/* Match OpenHFTA's plot_multiple_patterns: gain (dBi) against 0.25°-spaced
   elevation angles, FOM in the legend, optional angle-of-arrival bars on the right axis.
   A scalar FOM by band cannot show lobes or nulls, so it is not used as a substitute. */
async function showElevationPatterns(cells, rows, siteName, towerName) {
  const controls = $("#patternControls"), plot = $("#cmpPlot"), note = $("#patternNote");
  if (!controls || !plot || !note) return;
  const seq = ++CMP.plotSeq;
  const target = P().targets.find(t => t.id === CMP.target);
  const bands = META.bands.filter(b => cells.some(c => c.band === b && c.hfta != null && !c.issues.length));
  plot.hidden = false;
  if (!target || !bands.length || !rows.length) {
    controls.textContent = "No valid elevation patterns for this target yet.";
    note.textContent = "Select a target with evaluated HFTA results to see its elevation curves.";
    Plotly.purge(plot);
    return;
  }
  if (!bands.includes(CMP.patternBand)) CMP.patternBand = bands[0];
  const offsets = target.offsets?.length ? target.offsets : [0];
  if (!offsets.includes(CMP.patternOffset)) CMP.patternOffset = offsets.includes(0) ? 0 : offsets[0];
  controls.innerHTML = `<label>Band<select id="patternBand">${bands.map(b => `<option value="${b}" ${b === CMP.patternBand ? "selected" : ""}>${b} m</option>`).join("")}</select></label>
    <label>Terrain heading<select id="patternHeading">${offsets.map(o => `<option value="${o}" ${o === CMP.patternOffset ? "selected" : ""}>${((Number(target.heading) + Number(o)) % 360 + 360) % 360}° (${o > 0 ? "+" : ""}${o}° offset)</option>`).join("")}</select></label>`;
  $("#patternBand").onchange = e => { CMP.patternBand = e.target.value; showElevationPatterns(cells, rows, siteName, towerName); };
  $("#patternHeading").onchange = e => { CMP.patternOffset = Number(e.target.value); showElevationPatterns(cells, rows, siteName, towerName); };
  note.textContent = "Loading OpenHFTA elevation patterns…";
  const selected = cells.filter(c => c.band === CMP.patternBand && c.hfta != null && !c.issues.length);
  if (!selected.length) { Plotly.purge(plot); note.textContent = "No valid runs on this band."; return; }
  const desiredAz = ((Number(target.heading) + CMP.patternOffset) % 360 + 360) % 360;
  const distance = a => Math.abs(((Number(a) - desiredAz + 540) % 360) - 180);
  const patterns = await Promise.all(selected.map(async c => {
    try {
      const d = await api("GET", `/api/v2/p/${SLUG}/cell/${c.i}`);
      const best = d.cell.best == null ? null : d.cell.options[d.cell.best];
      const pick = best?.az?.reduce((a, b) => distance(a.az) <= distance(b.az) ? a : b);
      const gain = pick ? d.patterns[pick.run] : null;
      if (!Array.isArray(gain) || gain.length !== d.angles.length) return null;
      return { c, angles: d.angles, gain, pick, aoa: d.aoa };
    } catch (_) { return null; }
  }));
  if (seq !== CMP.plotSeq || !document.contains(plot)) return;
  const good = patterns.filter(Boolean);
  if (!good.length) { Plotly.purge(plot); note.textContent = "No valid elevation patterns were returned; inspect a result cell for details."; return; }
  const traces = good.map((d, i) => ({
    type: "scatter", mode: "lines", x: d.angles, y: d.gain,
    name: `${siteName(d.c.site)} / ${towerName(d.c.tower)} · FOM ${fmt(d.pick.fom, 1)} dB at ${d.pick.az}°`,
    line: { color: PAL[i % PAL.length], width: 2 },
    hovertemplate: "%{x:.2f}° · %{y:.1f} dBi<extra>%{fullData.name}</extra>"
  }));
  const aoa = good.find(x => x.aoa && Object.keys(x.aoa).length)?.aoa;
  if (aoa) {
    const angles = Object.keys(aoa).map(Number).filter(Number.isFinite).sort((a, b) => a - b);
    traces.push({ type: "bar", x: angles, y: angles.map(a => 100 * Number(aoa[a])),
      name: "Arrival angles", yaxis: "y2", opacity: 0.21,
      marker: { color: css("--warn") }, width: 0.35,
      hovertemplate: "%{x:.0f}° · %{y:.1f}% probability<extra>Arrival angles</extra>" });
  }
  const vals = good.flatMap(d => d.gain.slice(2)).filter(Number.isFinite);
  const ymin = vals.length ? Math.min(...vals) - 2 : -35;
  const ymax = vals.length ? Math.max(...vals) + 2 : 20;
  const layout = plotLayout({
    title: { text: `${target.name}: ${CMP.patternBand} m elevation patterns (OpenHFTA)`, font: { size: 14 } },
    xaxis: { title: "Elevation angle (°)", range: [0, 35], gridcolor: css("--line") },
    yaxis: { title: "Gain (dBi)", range: [ymin, ymax], gridcolor: css("--line") },
    yaxis2: { title: "Arrival-angle probability (%)", overlaying: "y", side: "right", showgrid: false, rangemode: "tozero" },
    legend: { orientation: "h", y: -0.3 }, barmode: "overlay",
    margin: { l: 55, r: 75, t: 58, b: 75 }
  });
  await Plotly.react(plot, traces, layout, { displaylogo: false, responsive: true });
  if (seq !== CMP.plotSeq) return;
  note.textContent = `Each curve is the actual 0.25°-resolution OpenHFTA gain pattern for the selected heading (${desiredAz}°). The FOM in each legend is averaged over the target's selected headings, so it is not the gain at the pattern's highest peak. The arrival-angle bars use the right-hand axis. Select another band or heading to examine nulls and lobes.`;
}

const WORLD = "__world__";
/* Worldwide view. Band columns: for each site/tower and band, the weighted mean FOM over the targets (information).
   Overall: for each target, the mean over its bands; then the weighted mean over the targets (weights from the Stack
   Designer, 1 when not set; weight 0 leaves a target out). This is exactly the Stack Designer's Overall
   (core/compromise.py), so a layout applied from the Designer gets the same value here.
   A row is ranked only when it has a value on every target and on every band that target has in any row. */
function worldwide(tg, site, tower) {
  const p = P(), W = p.settings.compromise?.weights || {}, wt = t => W[t.id] ?? 1;
  const used = tg.filter(t => wt(t) > 0);
  const cells = RES.cells.filter(c => used.some(t => t.id === c.target) && !c.issues.length && c.hfta !== null && !CMP.hide.has(c.tower));
  const bands = META.bands.filter(b => cells.some(c => c.band === b));
  const rows = [...new Set(RES.cells.filter(c => !CMP.hide.has(c.tower)).map(c => c.site + "|" + c.tower))];
  if (!CMP.ref || !rows.includes(CMP.ref)) CMP.ref = rows[0];
  if (!rows.length) { $("#cmpTbl").innerHTML = `<tr><td class="mute">No tower ticked.</td></tr>`; Plotly.purge("cmpPlot"); return; }
  const cellOf = (r, b) => {
    let num = 0, den = 0, n = 0, warn = null;
    for (const t of used) {
      const c = cells.find(x => x.site + "|" + x.tower === r && x.band === b && x.target === t.id); if (!c) continue;
      num += wt(t) * c.hfta; den += wt(t); n++; if (c.spacing === "red" || (c.spacing && !warn)) warn = c.spacing;
    }
    return den ? { v: num / den, n, warn } : null;
  };
  const data = Object.fromEntries(rows.map(r => [r, Object.fromEntries(bands.map(b => [b, cellOf(r, b)]))]));
  const tBands = Object.fromEntries(used.map(t => [t.id, META.bands.filter(b => cells.some(c => c.target === t.id && c.band === b))]));
  const tMean = (r, t) => {
    const v = tBands[t.id].map(b => cells.find(c => c.site + "|" + c.tower === r && c.band === b && c.target === t.id)?.hfta).filter(x => x != null);
    return v.length ? { v: v.reduce((a, b) => a + b, 0) / v.length, complete: v.length === tBands[t.id].length } : null;
  };
  const OV = Object.fromEntries(rows.map(r => {
    let num = 0, den = 0, complete = true;
    for (const t of used) { const m = tMean(r, t); if (!m) { complete = false; continue; } num += wt(t) * m.v; den += wt(t); if (!m.complete) complete = false; }
    return [r, { v: den ? num / den : null, complete }];
  }));
  const allb = r => OV[r].v;
  const nB = b => used.filter(t => (t.bands || []).includes(b)).length;   /* targets that use band b */
  /* Rows with complete coverage are ranked first; a row missing a target or a band is not comparable, so it goes below. */
  const full = r => OV[r].complete;
  /* Best markers only among comparable rows: a band value averaged over fewer targets is not the same quantity. */
  const best = Object.fromEntries([...bands.map(b => [b, Math.max(...rows.map(r => data[r][b] && data[r][b].n === nB(b) ? data[r][b].v : -1e9))]), ["all", Math.max(...rows.map(r => full(r) ? allb(r) ?? -1e9 : -1e9))]]);
  const show = (r, v, refv, key) => {
    if (v == null) return `<td class="mute n">–</td>`;
    const cls = "n" + (Math.abs(v - best[key]) < 0.005 ? " best" : "");
    return `<td class="${cls}">${CMP.delta && r !== CMP.ref ? (refv == null ? "–" : (v - refv >= 0 ? "+" : "") + fmt(v - refv)) : fmt(v)}</td>`;
  };
  rows.sort((a, b) => (full(b) - full(a)) || ((allb(b) ?? -1e9) - (allb(a) ?? -1e9)));
  let h = `<tr><th>Ref.</th><th>#</th><th>Site</th><th>Tower</th><th class="n" title="For each target, the mean over its bands; then the weighted mean over the targets. Same as the Stack Designer's Overall. Rows are ranked by this value">Overall</th>${bands.map(b => `<th class="n">${b} m</th>`).join("")}</tr>`;
  for (const [k, r] of rows.entries()) {
    const [sid, tid] = r.split("|");
    h += `<tr><td><input type="radio" name="ref" value="${r}" ${r === CMP.ref ? "checked" : ""} aria-label="Reference row"></td><td class="mute">${k + 1}</td><td>${esc(site(sid))}</td><td>${esc(tower(tid))}</td>`
      + show(r, allb(r), allb(CMP.ref), "all").replace(/>([^<]*)<\/td>$/, `><b>$1</b>${full(r) ? "" : ' <span class="small mute" title="No value on some targets or bands: not ranked with the others">partial</span>'}</td>`);
    for (const b of bands) {
      const d = data[r][b]; h += show(r, d?.v, data[CMP.ref][b]?.v, b).replace("</td>",
        (d && d.n < nB(b) ? ` <span class="small mute" title="Only ${d.n} of the ${nB(b)} targets that use ${b} m: the tower does not serve the others">(${d.n}/${nB(b)})</span>` : "") +
        (d?.warn ? ` <span class="sp ${d.warn}" title="Spacing warning on at least one target">&#9888;</span>` : "") + "</td>");
    }
    h += "</tr>";
  }
  $("#cmpTbl").innerHTML = h + `<tr><td colspan="${bands.length + 5}" class="small mute">Overall = for each target the mean over its bands, then the weighted mean over ${used.map(t => `${esc(t.name)}${wt(t) !== 1 ? ` ×${wt(t)}` : ""}`).join(", ")}.
    Weights come from the Stack Designer (1 if not set). "(n/N)" = the tower serves only n of the N targets that use that band, so its value is not comparable with a tower that serves all of them.
    Click a target button to see the HFTA runs behind a value.</td></tr>`;
  $$("input[name=ref]").forEach(x => x.onchange = () => { CMP.ref = x.value; matrix(); });
  // Worldwide combines multiple paths and bands, so it has no physically meaningful
  // single elevation curve. The scalar scores remain in the table above.
  CMP.plotSeq++;
  $("#patternControls").innerHTML = "<b>Worldwide summary</b>";
  $("#patternNote").textContent = "Worldwide averages multiple targets; a single elevation pattern cannot represent it. Choose a specific target above to display the original OpenHFTA-style gain curves and their lobes/nulls.";
  Plotly.purge("cmpPlot");
  $("#cmpPlot").hidden = true;
}
async function cellDrawer(i) {
  const d = await api("GET", `/api/v2/p/${SLUG}/cell/${i}`), c = d.cell, p = P();
  const site = p.sites.find(s => s.id === c.site)?.name, tower = p.towers.find(t => t.id === c.tower)?.name, tgt = p.targets.find(t => t.id === c.target);
  const st = p.settings, best = c.best != null ? c.options[c.best] : null;
  if (!best || !tgt) {
    $("#drawerBody").innerHTML = `<h2>${esc(site)} · ${esc(tower)} · ${esc(tgt?.name || "?")} · ${c.band} m</h2><div class="note"><b>No result.</b> ${esc([...(c.issues || []), d.aoa_note || ""].filter(Boolean).join(" ")) || "No switch setting could be scored."}</div>`;
    $("#drawer").hidden = false; return;
  }
  let h = `<h2>${esc(site)} · ${esc(tower)} · ${esc(tgt.name)} · ${c.band} m</h2>
    <p><b>FOM ${fmt(c.hfta_fom)} dB</b> with antennas at ${best.heights.join(" / ")} ft. </p>
    ${(c.notes || []).length ? `<div class="note small"><b>Calculation notes.</b> ${c.notes.map(esc).join("<br>")}<br>Filled angles are estimates between their neighbours, not core output.</div>` : ""}
    ${(c.spacing || []).length ? `<h3>Spacing warnings</h3>${warnList(c.spacing)}<p class="small mute">HFTA has no mutual coupling. The FOM above is the plain HFTA-method value and is probably optimistic.</p>` : ""}
    <h3>Switch settings</h3><div class="tbl"><table><tr><th>Antennas in use (ft)</th>${c.options[0].az.map(a => `<th class="n">${a.az}°</th>`).join("")}<th class="n">Weighted mean</th></tr>
    ${c.options.map((o, k) => `<tr><td>${o.heights.join(" / ")}${k === c.best ? ' <span class="chip good">best</span>' : ""}</td>${o.az.map(a => `<td class="n">${a.fom == null ? '<span class="neg" title="Run failed">failed</span>' : fmt(a.fom)}${a.filled_deg ? ' <span class="small amb" title="Some angles filled by interpolation">*</span>' : ""}</td>`).join("")}<td class="n"><b>${fmt(o.score)}</b></td></tr>`).join("")}</table></div>
    <p class="small mute">Weights: ${c.options[0].az.map(a => a.weight).join(", ")}. Mean = Σ(weight × FOM) ÷ Σ weight. Best setting = highest mean.</p>
    <div id="cellPlot" class="plot"></div>
    <h3>Reproduce in the original HFTA</h3><p class="small mute">Calculated with ${esc(d.engine?.name || "OpenHFTA")}${d.engine?.commit ? ` (commit ${esc(String(d.engine.commit).slice(0, 12))})` : ""}.</p><p class="small">Units feet. All antennas in phase. Ground: dielectric ${st.epsr}, conductivity ${st.sigma} S/m. Diffraction ${st.diffraction ? "on" : "off"}. Elevation file: <b>${esc(d.prn)}</b>.</p>
    <div class="tbl"><table><tr><th>Heading</th><th>Terrain file</th><th class="n">MHz</th><th>Type</th><th>Heights (ft)</th><th class="n">HFTA FOM</th></tr>
    ${best.az.map(a => { const r = d.runs[a.run]; return `<tr><td>${a.az}°</td><td>${esc(r.file)}</td><td class="n">${r.freq}</td><td>${r.hfta_type}</td><td>${r.heights_ft.join(" / ")}</td><td class="n">${fmt(a.fom)}</td></tr>`; }).join("")}</table></div>
    <button class="ghost small" id="copyRec">Copy these runs as text</button>`;
  $("#drawerBody").innerHTML = h; $("#drawer").hidden = false;
  const tr = best.az.filter(a => d.patterns[a.run]).map((a, k) => ({ x: d.angles, y: d.patterns[a.run], name: `${a.az}° (${d.runs[a.run].file})`, mode: "lines", line: { color: PAL[k % 8] } }));
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
  const ex = (k, t, d, alt) => `<div class="card"><h2>${t}</h2><p class="small">${d}</p><button data-ex="${k}" ${!S.has_results && !["project", "bundle"].includes(k) ? "disabled" : ""}>Download</button>${alt ? ` <button class="ghost" data-ex="${alt[0]}" ${!S.has_results && !["project", "bundle"].includes(k) ? "disabled" : ""}>${alt[1]}</button>` : ""}</div>`;
  $("#p-report").innerHTML = `<h1>Report and export</h1><p class="lead">Every exported number is an OpenHFTA result (the HFTA method; checked against original-HFTA output). Spacing warnings and the guy check are included as notes; they never change a number.</p>
  ${S.has_results ? "" : `<div class="note">Run the evaluation in step 4 first.</div>`}
  <p class="small mute">Calculations by OpenHFTA (RioDXGroup, github.com/RioDXGroup/openhfta), used unchanged. HFTA by R. Dean Straw, N6BV, published with
  <i>The ARRL Antenna Book</i>. ARRL elevation-angle files are copyright ARRL and are supplied by the user. Not affiliated with or endorsed by ARRL or the OpenHFTA authors.</p>
  <div class="exports">
    ${ex("html", "Report (HTML)", "One self-contained page to read, print or send: inputs, comparison tables, charts, guy check, and how to reproduce.")}
    ${ex("xlsx", "Workbook (Excel)", "Results, every HFTA run, and the combination of runs as live formulas, so each number can be traced.")}
    ${ex("replay", "HFTA replay pack (zip)", "Every terrain file used, each run with its exact HFTA inputs and FOM, expected patterns in OUT.PRN layout, and step-by-step instructions. <b>Download</b> = shareable: the .PRN files are left out (copyright ARRL) and listed by name and checksum. <b>With .PRN files</b> = private copy for your own records; do not share it.", ["replay?prn=1", "With .PRN files (private)"])}
    ${ex("csv", "Results (CSV)", "One row per site, tower, target and band, for your own spreadsheet.")}
    ${ex("bundle", "Project with files (zip)", "The project with its terrain and .PRN files, for moving <b>your own</b> project to another of your computers (“Open project zip”). Results are recomputed there. <b>Shareable</b> leaves the .PRN files out, for giving the project to someone else.", ["bundle?prn=0", "Shareable (no .PRN)"])}
    ${ex("project", "Project file (settings only)", "The project settings without terrain or .PRN files.")}
  </div>
  <div class="card" style="margin-top:14px"><h2>Delete this project</h2><p class="small">Removes the project “${esc(p.name)}” with all its files on the server: terrain, .PRN files and results.
  The library is not touched. Download the project zip first if you may want it back.</p><button class="danger" id="delProj">Delete project…</button></div>`;
  $("#delProj").onclick = () => {
    modal(`<h2>Delete “${esc(p.name)}”?</h2><p>All its files on the server are removed. This cannot be undone.</p>
      <div class="row"><button class="danger" id="delYes">Delete</button><button class="ghost" id="delNo">Keep</button></div>`);
    $("#delNo").onclick = closeModal;
    $("#delYes").onclick = async () => {
      try {
        const r = await api("DELETE", `/api/v2/p/${SLUG}`); closeModal(); META.projects = r.projects;
        try { localStorage.removeItem("hfta-project"); } catch (e) { /* ignore */ }
        toast("Project deleted"); location.reload();
      } catch (e) { toast(e.message, 5000); }
    };
  };
  $$("[data-ex]").forEach(b => b.onclick = () => { window.location = `/api/v2/p/${SLUG}/export/${b.dataset.ex}`; });
}

/* ---------------------------------------------------------------- start */
async function openProject(slug) {
  await flushSave();
  SLUG = slug; S = await api("GET", `/api/v2/p/${slug}`);
  try { localStorage.setItem("hfta-project", slug); } catch (e) { /* storage unavailable */ }
  /* Target called "South Asia" (the ARRL file's own wording) becomes "Asia", once, whichever page opens first. */
  if (P().targets.some(t => /^south asia$/i.test(t.name || ""))) { P().targets.forEach(t => { if (/^south asia$/i.test(t.name || "")) t.name = "Asia"; }); await save(true); }
  render();
}
async function init() {
  META = await api("GET", "/api/v2/meta");
  try {
    const who = await api("GET", "/api/whoami");
    if (who.accounts) $("#userBox").innerHTML = `${esc(who.user)} · ${who.admin ? `<a href="/admin">Users</a> · ` : ""}<a href="/logout">Log out</a>`;
  } catch (e) { /* no accounts */ }
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
  $("#helpBtn").onclick = showHelp;
  document.addEventListener("keydown", e => { if (e.key === "Escape") { $("#drawer").hidden = true; closeModal(); } });
  await openProject(SLUG);
}
init().catch(e => { document.body.innerHTML = `<p style="padding:20px">Could not start: ${esc(e.message)}</p>`; });

/* ---------------------------------------------------------------- hover help */
const TIPS = [
  // Sites
  ["#soil", "Ground type under and in front of the tower. Sets the two values beside it. For horizontal antennas the choice changes the FOM by under 0.2 dB (80 m) and under 0.1 dB from 40 m up; leave it at Average unless the path crosses water."],
  ["#epsr", "Dielectric constant of the ground (HFTA input). 13 = average soil."],
  ["#sigma", "Ground conductivity in siemens per metre (HFTA input). 0.005 = average soil."],
  ["#diff", "HFTA's diffraction model over hill tops. Leave on unless you are comparing with an old HFTA run made without it."],
  ["[data-k=lat]", "Latitude in decimal degrees, north positive. Example: 43.67214"],
  ["[data-k=lon]", "Longitude in decimal degrees, west negative. Example: -71.99089"],
  ["[data-src]", "Where the imported files came from. Shown on the site card and in the report."],
  ["[data-act=import]", "Load .PRO terrain files, or a .zip of them. The azimuth must be in each file name."],
  ["[data-act=dem]", "Make one profile per degree from an elevation file on this computer (GeoTIFF or ESRI ASCII grid)."],
  ["[data-act=flat]", "Flat ground in every direction. A reference: shows what the terrain adds or takes away."],
  ["[data-act=download]", "Download this site's .PRO files as a .zip, to load them into HFTA itself."],
  ["[data-act=clear]", "Delete this site's terrain files. The site and its position stay."],
  ["[data-act=del]", "Delete this site and its terrain files."],
  ["#addSite", "Another possible tower position."],
  ["#cmpAz", "Compass direction for the profile plot."],
  // Targets
  ["#prnBtn", "Elevation-angle files (.PRN), one per path: ARRL files from the Antenna Book, or tables made here with VOACAP."],
  ["#prnGen", "Make an elevation-angle table with VOACAP for any origin in the world, for a region, a season, a time of day or a single DX path."],
  ["#prnToLib", "Keep these files in your library, so every new project starts with them."],
  ["#prnFromLib", "Copy the library's .PRN files into this project."],
  ["[data-prv]", "Plot the file: how often openings arrive at each elevation angle, per band."],
  ["#tgBrg", "Set each target's bearing and spread from the site position to a reference point in its region, and name it after its file if it still has another region's name."],
  ["[data-act=auto]", "Download elevation data for this position and write one profile per degree. USGS 3DEP inside the United States, Terrain Tiles anywhere else."],
  ["[data-act=lib]", "Keep this site, with its terrain files, in your library for other projects."],
  ["[data-act=move]", "A copy of this site a set distance and bearing away, to test how much the result depends on the exact position."],
  ["#libSite", "Add a site saved in your library, with its terrain."],
  ["#libTw", "Add a tower saved in your library."],
  ["#addTw", "A new tower with one antenna. Towers can stand at one site or at every site."],
  ["[data-k=name]", "Name shown in tables and reports."],
  ["[data-k=notes]", "Free text, shown in the report."],
  ["#evalBtn", "Run OpenHFTA for every site, tower, target and band. Runs with unchanged inputs are reused."],
  ["#cmpDelta", "Show each value as the difference from the reference row instead of the absolute FOM."],
  ["#cmpSw", "Add a column after each band with the heights HFTA switched in for the best value. Hidden by default; the value's tooltip shows it too."],
  ["#delProj", "Remove this project and all its files from the server. The library is not touched."],
  ["[data-k=prn]", "Elevation-angle file for this path. It says how often openings arrive at each angle, per band."],
  ["[data-k=heading]", "Great-circle bearing from your site to the target, degrees true."],
  ["[data-sp]", "Also judge the target this many degrees either side of the bearing. 0 = bearing only."],
  ["[data-st]", "Step between the headings inside the spread."],
  ["[data-w]", "Weights of the headings, e.g. 1, 2, 1 to count the centre twice. Empty = equal."],
  ["[data-b]", "Bands evaluated for this target. Antennas on unticked bands are not run for it."],
  ["#addTg", "Another region or path."],
  // Towers
  ["[data-k=site]", "Where this tower stands. Every site = try the same tower at all sites to compare positions."],
  ["[data-k=height_ft]", "Height of the tower itself. Used for the drawing and the guy check, not by HFTA."],
  ["[data-k=switching]", "Which parts of each stack HFTA may select per target and band: the whole stack only, a stack switch (all, pairs, singles), or every combination."],
  ["[data-tg]", "Targets this tower is judged on. A fixed tower should serve only the targets it points at."],
  ["[data-ah]", "Height of this antenna above the tower base, feet."],
  ["[data-ae]", "Elements on this band (HFTA generic Yagi). Empty = the antenna does not work on this band."],
  ["[data-atr]", "Distance from the mast to the furthest element tip. Used only by the guy check."],
  ["[data-adr]", "How far the element tips hang below the boom. Used only by the guy check."],
  ["[data-ad]", "Remove this antenna."],
  ["[data-add]", "Add an empty row above the top antenna. Choose its bands and elements, or a band set."],
  ["[data-addsame]", "Add another antenna of the same type as the top one, 30 ft above it: the next antenna of a stack."],
  ["[data-copy]", "The same tower, as a separate copy, at another site."],
  ["[data-gh]", "Height where this guy level is attached to the tower."],
  ["[data-gr]", "Distance from the tower base to the guy anchor."],
  ["[data-gw]", "Guy material. Sets weight and diameter for the sag and ice load."],
  ["[data-gt]", "Tension when installed, pounds. Typically 10% of breaking strength."],
  ["[data-gi]", "Radial ice on guys and elements. Use the value your engineer gives for the site."],
  ["[data-gm]", "Extra clearance kept free for hardware and movement, feet."],
  ["[data-gadd]", "Another guy level."],
  ["[data-rohn]", "Fill the guy table with the Rohn 65G 160 ft standard layout."],
  ["[data-gcheck]", "Check every turning antenna against every guy, with ice and droop."],
  // Stack Designer
  ["#cmSite", "Terrain used for the search."],
  ["#cmSw", "Stack switching assumed for every band, as on the tower."],
  ["#cmMax", "Height of the tower: the highest any antenna may go. Every group's To follows it."],
  ["#cmGap", "Smallest distance between antennas of different groups."],
  ["#cmOrder", "Force the groups in list order: first group on top, or at the bottom."],
  ["#cmGuy", "Reject heights where an antenna would touch an iced guy of this tower."],
  ["[data-ct]", "Include this target in the search."],
  ["[data-cw]", "Weight of this target in the overall score. 2 = counts twice; 0 = left out."],
  ["[data-gn]", "Name used in the results."],
  ["[data-ge]", "Elements on this band. Several bands in one row = one multiband antenna."],
  ["[data-gf][data-key=count]", "How many antennas of this kind."],
  ["[data-gf][data-key=count_max]", "Also try up to this many antennas of this kind, so one search compares two against three. Empty = exactly Count."],
  ["[data-gf][data-key=lo]", "Lowest height tried for this group. Empty = from one step above the ground."],
  ["[data-gf][data-key=hi]", "Highest height tried for this group. Follows the tower height; lower it when guys or a mast section limit this group."],
  ["#scGo", "Run one antenna at each height between From and To against the chosen target and band."],
  ["[data-del]", "Remove this target."],
  ["[data-azsel]", "Choose the target to set on the map: click or drag on the map for its bearing, slider for its spread."],
  ["[data-act=del]", "Delete this site and its terrain files."],
  ["[data-ex]", "Download this export."],
  ["[data-ex='replay?prn=1']", "Private copy with your .PRN files inside: for your own records only, do not share."],
  ["[data-ex='bundle?prn=0']", "Project zip without the .PRN files, for giving the project to someone else."],
  ["input[name=ref]", "Reference row: with 'Show differences' on, every other row is shown relative to this one."],
  ["[data-gf][data-key=step]", "Height step of the search, feet. Smaller = slower and finer."],
  ["[data-gf][data-key=min_spacing]", "Smallest distance between two antennas of this group."],
  ["[data-gf][data-key=equal_tol]", "Keep the gaps inside the stack equal within this many feet. Empty = any spacing."],
  ["[data-gf][data-key=turning_radius]", "Distance from the mast to the furthest element tip. Needed for the guy check."],
  ["[data-gf][data-key=droop]", "How far the element tips hang below the boom. Needed for the guy check."],
  ["[data-gx]", "Remove this group."],
  ["#cmAddG", "Another kind of antenna."],
  ["#cmGo", "Run the search. Large searches take minutes; progress is shown, and Cancel beside the bar stops it."],
  ["[data-apply]", "Add this layout to the Towers page, at the Designer's site."],
  ["#cmCurveSel", "Group shown in the chart."],
  // Height scan
  ["#scSite", "Terrain used for the scan."], ["#scTg", "Target for the scan."], ["#scEl", "Elements of the single antenna."],
  ["#scBand", "Band of the scan."], ["#scLo", "Lowest height scanned."], ["#scHi", "Highest height scanned."], ["#scSt", "Step between heights."],
  // Compare
  ["#evalBtn", "Run HFTA for every tower at its site, every target and band. Runs already done with the same inputs are reused."],
  ["[data-cmptg]", "Show the results for this target."],
  ["#cmpDelta", "Show each value as the difference from the reference row."],
  // Top bar
  ["#newProj", "Start an empty project."], ["#openProj", "Open a project saved with 'Project with files'."], ["#helpBtn", "How to use the planner."],
];
function applyTips(root = document) {
  for (const [sel, tip] of TIPS) for (const el of root.querySelectorAll(sel)) if (!el.title) el.title = tip;
}
new MutationObserver(() => applyTips()).observe(document.documentElement, { childList: true, subtree: true });

/* ---------------------------------------------------------------- help */
function showHelp() {
  $("#drawerBody").innerHTML = `<h2>How to use the planner</h2>
  <p class="small mute">Every number comes from OpenHFTA runs (the HFTA method). The planner only organises the runs and the arithmetic between them.
  New here? Read the one-page <a href="/guide" target="_blank" rel="noopener">getting-started guide</a> (it prints well).</p>

  <h3>1. Sites</h3>
  <p>A site is one position where a tower could stand. Enter its latitude and longitude. Then give it terrain, one file per compass direction:</p>
  <ul>
    <li><b>Fetch terrain online</b>: one click. Inside the United States it uses USGS 3DEP (1 m lidar where available). Anywhere else it uses
    AWS Terrain Tiles (Tilezen): SRTM worldwide, better national data in much of Europe, Canada, Australia and New Zealand, and ArcticDEM north of 60°,
    about 30 m spacing, which the ARRL HFTA notes call sufficient for HF. All of these measure tree tops, not the ground.</li>
    <li><b>Import .PRO or .zip</b>: files from MicroDEM or a K6TU terrain set.</li>
    <li><b>Generate from DEM file</b>: a GeoTIFF or ASCII grid you downloaded yourself.</li>
    <li><b>Flat ground</b>: no terrain, for a reference run.</li>
  </ul>
  <p>Add two or more sites to compare positions. <b>Copy, moved…</b> makes a second site a set distance away, to see how much the result depends on the exact position (HFTA's move-the-tower check).</p>
  <p><b>Profile length and far horizon.</b> HFTA reads at most 148 points per profile: 4.4 km at 30 m is the standard. The fetch can also make 10 km profiles at 68 m, but coarser spacing changes results on rough ground by about 1 dB, so compare 10 km profiles only with other 10 km profiles. After every fetch the site card shows the <b>far horizon</b>: the highest elevation angle of ground between the end of the profile and 15 km, seen from 30 m up the tower. Near or above 1° means a distant ridge that the standard profile does not contain; that is when the 10 km profile is worth a run.</p>

  <p><b>Elevation-angle tables with VOACAP.</b> Targets → "Generate with VOACAP…" makes a .PRN table for any origin in the world, the way the
  ARRL files were made: VOACAP is run for every month, hour and three solar levels to several points in the region, and every propagation mode
  counts its elevation angle, weighted by its reliability. For the W1 (Boston) origin the result was checked against the ARRL W1 files: on
  Europe, Japan, Asia, Africa, Oceania and South America the FOM ranking of test antennas agrees within about 1 dB on nearly every band
  (worst 2 dB); USA agrees within 2 dB on 80–15 m, but on 12 and 10 m the two disagree (VOACAP predicts higher angles for domestic paths).
  Fewer months or hours give a table for a season or a time of day; one solar level gives a table for that part of the cycle. The ARRL
  files remain the reference where they exist.</p>
  <p><b>Library.</b> "Save to library" on a site or tower card keeps a named copy for all your projects (sites with their terrain files). "Add from library…" below the cards copies one into the current project.</p>

  <h3>2. Targets</h3>
  <p>A target is a region you want to work: a bearing and an elevation-angle file (.PRN) for that path, either an ARRL file from the Antenna Book or a table made here with VOACAP. Choosing the file sets the bearing from your site's position to a reference point in that region (shown under the bearing); "Bearings from site position" recomputes them all. The <b>map of targets</b> below the table is a great-circle map centred on your site: choose a target, click or drag on the map to set its bearing, and use the slider for its spread. Tick the bands that matter for it. Headings: the bearing plus or minus a spread, so a target is judged over several directions, not one.</p>

  <h3>3. Towers</h3>
  <p>A tower is a set of antennas at given heights. On each band, the antennas that work on that band form one HFTA stack.</p>
  <ul>
    <li><b>Location</b>: the site where the tower stands. "Every site" tries the same tower at all sites, to compare positions.</li>
    <li><b>Serves</b>: the targets this tower is judged on. A fixed European tower should serve Europe only.</li>
    <li><b>Copy to…</b>: the same antennas as a separate tower at another site.</li>
    <li><b>Switching</b>: which parts of the stack HFTA may select for each target and band.</li>
    <li>Turning radius and droop are used only by the guy check.</li>
  </ul>
  <p><b>Guy and ice check.</b> Enter guy heights and anchor distances (or the Rohn 65G preset). Pick the radial ice your engineer gives for the site. The check reports, for each turning antenna, how far the iced guy is from the drooping element tip. Negative = contact. The drawing on the card is to one scale, so guys and turning radii can be compared by eye.</p>

  <h3>Stack Designer</h3>
  <p>Searches heights for one tower over all ticked targets at once. Groups: one row per antenna type, with how many of them (Count) and the spacing rules inside the group.</p>
  <ul>
    <li><b>One row = one kind of antenna.</b> A tribander or a 5-band is one row with elements on each of its bands; four rows for 40, 20, 15 and 10 m mean four separate monobanders.</li>
    <li><b>Count</b> is how many antennas of the type; <b>up to</b> lets the search also try more, so one run compares two tribanders against three.</li>
    <li><b>Tower height</b> is the highest any antenna may go. Each group's To follows it automatically; lower one group's To (or raise its From) to hold it within a band of heights, for example when guys or a mast section limit where it can go.</li>
    <li><b>Min gap between groups</b>: the smallest distance between antennas of different groups.</li>
    <li><b>Group order</b>: force one group above the other when the physical layout is fixed.</li>
    <li><b>Respect guys of</b>: reject heights where an antenna would touch an iced guy, using that tower's guy table.</li>
    <li>Weights: a target with weight 2 counts twice. Weight 0 leaves it out.</li>
  </ul>
  <p>The table ranks layouts by overall score. Under each target, "best" marks the highest score in that column, and the red figure is how far a row is below it. The chart shows each group's score against height, so you can see why a height won and where the search stopped. <b>Use as tower</b> adds a layout to the Towers page.</p>

  <h3>Height scan</h3>
  <p>One antenna, one target, one band: score against height. The quickest way to answer "is 20 ft more worth it?".</p>

  <h3>4. Compare and 5. Report</h3>
  <p>Compare runs HFTA for every tower at its site(s), every target and band, and shows the best stack-switch setting for each. The buttons above the table choose the target.
  <b>Worldwide</b> shows all targets together (weighted mean, weights from the Stack Designer): the view for one tower that must work everywhere. Report exports the tables, the charts, and a replay pack: the exact .PRO files and settings, so any number can be reproduced in HFTA itself.</p>

  <h3>Reading the scores</h3>
  <p>FOM is HFTA's figure of merit: antenna gain at each elevation angle, weighted by how often openings arrive at that angle on that path. A difference under 0.5 dB is small; about 1 dB is where a difference starts to matter on the air. On a hill that falls away towards the target, HFTA often prefers a lower antenna than you expect: the slope already acts as height, and more height adds nulls at useful angles.</p>
  <p>Marks in the tables: <b>*</b> beside a value = a few angles of that run were filled by interpolation after the calculation core returned invalid values (the result is an estimate at those angles); <span class="neg">failed</span> = the run could not be calculated and gives no FOM; ⚠ = a spacing warning.</p>

  <h3>What HFTA cannot model</h3>
  <ul>
    <li>Generic antennas by element count, not your actual antenna.</li>
    <li>No mutual coupling between stacked antennas: close spacing is rated too well (hence the spacing warnings).</li>
    <li>Perfect power split and phasing, no feedline loss.</li>
    <li>One terrain slice per heading; ground to the side is ignored. Terrain data measures tree tops.</li>
    <li>Validated for 7–30 MHz; below 7 MHz diffraction is less reliable.</li>
  </ul>

  <h3>Accounts, sharing and privacy</h3>
  <p>On a hosted copy each user has a login and a project store of their own; nothing is shared between users. The ARRL .PRN files are copyright: keep them in your own account, and give other people the <b>shareable</b> exports (Report page), which leave the files out and list them by checksum. "Delete project" on the Report page removes a project with all its files.</p>`;
  $("#drawer").hidden = false;
}

/* ---------------------------------------------------------------- one-tower compromise */
function compForm() {
  const p = P();
  p.settings.compromise = p.settings.compromise || { site: p.sites[0]?.id, weights: {}, switching: "stackmatch", min_gap: 15, max_height: 160, guys_from_tower: "",
    groups: [{ name: "Tribander", el: { "20": 4, "15": 4, "10": 4 }, count: 3, lo: "", hi: "", step: 5, min_spacing: 30, equal_tol: 10, turning_radius: null, droop: null },
             { name: "40 m Yagi", el: { "40": 3 }, count: 2, lo: "", hi: "", step: 5, min_spacing: 60, equal_tol: "", turning_radius: null, droop: null }] };
  const f = p.settings.compromise;
  /* One-time clean-up for projects saved before From/To became optional: blank them, so Max height is the only limit. */
  if (!f.range_blanked) { f.groups.forEach(g => { g.lo = ""; g.hi = ""; }); f.range_blanked = true; save(); }
  /* "To" starts at the tower height and follows it, unless the user typed a different value for that group. */
  f.groups.forEach(g => { if (g.hi === "" || g.hi == null) g.hi = f.max_height; });
  return f;
}
function compCard() {
  const p = P(), f = compForm(), tb = towerBands(f.groups); if (!p.sites.length || !p.targets.length) { $("#compCard").innerHTML = ""; return; }
  const guyTowers = p.towers.filter(t => (t.guys?.levels || []).length);
  $("#compCard").innerHTML = `<div class="card hfta" style="margin-top:14px"><h2>Stack Designer <span class="chip good">HFTA</span></h2>
  <p class="small mute">Searches the heights of one tower for the best result over all ticked targets together. For each target and band the best stack-switch setting is used,
  as in Compare. Score per target = mean over bands; overall = weighted mean over targets. Every number is HFTA runs plus this arithmetic.</p>
  <div class="row"><label>Site<select id="cmSite">${p.sites.map(x => `<option value="${x.id}" ${x.id === f.site ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></label>
    <label>Switching<select id="cmSw"><option value="stackmatch" ${f.switching === "stackmatch" ? "selected" : ""}>Stack switch: all, pairs, singles</option><option value="full" ${f.switching === "full" ? "selected" : ""}>Whole stack only</option><option value="all" ${f.switching === "all" ? "selected" : ""}>Every combination</option></select></label>
    <label>Tower height (ft)<input type="number" id="cmMax" value="${f.max_height}" title="Highest height any antenna may have. Every group's To (ft) follows it unless you change that group's To"></label>
    <label>Min gap between groups (ft)<input type="number" id="cmGap" value="${f.min_gap}"></label>
    <label>Group order<select id="cmOrder" title="Which group is above which. The list order of the groups below is used.">
      <option value="any" ${(f.order || "any") === "any" ? "selected" : ""}>Any (HFTA decides)</option>
      <option value="first_top" ${f.order === "first_top" ? "selected" : ""}>As listed, first group on top</option>
      <option value="first_bottom" ${f.order === "first_bottom" ? "selected" : ""}>As listed, first group at the bottom</option></select></label>
    <label>Respect guys of<select id="cmGuy"><option value="">no guy check</option>${guyTowers.map(t => `<option value="${t.id}" ${t.id === f.guys_from_tower ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select></label></div>
  <h3 class="small" style="margin:12px 0 4px">Targets and weights</h3>
  <div class="row">${p.targets.map(t => `<label style="flex-direction:row;align-items:center;gap:4px"><input type="checkbox" data-ct="${t.id}" ${f.weights[t.id] !== 0 ? "checked" : ""}>${esc(t.name)}
    <input type="number" class="s" step="0.5" min="0" data-cw="${t.id}" value="${f.weights[t.id] ?? 1}" title="Weight"></label>`).join("")}</div>
  <h3 class="small" style="margin:12px 0 4px">Antenna groups</h3>
  <p class="small mute" style="margin:0 0 4px">One row = one kind of antenna; Count = how many of it. Elements on several bands in the same row = a tribander or multiband antenna (one boom, one height for all its bands).
  Separate rows = separate antennas (monobanders). Use "Band set…" to fill a row for a common antenna, then adjust the element counts.</p>
  <div class="tbl"><table><tr><th>Name</th>${tb.map(b => `<th>${b} m</th>`).join("")}<th class="n">Count</th><th class="n" title="Optional. Also try more antennas of this type, up to this number; the result ranks all counts together">up to</th><th class="n" title="Optional lower limit for this group. Empty = from one step above ground">From (ft)</th><th class="n" title="Highest height for this group. Follows the tower height; lower it to keep this group below a guy, a mast section or another group">To (ft)</th><th class="n">Step</th><th class="n">Min spacing (ft)</th><th class="n">Equal ± (ft)</th><th class="n">Turning radius (ft)</th><th class="n">Droop (ft)</th><th></th></tr>
  ${f.groups.map((g, j) => `<tr><td><input class="w" style="width:110px" data-gn="${j}" value="${esc(g.name || "")}"><br>${bandSetSelect(`data-gset="${j}"`)}</td>
    ${tb.map(b => `<td>${elSelect(`data-ge="${j}" data-band="${b}"`, b, (g.el || {})[b])}</td>`).join("")}
    ${["count", "count_max", "lo", "hi", "step", "min_spacing", "equal_tol", "turning_radius", "droop"].map(k => `<td class="n"><input type="number" class="s" data-gf="${j}" data-key="${k}" value="${g[k] ?? ""}" ${k === "equal_tol" ? 'placeholder="any"' : k === "hi" ? `placeholder="${f.max_height}"` : k === "lo" ? `placeholder="${g.step || 5}"` : k === "count_max" ? 'placeholder="–"' : ["turning_radius", "droop"].includes(k) ? 'placeholder="–"' : ""}></td>`).join("")}
    <td><button class="danger small" data-gx="${j}">Remove</button></td></tr>`).join("")}</table></div>
  <p class="small mute" style="margin:4px 0 0">Elements per band as in HFTA. Turning radius and droop are needed only with the guy check.</p>
  ${warnList(compFormWarnings(f), "Spacing rules: no warnings.")}
  <div class="row" style="margin-top:8px"><button class="ghost small" id="cmAddG">Add group</button><button id="cmGo">Design the stack</button></div>
  <div class="prog" hidden id="cmProg"><i></i></div><div id="cmOut"></div></div>`;
  const sv = () => save();
  $("#cmSite").onchange = e => { f.site = e.target.value; sv(); }; $("#cmSw").onchange = e => { f.switching = e.target.value; sv(); };
  $("#cmMax").onchange = e => { const old = Number(f.max_height); f.max_height = Number(e.target.value);
    f.groups.forEach(g => { if (g.hi === "" || g.hi == null || Number(g.hi) === old || Number(g.hi) > f.max_height) g.hi = f.max_height; }); sv(); compCard(); }; $("#cmGap").onchange = e => { f.min_gap = Number(e.target.value); sv(); compCard(); };
  $("#cmGuy").onchange = e => { f.guys_from_tower = e.target.value; sv(); };
  $("#cmOrder").onchange = e => { f.order = e.target.value; sv(); };
  $$("[data-ct]").forEach(cb => cb.onchange = () => { f.weights[cb.dataset.ct] = cb.checked ? Number($(`[data-cw="${cb.dataset.ct}"]`).value || 1) : 0; sv(); });
  $$("[data-cw]").forEach(inp => inp.onchange = () => { f.weights[inp.dataset.cw] = Number(inp.value); $(`[data-ct="${inp.dataset.cw}"]`).checked = Number(inp.value) > 0; sv(); });
  $$("[data-gn]").forEach(inp => inp.onchange = () => { f.groups[inp.dataset.gn].name = inp.value; sv(); });
  $$("[data-gset]").forEach(sel => sel.onchange = () => { const g = f.groups[sel.dataset.gset]; g.el = applyBandSet(g.el, sel.value);
    if (!g.name && sel.value) g.name = sel.selectedOptions[0].text; sv(); compCard(); });
  $$("[data-ge]").forEach(sel => sel.onchange = () => { const g = f.groups[sel.dataset.ge]; g.el = g.el || {}; if (sel.value) g.el[sel.dataset.band] = Number(sel.value); else delete g.el[sel.dataset.band]; sv(); compCard(); });
  $$("[data-gf]").forEach(inp => inp.onchange = () => { f.groups[inp.dataset.gf][inp.dataset.key] = inp.value === "" ? (["turning_radius", "droop", "count_max"].includes(inp.dataset.key) ? null : "") : Number(inp.value); sv(); compCard(); });
  $$("[data-gx]").forEach(b => b.onclick = () => { f.groups.splice(Number(b.dataset.gx), 1); sv(); compCard(); });
  $("#cmAddG").onclick = () => { f.groups.push({ name: "", el: {}, count: 1, lo: "", hi: f.max_height, step: 5, min_spacing: 30, equal_tol: "", turning_radius: null, droop: null }); sv(); compCard(); };
  $("#cmGo").onclick = async () => {
    await save(true);
    const targets = p.targets.filter(t => f.weights[t.id] !== 0).map(t => t.id);
    if (!targets.length) return toast("Tick at least one target");
    const body = { site: f.site, targets, weights: Object.fromEntries(targets.map(t => [t, f.weights[t] ?? 1])), groups: f.groups, switching: f.switching,
      min_gap: f.min_gap, max_height: f.max_height, guys_from_tower: f.guys_from_tower || null, order: f.order || "any", min_spacing: 30, top: 25 };
    $("#cmOut").innerHTML = `<p class="note small">Searching… The earlier result is hidden until this search finishes. Large searches take several minutes.</p>`;
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
  for (const g of f.groups) {
    if (g.hi === "" || g.hi == null) continue;
    if (Number(g.hi) > Number(f.max_height)) out.push({ level: "amber", text: `${g.name || describe(g)}: "To" is ${g.hi} ft but the tower height is ${f.max_height} ft, so the search stops at ${f.max_height} ft. Raise Max height to search higher.` });
    else if (Number(g.hi) < Number(f.max_height)) out.push({ level: "amber", text: `${g.name || describe(g)}: searched only up to ${g.hi} ft (its To), not to the tower height ${f.max_height} ft.` });
  }
  if (f.groups.length > 1 && Number(f.min_gap) < r.gap_amber_ft) out.push({ level: Number(f.min_gap) < r.gap_red_ft ? "red" : "amber", text: `Minimum gap between groups ${f.min_gap} ft is below ${r.gap_amber_ft} ft: antennas on different bands may interact; HFTA does not model this.` });
  return out;
}
function compResult(r) {
  const p = P(); r.targets.forEach(t => { const cur = p.targets.find(x => x.id === t.id); if (cur) t.name = cur.name; });
  const lay = l => l.map((g, i) => `${r.groups[i].name || r.groups[i].model} ${g.join(" / ")}`).join("; ");
  const q = r.request || {}, nm = id => p.sites.find(x => x.id === id)?.name || "?", tn = id => p.targets.find(x => x.id === id)?.name || "?";
  const inputs = !r.request ? "" : `Site ${nm(q.site)}; tower height ${q.max_height} ft; min gap ${q.min_gap} ft; order ${q.order || "any"}; ${q.guys_from_tower ? "guy check on" : "no guy check"}; switching ${q.switching}.
    Targets: ${(q.targets || []).map(t => `${tn(t)}${(q.weights || {})[t] !== 1 ? " ×" + q.weights[t] : ""}`).join(", ")}.
    Groups: ${(q.groups || []).map(g => `${esc(g.name || "?")} ×${g.count}${g.count_max ? "–" + g.count_max : ""} (${bandsOf(g).join("/")} m; ${g.lo || "–"} to ${g.hi || q.max_height} ft, step ${g.step}, spacing ≥ ${g.min_spacing})`).join("; ")}.`;
  r.inputs_text = inputs.replace(/\s+/g, " ");
  const st = r.stats, n = v => Number(v).toLocaleString();
  const summary = !st ? "" : `<div class="note small"><b>Search summary.</b> ${n(st.hfta_runs)} HFTA runs (each one HFTA calculation of an elevation pattern:
    ${st.stages.map(x => `${esc(x.stage)} ${n(x.runs)}`).join("; ")}). ${n(st.fom_evaluations)} FOM evaluations against the .PRN files.
    Layouts scored per group: ${st.group_layouts.map(g => `${esc(g.name)} ${n(g.layouts)}`).join(", ")}.
    ${n(st.combinations_checked)} combinations of groups examined.
    ${st.complete === undefined ? "" : st.complete
      ? (st.coarse_grid
          ? `<b>Best found.</b> The height grid was too large, so it was searched coarse first and then fine around the best coarse layouts; a layout between them could be slightly better.`
          : `<b>Complete:</b> no other layout on this height grid scores higher. Combinations that could not beat the best were skipped by calculation, not by guess.`)
      : `<b>Search limit reached:</b> best found, not proven best. Narrow the height ranges or use a larger step.`}
    ${st.failed_runs ? `<span class="neg">${n(st.failed_runs)} run(s) failed in the calculation core; ${n(st.layouts_dropped)} layout(s) without a complete score were left out.</span>` : ""}
    ${st.filled_runs ? `${n(st.filled_runs)} run(s) had a few invalid angles filled by interpolation.` : ""}
    Time ${st.seconds < 90 ? st.seconds + " s" : (st.seconds / 60).toFixed(1) + " min"}.
    <span class="mute">Each run is one OpenHFTA calculation, the same as one press of Calculate in the original HFTA.</span></div>`;
  /* Does the shown result match the form as it is now? */
  const f = compForm(), diffs = [];
  if (q.site !== f.site) diffs.push("site");
  if (Number(q.max_height) !== Number(f.max_height)) diffs.push(`tower height (result ${q.max_height} ft, form ${f.max_height} ft)`);
  if (Number(q.min_gap) !== Number(f.min_gap)) diffs.push("min gap");
  if ((q.order || "any") !== (f.order || "any")) diffs.push("group order");
  if ((q.guys_from_tower || "") !== (f.guys_from_tower || "")) diffs.push("guy check");
  if (q.switching !== f.switching) diffs.push("switching");
  const gkey = g => JSON.stringify([g.name, g.el, Number(g.count), g.count_max || null, String(g.lo ?? ""), String(g.hi === "" || g.hi == null ? q.max_height : g.hi), Number(g.step), Number(g.min_spacing), String(g.equal_tol ?? "")]);
  const fkey = g => JSON.stringify([g.name, g.el, Number(g.count), g.count_max || null, String(g.lo ?? ""), String(g.hi === "" || g.hi == null ? f.max_height : g.hi), Number(g.step), Number(g.min_spacing), String(g.equal_tol ?? "")]);
  if (r.request && ((q.groups || []).length !== f.groups.length || (q.groups || []).some((g, i) => gkey(g) !== fkey(f.groups[i])))) diffs.push("antenna groups");
  const wNow = Object.fromEntries(p.targets.filter(t => f.weights[t.id] !== 0).map(t => [t.id, f.weights[t.id] ?? 1]));
  if (r.request && JSON.stringify(Object.entries(q.weights || {}).sort()) !== JSON.stringify(Object.entries(wNow).sort())) diffs.push("targets or weights");
  const stale = r.request && diffs.length ? `<div class="note" style="border-left-color:#d9822b"><b>This result is from an earlier search with different inputs</b> (${esc(diffs.join(", "))}).
    Press <b>Design the stack</b> to search with the inputs above.</div>` : "";
  $("#cmOut").innerHTML = `${stale}${summary}${inputs ? `<div class="note small"><b>Inputs of this run</b> (${esc(r.stamp || "")}): ${esc(inputs)}<br>A different result after a new run means one of these changed.</div>` : ""}
  <p class="small mute" style="margin-top:10px">Spacing column: hover a chip for details. Rows are ranked by HFTA only; a warning means HFTA is probably optimistic for that layout.
    Best ${r.evaluated} layouts shown, from ${r.runs} HFTA runs (${esc(r.stamp || "")}).
    Loss = difference from the best possible for that target alone (shown in the last row). Heights in ft.</p>
  <div class="tbl"><table><tr><th>#</th><th>Layout</th><th>Spacing</th><th class="n">Overall</th>${r.targets.map(t => `<th class="n">${esc(t.name)} <span class="mute">(w ${r.weights[t.id]})</span></th>`).join("")}<th></th></tr>
  ${r.rows.map((x, k) => { const sw = worstOf(x.spacing || []); return `<tr><td>${k + 1}</td><td>${esc(lay(x.layout))}</td>
    <td>${sw ? `<span class="chip ${sw === "red" ? "bad" : "warn"}" title="${esc((x.spacing || []).map(w => w.text).join("\n"))}">${sw === "red" ? "Too close" : "Close"}</span>` : `<span class="small mute">OK</span>`}</td>
    <td class="n"><b>${fmt(x.overall)}</b></td>
    ${r.targets.map(t => `<td class="n">${x.loss[t.id] >= 0 ? `<b>${fmt(x.targets[t.id])}</b>` : fmt(x.targets[t.id])}<br><span class="small ${x.loss[t.id] < -1 ? "neg" : x.loss[t.id] < -0.3 ? "amb" : "mute"}">${x.loss[t.id] >= 0 ? "best" : fmt(x.loss[t.id])}</span></td>`).join("")}
    <td><button class="ghost small" data-apply="${k}">Use as tower</button></td></tr>`; }).join("")}
  <tr><td></td><td class="mute">Best for each target alone</td><td></td><td></td>${r.targets.map(t => `<td class="n mute">${fmt(r.own_best[t.id])}<br><span class="small">${esc(lay(r.own_layout[t.id]))}</span></td>`).join("")}<td></td></tr></table></div>
  ${r.curves?.length ? `<h3 class="small" style="margin:14px 0 4px">Score against height, by group</h3>
  <p class="small mute" style="margin:0 0 6px">Why a height was chosen. Solid line = overall (weighted over targets); thin lines = each target. For a stack, the best layout with its top antenna at that height.
  Rules between groups (gap, order, guys) can move the chosen height away from a group's own peak.</p>
  <p class="small" style="margin:0 0 6px"><b>Heights searched:</b> ${r.curves.map(c => `${esc(c.name)} ${Math.min(...c.heights)}–${Math.max(...c.heights)} ft`).join("; ")}.
  The limit for each group is its own To (ft), which follows the tower height unless you changed it. Heights outside this range were not calculated.</p>
  <div class="row" style="align-items:center"><label>Group<select id="cmCurveSel">${r.curves.map((c, i) => `<option value="${i}">${esc(c.name)}</option>`).join("")}</select></label></div>
  <div id="cmCurve" class="plot sm"></div>` : ""}`;
  if (r.curves?.length) {
    const draw = () => {
      const c = r.curves[Number($("#cmCurveSel").value)];
      const tr = [{ x: c.heights, y: c.overall, name: "Overall", mode: "lines+markers", line: { color: css("--ink"), width: 3 } }];
      r.targets.forEach((t, i) => tr.push({ x: c.heights, y: c.targets[t.id], name: t.name, mode: "lines", line: { color: PAL[i % 8], width: 1 } }));
      Plotly.react("cmCurve", tr, plotLayout({ title: { text: `${c.name}: HFTA score (FOM) against height`, font: { size: 13 } }, margin: { l: 50, r: 16, t: 28, b: 80 }, legend: { orientation: "h", y: -0.4 },
        /* Axis spans the user's own range (lowest From to Max height), so a search that stops early shows as an empty stretch. */
        xaxis: { title: { text: "height of the (top) antenna, ft", standoff: 6 }, gridcolor: css("--line"), range: [0, Number(compForm().max_height)] },
        yaxis: { title: "FOM", gridcolor: css("--line") } }), { displaylogo: false, responsive: true });
    };
    $("#cmCurveSel").onchange = draw; draw();
  }
  $$("[data-apply]").forEach(b => b.onclick = async () => {
    const x = r.rows[Number(b.dataset.apply)], f = compForm();
    const ants = x.layout.flatMap((hs, i) => hs.map(h => ({ h, el: { ...r.groups[i].el }, turning_radius: r.groups[i].turning_radius ?? null, droop: r.groups[i].droop ?? null })));
    const g = p.towers.find(t => t.id === f.guys_from_tower);
    p.towers.push({ id: uid("w"), name: `Stack ${lay(x.layout)}`.slice(0, 60), site: f.site || null, design: `Stack Designer row ${Number(b.dataset.apply) + 1}, overall ${fmt(x.overall)}. ${r.inputs_text || ""}`, switching: f.switching, height_ft: Math.max(...x.layout.flat()), targets: r.targets.map(t => t.id),
      antennas: ants, guys: g ? JSON.parse(JSON.stringify(g.guys)) : { levels: [], ice_in: 1.0, margin_ft: 2.0 } });
    await save(true); toast("Added as a new tower at the Designer's site. In Compare, press Evaluate to include it.", 6000); rTowers();
  });
}
