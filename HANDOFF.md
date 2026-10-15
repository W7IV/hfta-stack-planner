# HFTA Stack Planner — status and handoff

Updated 15 October 2026. Read this first when you pick the project up again (person or AI assistant).
The README describes the program; this file says where it stands, what is open and what was decided.

## Where things are
| Item | Location |
|---|---|
| Code | github.com/W7IV/hfta-stack-planner, branch `main` (last change: facdd3d, 14 Oct) |
| Hosted test copy | Railway: hfta-stack-planner-production.up.railway.app (auto-deploys `main`; accounts per user) |
| Release candidate | Tag `v1.0.0-rc2`: Windows zip on GitHub Releases, Docker image `ghcr.io/w7iv/hfta-stack-planner` |
| Calculation core | OpenHFTA (RioDXGroup) commit 7d62e863, used unchanged; `tests/test_hfta_match.py` checks 560 gains against original HFTA |
| Station study (private) | github.com/W7IV/canaan-station: `Canaan_Towers_Summary.md` holds the current Canaan layouts |
| Laptop clones | `C:\Users\Paul\Documents\GitHub\hfta-stack-planner` and `...\canaan-station` |

Rules that do not change: every number must be reproducible in the original HFTA; ARRL .PRN files are copyright
and never go into the repository or a shareable export; extras beyond HFTA (spacing, guys, 6 m positions) never
change a FOM and are marked "not part of HFTA".

## Open tasks
Priority order. "Paul" = needs the owner; the rest can be done by whoever works on the code.

1. **Railway outage, 14 Oct ("Application failed to respond").** Paul: send the deploy log, or press Restart.
   The code starts cleanly under gunicorn with Railway's settings, so the likely cause is a crash or an
   out-of-memory kill during a large job. If the log shows a kill: set `HFTA_WORKERS=2` on Railway and consider
   a default cap for hosted copies in `app.py`.
2. **Release v1.0.0.** After the outage is settled: Paul tests the rc2 Windows zip on the laptop (start, fetch
   terrain, VOACAP table, Evaluate); Paul sets the GHCR package to public; then tag `v1.0.0` from the laptop
   (the cloud session cannot push tags or create releases).
3. **Paul's final-check list** (from 12 Oct): accounts test with a second user; Designer re-run on a fresh
   project; Worldwide equality check; exports (HTML, Excel, CSV, replay pack) opened and read; two-window save
   conflict; project delete; one result checked in the original HFTA. HFTA itself needs `COMDLG32.OCX`
   registered on Windows 11 (see the chat of 14 Oct).
4. **Existing projects:** press "Bearings from site position" once in the 40M-ROT project (renames the targets
   that were all called "Africa"); tick 40 m (and 80 m) on targets made before 13 Oct.
5. **Designer and hosted memory:** the time budget (`STAGE_SECONDS` in core/compromise.py, 240 s per stage)
   assumes the worker count Railway reports; check `sc.workers` against real CPU on Railway.
6. **Possible next features** (not started; ask Paul before doing any):
   - VOACAP tables for all regions in one action (today one region per run), so 80 m can use one method throughout.
   - Contest-log weighting of targets (Paul's original idea: weight by where the logs come from).
   - K6TU tie-in: fetch his one-degree terrain sets by latitude/longitude (Paul to ask K6TU).
   - NEC check for close spacings (40 m against tribanders, dipole against 40 m) — outside HFTA, so a separate tool.
   - Weights in the Targets step as well as in the Designer form (today the Designer form is the only place).

## Done in this period (11–14 Oct), for reference
- Review findings F01–F22 fixed; accounts and per-user stores; CSP and non-root container; project revisions.
- VOACAP angle tables for any origin; worldwide terrain (USGS 3DEP in the US, AWS Terrain Tiles elsewhere);
  far-horizon check; optional 10 km profiles.
- Windows package and Docker image built by GitHub Actions on a `v*` tag.
- Run identity includes the terrain file's SHA-256; a heading with two profile files uses the newest and the site
  card warns (this found a wrong terrain set in Paul's Canaan EU site).
- HFTA's 1–35° limit enforced: a target whose table is mostly above 35° (NVIS) is not scored.
- Cancel on every job; Designer budget by measured time, refining 20 → 10 → 5 ft.
- Targets: name follows the file, 40–10 m ticked by default. Towers: empty new rows, "Add same as top",
  6 m column (position only, no FOM).
- Usability pass: coloured card bars (blue inputs, green HFTA, amber checks), grouped site controls, step ticks,
  two-line page introductions, switch columns on request, fixed-width tower drawing, pinned Remove column.

## Decisions worth remembering
- Soil choice changes HFTA FOM by under 0.2 dB (measured); K6STI ground constants are not used.
- Africa 80 m in the ARRL W1-MA file has only two samples (3° and 4°); use a VOACAP table for 80 m there.
- 6 m is never scored: HFTA stops at 30 MHz and no arrival-angle table covers 50 MHz.
- The hosted copy is for testing and sharing with a few people; the main way to run it is locally
  (Windows zip or Docker).
