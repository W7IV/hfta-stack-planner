# HFTA Stack Planner

A local web application around **OpenHFTA**, an open-source implementation of the method of N6BV's HFTA
(HF Terrain Assessment). It compares tower sites, antenna stacks and switch settings over real terrain. Every run
is recorded with the exact inputs to type into the original HFTA, so any number can be checked there.

**Engine.** All calculations are done by OpenHFTA, not by the original ARRL HFTA program. The engine (OpenHFTA
commit, SHA-256 of the native library, wrapper version) is recorded with every result and export.

## Credits
- **Calculations:** [OpenHFTA](https://github.com/RioDXGroup/openhfta) by RioDXGroup (BSD Zero Clause licence).
  This planner does not include or change OpenHFTA: the Dockerfile downloads it at a fixed commit, builds it, and
  calls it unchanged. Thanks to its authors.
- **HFTA:** written by R. Dean Straw, N6BV (Silent Key), and published by ARRL with *The ARRL Antenna Book*.
  This planner follows HFTA's method so that every result can be checked in HFTA.
- **Elevation-angle (.PRN) files:** copyright ARRL. They are not included; users supply their own.
- Not affiliated with or endorsed by ARRL or the OpenHFTA authors.

## The rule
**Every Figure of Merit (FOM) shown is one OpenHFTA run, or simple arithmetic on runs.**
The arithmetic is limited to:
- the weighted mean over a target's headings (e.g. 44°, 52°, 60° for Europe), and
- the best of a tower's stack-switch settings (whole stack, pairs, single antennas).
- for an overall score over several targets (Stack Designer, Worldwide view): for each target the mean over its bands,
  then the weighted mean over the targets. This is an average of dB values chosen as a planning score; it is not
  the same as HFTA's own FOM, which weights linear power by the arrival-angle statistics.

**Invalid core output.** A known fault of the calculation core returns a few invalid angles on some profiles.
Up to 8 isolated angles (2 degrees) are filled by straight-line interpolation; the run is then marked (* in Compare,
a note in the result, `core_note` in the replay pack). A run with more invalid angles, or an invalid first or last
angle, is a failed run: it gets no FOM and is never ranked.

**Missing arrival-angle data.** A target without a .PRN file, or a band that its .PRN file does not contain, gives no
result and says why. The Stack Designer refuses to start until every chosen target has data on every band it scores.
Antennas are entered as HFTA enters them: for each band, the number of elements (Dipole, 2-6 or 8). No brand
models. Two checks are added as notes only; they never change a number:

| Check | What it shows |
|---|---|
| Spacing warnings | Stack spacing in wavelengths (HFTA has no mutual coupling, so close stacks look too good) and the gap between antennas on different bands. Red = too close, amber = close. Limits can be changed per project (default: red below 0.30 wavelength, amber below 0.40; gap red below 10 ft, amber below 15 ft). |
| Guy and ice check | Turning antennas against guy wires, with guy sag and element droop under radial ice (assumptions and range: core/guys.py). |

## Workflow (five steps)
1. **Sites**: one or more tower positions on the property. Terrain fetched online for any place in the world (USGS
   3DEP in the US, AWS Terrain Tiles elsewhere), from MicroDEM .PRO files, K6TU one-degree terrain sets
   (https://www.k6tu.net), or generated from a DEM file (GeoTIFF or ESRI ASCII grid). Compare the sites' profiles
   and ground slope side by side.
2. **Targets**: a path (e.g. Europe 52°), its ARRL elevation-angle file (.PRN), headings and bands.
   The ARRL .PRN files come with the ARRL Antenna Book and are not included.
3. **Towers**: stacks of antennas (height and elements per band, as in HFTA), with spacing warnings, the targets each
   tower serves (this sets the directions, because HFTA treats the antennas as facing the azimuth of the terrain
   file), stack switching, and an optional guy and ice check (Phillystran or EHS, radial ice, element droop).
   A height scan finds good heights for one antenna. **Stack Designer** searches the stack heights
   for the best weighted result over all chosen targets (for example six regions), within spacing, gap, height and
   guy limits, and shows the loss against each target's own best layout.
4. **Compare**: all sites × towers × targets × bands. Click any value to see the HFTA runs behind it, the elevation
   pattern with the arrival angles, and the exact inputs to type into HFTA.
5. **Report**: HTML report, Excel workbook (results built from the run log with live formulas), CSV, the
   **HFTA replay pack**, and the project file.

## HFTA replay pack
A zip with every terrain and .PRN file used, `runs.csv` (each HFTA run: terrain file, elevation file, frequency,
antenna type, heights, ground, diffraction, FOM), `combination.csv` (how runs combine into each result),
`expected_out/<run>.PRN` (the expected pattern in HFTA's OUT.PRN layout) and step-by-step instructions.

## Tests
- `python tests/test_hfta_match.py` compares the core with 16 runs written by the original HFTA (560 gains at
  14.2 MHz, 4-element antennas): all agree within 0.1 dB, the precision HFTA prints. The test first checks itself:
  it must fail on invalid core output (NaN, infinite values, short output). This reference set covers one band and one
  antenna type only; other bands, types and FOM values are not yet compared with the original HFTA.
- `python tests/test_accounts.py` checks logins, user management and the separation of users' project stores.
- `python tests/test_wrapper.py` checks the planner's own guarantees with the real core and the synthetic test .PRN:
  safe file paths, input checks, recalculation when a terrain file changes, invalid-output policy, missing data,
  terrain replacement, the Stack Designer's exact search, guy limits, export safety, cross-site requests, and
  shareable exports.

## Running it (on your own computer)
The app runs locally; nothing is sent to a server.

1. Install Python 3.10+ and gfortran. On Windows, use WSL (Ubuntu): `sudo apt install python3-pip gfortran`.
2. Build the OpenHFTA core next to this folder (`../openhfta`), following its README.
3. `pip install -r requirements.txt`
4. `python app.py`, then open http://localhost:5000
   (`PORT` and `HOST` environment variables change the address; the default listens on this computer only).
   Nothing leaves this computer, except the "Fetch terrain online" request to USGS (position only).

Projects are stored in `projects/<name>/` (project.json, terrain, .PRN files, results).
The previous single-page optimiser (multi-antenna height search, tribander trade-off matrix) is still at `/classic`.

**With Docker (any system, no compiler needed):**
```
docker build -t hfta-planner .
docker run -p 127.0.0.1:5055:5055 -v hfta-data:/data hfta-planner
```
Then open http://localhost:5055. Projects are kept in the Docker volume `hfta-data`. `127.0.0.1:` keeps the app on
this computer only; without it Docker opens the port to the whole network, with no password. The image builds the OpenHFTA
core at a pinned commit and checks it against the original HFTA during the build.

## Hosted test copy (Railway)
1. Push this folder to a private GitHub repository.
2. Railway: New project → Deploy from GitHub repo. Railway finds the `Dockerfile`.
3. Add a volume mounted at `/data` (projects are stored there).
4. Variables: `APP_PASSWORD` (the administrator's password) and `HFTA_WORKERS` (number of vCPUs of the
   service). On Railway, or with `HOSTED=1`, the app **refuses to start without `APP_PASSWORD`**.
5. Settings → Networking → Generate domain.

**Accounts.** With `APP_PASSWORD` set, every page needs a login. The administrator logs in as **admin** with that
password and creates users on the **Users** page (top right); each user has a name, a password, and a project store
and library of their own under `users/<name>/` on the data volume. Users never see each other's projects or files,
and the administrator's projects are the base store (the projects of a copy that ran before accounts existed are
the administrator's). Removing a login keeps the user's files on the volume. Logins last 30 days; after eight
failed attempts an address must wait five minutes. Set `SECRET_KEY` to keep logins valid across redeploys
(otherwise a random key is kept on the volume, which does the same). Without `APP_PASSWORD` (own computer) there
is no login and one store.

**Moving a project:** Report → "Project with files (zip)" on one copy, then "Open project zip" on the other.
The zip holds the terrain and .PRN files; results are recomputed. The ARRL .PRN files are copyright: keep such
zips and any hosted copy private.

**Sharing with someone else:** use the *shareable* downloads (Report page): the replay pack and the project zip
then leave the .PRN files out and list them by name and SHA-256, so the other person can check that their own copy
is the same file. The private versions are for your own records only.

| Variable | Meaning | Default |
|---|---|---|
| `PORT` | web port | 5000 (`python app.py`), 5055 (container); Railway sets it |
| `APP_PASSWORD` | password for the browser | none |
| `PROJECTS_DIR` | where projects are stored | `./projects` (`/data/projects` in the container) |
| `HFTA_WORKERS` | calculation processes | number of CPUs |
| `HOSTED` | `1` = server on a network: a password is then required | not set |
| `SECRET_KEY` | signing key for login cookies | random, kept on the data volume |
| `OPENHFTA_DIR` | OpenHFTA checkout | `../openhfta` (`/opt/openhfta` in the container) |

## VOACAP angle tables (any origin in the world)
Targets → **Generate with VOACAP…** makes a `.PRN` elevation-angle table for any origin and region, so that a station
outside the US (or in Alaska) can use steps 2–5 without ARRL files. `voacapl` (public-domain VOACAP for Linux, port by
M0DNS, github.com/jawatson/voacapl) is built into the Docker image; for a local run install it and run `makeitshfbc`
(`VOACAPL` and `ITSHFBC` environment variables point to the binary and the data folder if they are not in the default
places). Every generated file is titled "VOACAP-generated"; it is not an ARRL file.

**Method** (core/aoa_gen.py), after the way N6BV made the ARRL files: VOACAP method 25 (all modes) is run for every month,
every hour and three sunspot numbers (10, 70, 150), from the origin to several receive points that stand for the region,
with isotropic antennas, 1.5 kW and a required SNR of 24 dB. Every propagation mode of every hour contributes its
elevation angle, weighted by that mode's reliability. The weighted counts at each whole degree are written as
percentages per band. Options: a choice of months (e.g. the contest season), of UTC hours (e.g. night), of solar
level, and custom receive points instead of a region.

**Check against the ARRL files.** Tables for the W1 (Boston, MA) origin were compared with the seven ARRL W1-MA files
(`tools/compare_prn.py`): for each band, the FOM of eight test antennas (single 4-element Yagis at 40–160 ft and
stacks) over flat ground was computed with both files. A constant offset between two files does not change which
antenna wins; the number that matters is the largest FOM difference after removing that offset ("ranking error").

| Region | Mean angle, ARRL vs VOACAP (20 m) | Ranking error, worst band | Note |
|---|---|---|---|
| Europe | 11.1° vs 10.1° | 0.6 dB | all bands within 0.6 dB |
| Japan | 5.6° vs 6.1° | 1.4 dB | |
| Asia | 6.9° vs 5.3° | 1.2 dB | 40 m: ARRL has more at 1–2°, a 4 dB offset but the same ranking |
| southern Africa | 7.3° vs 6.7° | 0.9 dB | ARRL 80 m column is nearly empty |
| Oceania | 5.2° vs 4.6° | 2.0 dB | 10 m |
| South America | 10.2° vs 10.8° | 1.0 dB | |
| USA | 17.9° vs 17.1° | 1.9 dB on 80–15 m | 12 and 10 m disagree (4.8 and 7.8 dB): VOACAP predicts higher angles for domestic paths than the ARRL file |

So for DX regions a VOACAP table ranks antennas the way the ARRL file does, within the 1 dB that matters in practice.
For domestic 12 and 10 m the two methods differ; use the ARRL file there if you have it. The ARRL files remain the
reference where they exist. The receive points per region are listed in core/aoa_gen.py; "Asia" is India to China.

## Development list
Both items for stations outside the US are done. Open points:

1. ~~Docker image with VOACAP~~: done, see "VOACAP angle tables" above. Still to do: a W1-MA comparison in the test
   suite needs the ARRL files, which are not in the repository, so it stays a manual check (`tools/compare_prn.py`).

2. ~~Terrain for any country~~: done. "Fetch terrain online" uses USGS 3DEP inside the United States and AWS
   Terrain Tiles (Tilezen `skadi` tiles in the SRTM `.hgt` layout) anywhere else: SRTM worldwide, better national
   open data in much of Europe, Canada, Australia and New Zealand, ArcticDEM/GMTED north of 60°. About 30 m
   spacing (the ARRL HFTA notes call 30 m enough for HF). Tiles are cached under `<PROJECTS_DIR>/_cache/hgt`
   (about 25 MB per degree square). All of these sets measure tree tops, not the ground. Attribution: Tilezen /
   Mapzen Terrain Tiles and the sources listed at github.com/tilezen/joerd; no service guarantee.

3. ~~Hardening before public hosting~~: done. Browser rules (content security policy: scripts and styles only from
   the planner itself, no framing), the container runs as an unprivileged user (the entrypoint starts as root only to
   make the data volume writable, then drops root), and a project keeps a revision number: when two windows edit
   the same project, the second save is refused with a notice to reload instead of overwriting the first.
4. ~~Check of the guy-wire model~~: the sag formula (parabola, constant initial tension) was compared with an exact
   catenary in the tests: within 0.7 ft in the worst case tried (steep guy, 1.25 in ice, thin wire) and within
   0.2 ft in ordinary cases; the 2 ft margin covers it. Assumptions are listed at the top of core/guys.py. Wind,
   insulators and the guy load on the tower are not modelled; a tower engineer's calculation takes precedence.

## Limits
- HFTA's method is validated for 7–30 MHz. Below 7 MHz diffraction is less reliable; above 30 MHz terrain data
  must resolve features of about 1/8 wavelength.
- HFTA has no mutual coupling between stacked antennas; close spacing (under about 0.3 wavelength) is rated
  too well.
- At most 4 antennas of one type per band, as in HFTA.
