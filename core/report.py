"""Self-contained HTML report (no external files): inputs, comparison tables, charts as inline SVG,
guy check, and how to reproduce every number in HFTA."""
from __future__ import annotations
import datetime, html, io
from collections import defaultdict
from . import antennas as A, project as P, terrain as TR
from .evaluate import total

CSS = """
:root{--ink:#1d2733;--mute:#5b6b7c;--line:#d8e0e8;--accent:#1f5f8b;--good:#2e7d4f;--bad:#b23b3b;--bg:#fff;--chip:#eef3f8}
body{font:15px/1.5 "Source Sans 3","Segoe UI",Arial,sans-serif;color:var(--ink);background:var(--bg);margin:0;padding:24px 20px}
main{max-width:1060px;margin:0 auto}h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:32px 0 8px;border-bottom:2px solid var(--line);padding-bottom:4px}
h3{font-size:16px;margin:18px 0 6px}.mute{color:var(--mute)}.chip{display:inline-block;background:var(--chip);border-radius:4px;padding:1px 8px;margin-right:6px;font-size:13px}
table{border-collapse:collapse;width:100%;margin:6px 0 14px;font-size:14px;font-variant-numeric:tabular-nums}
th,td{border:1px solid var(--line);padding:4px 8px;text-align:left}th{background:#f3f6f9}td.n{text-align:right}
td.best{font-weight:700;color:var(--good)}td.bad{color:var(--bad);font-weight:600}.wrap{overflow-x:auto}
.sp.red,.warnl .red b{color:#b33a3a}.sp.amber,.warnl .amber b{color:#b26b00}.warnl{margin:4px 0 12px;padding-left:18px}.warnl li{margin:2px 0}
.note{border-left:4px solid var(--accent);background:#f5f9fc;padding:8px 12px;margin:10px 0}
svg{max-width:100%;height:auto}@media print{h2{break-after:avoid}table{break-inside:avoid}}
"""

def _svg_elevation_patterns(proj, slug, target, band, cells, res, sites, towers):
    """OpenHFTA-style gain-vs-elevation curves, with weighted FOM in the legend.
    One real terrain heading nearest the target's centre is shown per site/tower.
    The complete HFTA run series remains in the replay pack.
    """
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .evaluate import band_freq
    import engine

    angle = float(target["heading"])
    angular_gap = lambda v: abs((float(v) - angle + 180) % 360 - 180)
    traces = []
    for c in cells:
        if c["band"] != band or c.get("best") is None:
            continue
        opts = c["options"][c["best"]].get("az") or []
        if not opts:
            continue
        az = min(opts, key=lambda x: angular_gap(x["az"]))
        gain = (res.get("patterns") or {}).get(az["run"])
        if gain is None or len(gain) != len(engine.ANGLES):
            continue
        traces.append((c, az, gain))
    if not traces:
        return ""

    fig, ax = plt.subplots(figsize=(9.5, 3.7), dpi=100)
    palette = ["#1f5f8b", "#d9822b", "#2e7d4f", "#8e44ad", "#b23b3b", "#5b6b7c", "#16a085", "#c0a000"]
    for i, (c, az, gain) in enumerate(traces):
        label = (f"{sites[c['site']]['name']} / {towers[c['tower']]['name']}: "
                 f"FOM {float(az.get('fom') if az.get('fom') is not None else c['hfta_fom']):.1f} dB (heading {az['az']:g}°)")
        ax.plot(engine.ANGLES, gain, linewidth=1.8, color=palette[i % len(palette)], label=label)

    ax.set_xlim(0, 35)
    vals = [float(g) for _, _, curve in traces for g in curve[2:] if np.isfinite(g)]
    if vals:
        ax.set_ylim(min(vals) - 2, max(vals) + 2)
    ax.set_xlabel("Elevation angle (°)")
    ax.set_ylabel("Gain (dBi)")
    ax.set_title(f"{target['name']}: {band} m · terrain-modified gain")
    ax.grid(alpha=0.28)

    try:
        aoa = engine.parse_aoa(P.prn_file(slug, target["prn"]).read_text(errors="ignore"), band_freq(proj, band))
    except (OSError, ValueError, KeyError):
        aoa = None
    if aoa:
        ax2 = ax.twinx()
        x = sorted(float(x) for x in aoa if 0 <= float(x) <= 35)
        ax2.bar(x, [100 * aoa[v] for v in x], width=0.35, color=palette[3], alpha=0.2)
        ax2.set_ylabel("Arrival-angle probability (%)")
        ax2.set_ylim(bottom=0)

    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=2, fontsize=7, frameon=False)
    fig.tight_layout()
    out = io.StringIO()
    fig.savefig(out, format="svg", bbox_inches="tight")
    plt.close(fig)
    value = out.getvalue()
    return value[value.find("<svg"):]

def html_report(proj, slug, res, layers_on, guy_rows=None) -> str:
    e = html.escape; S = {s["id"]: s for s in proj["sites"]}; TW = {t["id"]: t for t in proj["towers"]}; TG = {t["id"]: t for t in proj["targets"]}
    from . import spacing as SP
    from .evaluate import band_freq
    on = []
    eng = res.get("engine") or {}
    lay_txt = ("Calculated with OpenHFTA, an open-source implementation of the HFTA method (checked against original-HFTA output "
               "within 0.1 dB on the reference set; see README). Spacing warnings and the guy check are notes only; they never change a number.")
    if res.get("n_filled"): lay_txt += f" {res['n_filled']} run(s) had a few invalid angles from the core, filled by interpolation (marked in the replay pack)."
    if res.get("n_failed"): lay_txt += f" {res['n_failed']} run(s) failed and give no result."
    st = proj["settings"]; o = []; spr = st["spacing"]
    o.append(f"<main><h1>{e(proj['name'])}</h1><p class=mute>HFTA Stack Planner report, {datetime.date.today()}. "
             f"Results computed {e(res['stamp'])} from {res['n_runs']} OpenHFTA runs. Engine: {e(eng.get('name', 'unknown'))} "
             f"commit {e(str(eng.get('commit', 'unknown'))[:12])}, library {e(str(eng.get('library_sha256', 'unknown'))[:12])}.</p><div class=note>{e(lay_txt)}</div>")
    o.append("<h2>Important safety and performance limitations</h2>"
             "<p><strong>Comparative RF planning only: not a tower or antenna structural design, engineered clearance "
             "assessment, safety certification, or guarantee of radio performance.</strong> HFTA results depend on "
             "simplified models and user-selected input data; coupling, loss, propagation and terrain uncertainty "
             "can change actual outcomes. Guy-wire, ice and spacing checks are simplified guidance only; they "
             "cannot determine tower, guy, foundation or anchor strength, wind/ice safety, or real-world "
             "clearance. Do not build, modify, climb or operate an installation based on this study alone. "
             "Verify inputs independently and obtain qualified engineering review for construction and safety "
             "decisions. Software supplied AS IS, without warranty, under the MIT license. See the full "
             "DISCLAIMER.md in the HFTA Stack Planner distribution.</p>")
    o.append("<h2>Inputs</h2><h3>Sites</h3><table><tr><th>Site</th><th>Position</th><th>Terrain source</th><th>Profiles</th><th>Notes</th></tr>")
    for s in proj["sites"]:
        n = len(TR.profile_index(P.site_dir(slug, s["id"])))
        pos = f'{s["lat"]:.5f}, {s["lon"]:.5f}' if s.get("lat") not in (None, "") else "-"
        o.append(f"<tr><td>{e(s['name'])}</td><td>{pos}</td><td>{e(str(s.get('terrain', {}).get('source', '-')))}</td><td class=n>{n}</td><td>{e(s.get('notes', ''))}</td></tr>")
    o.append("</table><h3>Targets</h3><table><tr><th>Target</th><th>Elevation file</th><th>Heading</th><th>Headings used (weight)</th><th>Bands</th></tr>")
    for t in proj["targets"]:
        hd = ", ".join(f"{(t['heading'] + of) % 360:g}° ({w:g})" for of, w in zip(t["offsets"], t["weights"]))
        o.append(f"<tr><td>{e(t['name'])}</td><td>{e(t['prn'])}</td><td class=n>{t['heading']:g}°</td><td>{hd}</td><td>{', '.join(t['bands'])}</td></tr>")
    o.append("</table><h3>Towers</h3>")
    for t in proj["towers"]:
        serves = ", ".join(TG[x]["name"] for x in (t["targets"] if t.get("targets") is not None else TG) if x in TG) or "none"
        o.append(f"<p><b>{e(t['name'])}</b> <span class=chip>serves: {e(serves)}</span><span class=chip>switching: {e(t.get('switching', 'stackmatch'))}</span></p><table><tr><th>Height (ft)</th><th>Bands and HFTA type</th></tr>")
        for a in sorted(t["antennas"], key=lambda a: -a["h"]):
            btxt = ", ".join(f"{b} m ({A.hfta_type(a, b)})" for b in A.bands_of(a))
            o.append(f"<tr><td class=n>{a['h']:g}</td><td>{btxt}</td></tr>")
        o.append("</table>")
        wl = SP.check(t["antennas"], lambda b: band_freq(proj, b), spr)
        if wl:
            o.append("<ul class=warnl>" + "".join(f"<li class={w['level']}><b>{'TOO CLOSE' if w['level'] == 'red' else 'CLOSE'}</b> {e(w['text'])}</li>" for w in wl) + "</ul>")
        else:
            o.append("<p class=mute>Spacing: no warnings.</p>")
    o.append(f"<p class=mute>Spacing warnings (HFTA has no mutual coupling): stack spacing red below {spr['red_wl']} wavelength, amber below {spr['amber_wl']}; "
             f"gap between antennas on different bands red below {spr['gap_red_ft']:g} ft, amber below {spr['gap_amber_ft']:g} ft. "
             "These limits are guidance from one NEC-2 example (two Yagis: 0.22 wavelength lost 2.2 dB of stacking gain, 0.43 wavelength 0.7 dB), "
             "not a general rule.</p>")
    o.append(f"<p class=mute>Ground: {e(st['soil'])} (dielectric {st['epsr']}, conductivity {st['sigma']} S/m). Diffraction {'on' if st['diffraction'] else 'off'}.</p>")
    # comparison
    o.append("<h2>Comparison</h2><p>FOM in dB, higher is better. Differences of 0.3 dB or less are not significant. "
             "<b>Bold green</b> = best in its column.</p>")
    by_t = defaultdict(list)
    for c in res["cells"]: by_t[c["target"]].append(c)
    for tid, cells in by_t.items():
        t = TG[tid]; bands = [b for b in A.BANDS if any(c["band"] == b for c in cells)]
        rows = sorted({(c["site"], c["tower"]) for c in cells}, key=lambda k: (S[k[0]]["name"], TW[k[1]]["name"]))
        val = {(c["site"], c["tower"], c["band"]): c for c in cells}
        best = {b: max([total(val[(s, w, b)], layers_on) for s, w in rows if (s, w, b) in val and val[(s, w, b)].get("hfta_fom") is not None] or [None], key=lambda x: -1e9 if x is None else x) for b in bands}
        o.append(f"<h3>{e(t['name'])} <span class=mute>({e(t['prn'])}, {t['heading']:g}°)</span></h3><div class=wrap><table><tr><th>Site</th><th>Tower</th>")
        o += [f"<th>{b} m</th><th class=mute>switch</th>" for b in bands]; o.append("</tr>")
        series, values = [], {}
        for s, w in rows:
            lab = f"{S[s]['name']} / {TW[w]['name']}"; series.append(lab); values[lab] = {}
            o.append(f"<tr><td>{e(S[s]['name'])}</td><td>{e(TW[w]['name'])}</td>")
            for b in bands:
                c = val.get((s, w, b))
                if not c or c.get("hfta_fom") is None:
                    o.append(f"<td class=mute colspan=2>{e('; '.join(c['issues'])) if c else '-'}</td>"); continue
                v = total(c, layers_on); values[lab][b] = v
                bo = c["options"][c["best"]]["heights"]; cls = "n best" if best[b] is not None and abs(v - best[b]) < 0.005 else "n"
                extra = f"<br><span class=mute>HFTA {c['hfta_fom']:.2f}</span>" if on else ""
                sw = SP.worst(c.get("spacing", []))
                if sw:
                    tip = e(" | ".join(w["text"] for w in c["spacing"]))
                    extra += f" <span class='sp {sw}' title='{tip}'>&#9888;</span>"
                o.append(f"<td class='{cls}'>{v:.2f}{extra}</td><td class=mute>{' / '.join(f'{h:g}' for h in bo)}</td>")
            o.append("</tr>")
        o.append("</table></div><p class=mute>&#9888; = spacing warning on that band (see Towers above).</p>")
        if bands and series:
            o.append("<p class=mute>Elevation curves: the gain at each 0.25-degree elevation increment, from a terrain heading nearest the target centre. "
                     "FOM in the legend is averaged over the target's selected headings and is not the maximum plotted gain. "
                     "FOM summaries remain in the table above; faded bars represent arrival-angle probabilities.</p>")
            for band in bands:
                svg = _svg_elevation_patterns(proj, slug, t, band, cells, res, S, TW)
                if svg:
                    o.append(svg)
    if guy_rows:
        o.append("<h2>Guy clearance (not part of HFTA; applies to antennas that turn)</h2>")
        for tname, rows in guy_rows.items():
            tw = next(t for t in proj["towers"] if t["name"] == tname); g = tw.get("guys", {})
            lv = ", ".join(f"{l['h']:g} ft to {l['r']:g} ft anchors ({e(l['wire'])})" for l in g.get("levels", []))
            o.append(f"<h3>{e(tname)}</h3><p class=mute>Guys: {lv}. Radial ice {g.get('ice_in', 1.0)} in, hardware margin {g.get('margin_ft', 2.0)} ft.</p>"
                     "<table><tr><th>Antenna</th><th>Height (ft)</th><th>Turning radius (ft)</th><th>Clearance (ft)</th><th>Limited by</th></tr>")
            for r in sorted(rows, key=lambda r: -r["h"]):
                cl = r["clearance"]; cls = "n bad" if cl is not None and cl < 0 else "n"
                o.append(f"<tr><td>{e(r['name'])}</td><td class=n>{r['h']:g}</td><td class=n>{r['turning_radius'] or '-'}</td><td class='{cls}'>{'-' if cl is None else f'{cl:.1f}'}</td><td>{e(r['limit'])}</td></tr>")
            o.append("</table>")
    o.append("<h2>How to reproduce in HFTA</h2><p>Each FOM above is either one HFTA run or arithmetic on HFTA runs: the weighted mean over the target's "
             "headings, and the best of the tower's switch settings. Export the <b>HFTA replay pack</b> from the planner: it holds every terrain and "
             "elevation file used, every run with its exact HFTA inputs and FOM, the expected elevation pattern of each run (HFTA OUT.PRN layout), and "
             "the step-by-step combination of runs into each result.</p>"
             "<p class=mute>Calculations by OpenHFTA (RioDXGroup, https://github.com/RioDXGroup/openhfta), used unchanged. HFTA by R. Dean Straw, N6BV, published with The ARRL Antenna Book. ARRL elevation-angle files are copyright ARRL and supplied by the user. Not affiliated with or endorsed by ARRL or the OpenHFTA authors.</p></main>")
    return f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>{e(proj['name'])} - HFTA study</title><style>{CSS}</style></head><body>{''.join(o)}</body></html>"
