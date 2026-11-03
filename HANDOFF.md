# HFTA Stack Planner — status and handoff

Updated 2 November 2026 (public copy live, v1.1.1). Read this first when you pick the project up again (person or AI
assistant). The README describes the program; this file says where it stands, what is open and what was decided.

## Public copy (2 November 2026)
Decision: a second, public copy on its own Railway project, with `PUBLIC_MODE=1`, so that anyone can use the planner
without an account or an installation. Paul's own copy keeps its accounts and keeps deploying `main`; the public copy
deploys a tagged image only. Full plan, owner decisions D1–D6 and the status of each step:
`docs/PUBLIC_MODE_BRIEF.md`. What changed: `docs/RELEASE_NOTES_v1.1.0.md`.

Open, in order:
1. Done, 2 November: commit 8ac22b7, release-readiness green, tag `v1.1.0` released (Windows zip on GitHub
   Releases; Docker image `ghcr.io/w7iv/hfta-stack-planner:v1.1.0`, publicly pullable).
2. **Memory measurement:** done 2 November in the v1.1.0 image (public mode, 2 CPUs, 4 GB). Heavy Designer
   search: 6 targets x 3 headings, 72 real profiles, tribanders 2-4 high (20-200 ft) plus 40 m 1-2 high.
   Peak memory of the whole container: **136 MB**. Memory is not the limit: set the public replica to 2 vCPU and
   1 GB, and `LIMIT_MEMORY_MB=1024`.
   **Finding:** the same search took **45 minutes** (20,238 HFTA runs, about 0.27 s each on 2 workers).
   `STAGE_SECONDS` limits only the first (coarse) stage of each group; the refine stages (40, 20, 10, 5 ft)
   have no time limit and took 40 of the 45 minutes. One such search holds one of the two server places for
   45 minutes. Fixed in v1.1.1 (2 November): a 10-minute limit for the whole search in public mode
   (`SEARCH_SECONDS`), and the per-workspace allowance Paul proposed: 2 Designer searches, 3 height scans,
   3 VOACAP tables, in total, shown up front. See `docs/RELEASE_NOTES_v1.1.1.md`. Checked in a local build of
   v1.1.1: the same search took 7.3 minutes, best FOM 0.28 dB below the 45-minute result, 107 MB peak.
   Done: commit d4641af, release-readiness green, tag `v1.1.1` released.
3. Done 2 November: the public copy runs v1.1.1 at hfta-stack-planner-production-6f55.up.railway.app
   (own Railway project, replica 2 vCPU and 1 GB, volume `/data`, `PUBLIC_MODE=1`, `LIMIT_MEMORY_MB=1024`,
   `OPERATOR_CONTACT`, `STATS_PASSWORD`). Read-only checks passed. Decision D5 changed: Railway has only
   account-wide usage limits, and the account carries other projects, so the replica size is the cost limit
   (about $50 per month at most). **Paul:** check the project's usage weekly; one-week private trial with the
   acceptance checks in the brief; then announce.
4. **v1.1.2 prepared** (2 November, `docs/RELEASE_NOTES_v1.1.2.md`): the Designer no longer lists layouts with
   an antenna that no switch setting selects (Paul found "40 m Yagi 5 / 145" equal to "15 / 145" on the public copy),
   an empty lowest height is a quarter wavelength, and the K6TU and "this computer" texts are corrected. Affects
   every copy since the Designer was added, the Windows zip included. **Paul:** commit, release-readiness, then
   tag `v1.1.2` (with the trial's fixes, or alone) and move the public copy to image `v1.1.2`.
   Done: v1.1.2 released 3 November (commit 8385bc8). **Paul:** move the public copy to image `v1.1.2`.
   Not yet released (next release): the "Rohn 65G 160 ft standard" guy button is removed (Paul, 2 November). An
   engineered tower may have more guy levels or other heights for the wind load at its site, so every user enters
   the guys from their own tower's drawings. The button also set the tower height to 160 ft without saying so.
   Guy tables already saved in projects are kept.
   Also not yet released: VOACAP tables per workspace raised from 3 to 7, in total and per day (Paul, 3 November;
   the trial refused a worldwide set of 7 regions). Until the next release, set `LIMIT_VOACAP_TABLES=7` and
   `LIMIT_VOACAP_PER_DAY=7` on the public Railway project. And the page never shows an empty error message any more
   (over HTTP/2 the status text is empty, so a refusal that was not JSON showed as "").
5. **Paul:** attorney check on ARRL files (decision D3). `PRN_UPLOAD=off` is ready if the answer is no.

The 14 October outage (item 1 below) was looked at on 2 November: the deploy logs show normal replacements by new
deploys (five or more pushes that day), not a crash or a memory kill. `HFTA_WORKERS` was 24 on Railway and is now 2.

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
