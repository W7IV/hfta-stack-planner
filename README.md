# HFTA Stack Planner

A local web application around **OpenHFTA**, an open-source implementation of the method of N6BV's HFTA
(HF Terrain Assessment). It compares tower sites, antenna stacks and switch settings over real terrain. Every run
is recorded with the exact inputs to type into the original HFTA, so any number can be checked there.

**Engine.** All calculations are done by OpenHFTA, not by the original ARRL HFTA program. The engine (OpenHFTA
commit, SHA-256 of the native library, wrapper version) is recorded with every result and export.

> **Safety, engineering and accuracy notice:** This is comparative RF-planning software, **not**
> a structural engineering, tower-safety or antenna-clearance certification. HFTA results are modeled estimates,
> not assured gain, coverage or contest performance; the optional guy/ice checks and spacing warnings cannot
> establish whether an installation is safe. Do not use outputs alone to design, erect or modify towers, guy wires,
> foundations, anchors or antennas. Independently verify inputs, engineering and real-world performance, and obtain
> qualified review for safety-critical decisions. Provided **AS IS** under MIT.
> Read the [Legal, Performance and Engineering Disclaimers](DISCLAIMER.md) before relying on results.

## Windows release signing

Windows release ZIPs now require Microsoft **Artifact Signing** Authenticode signatures and
RFC3161 timestamps before GitHub's release workflow can publish them. The ZIPs built locally
or as unapproved CI candidates remain unsigned until the dedicated Windows signing job runs.
The signing identity is the Azure-verified individual's legal name; the project remains
**HFTA Stack Planner by W7IV**, distributed under the MIT license.

**For maintainers:** set up the Entra service principal, `artifact-signing` GitHub
environment, federation and Certificate Profile Signer role as documented in
[Artifact Signing setup](docs/ARTIFACT_SIGNING.md).
Until those are configured, the release workflow deliberately **fails closed**
instead of distributing an unsigned Windows executable. Past releases (through
v1.0.5) remain unsigned and may be blocked by Windows Smart App Control.

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
1. **Sites**: one or more tower positions on the property. Choose coordinates manually or use **Pick location on map** (interactive OpenStreetMap tiles, online only). Changing coordinates from the map clears that site's old terrain profiles and previous comparison results, so fetch terrain again. Terrain fetched online for any place in the world (USGS
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
   guy limits, and shows the loss against each target's own best layout. A run costs 0.01 to 0.7 s depending on
   terrain, band and stack size, so the Designer times a few runs first and coarsens the height grid until each
   stage fits about four minutes, then searches fine around the best coarse layouts; the summary says when it did.
   Cancel beside the progress bar stops a search.
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

**Windows (no installation):** download `HFTA-Stack-Planner-windows-<version>.zip` from the Releases page, unzip it
anywhere, double-click **Start HFTA Stack Planner.exe**, and the browser opens http://localhost:5055. The package
holds its own Python, the OpenHFTA core and VOACAP; your projects stay in its `data` folder. The Windows package uses a small native launcher rather than a batch script. This unsigned executable
may still be blocked by Smart App Control or SmartScreen; use the local Docker image if blocked,
and report the exact Windows warning rather than disabling security protections. The package is built by
`tools/build_windows.sh` and checked against the original-HFTA output before it is zipped.

**Upgrading on Windows:** close every previous HFTA console before launching the newer executable. Only one instance
can occupy `127.0.0.1:5055`; the launcher refuses to run if that port is already in use, rather than opening an
older copy in the browser. Each extracted release uses its own `data` folder; copy the **data** folder from your
old release into the new extracted folder before starting if you want to retain your towers, targets and terrain.

**Linux, macOS, and Windows with Docker (no native installation required):**

HFTA Stack Planner ships a **Linux Docker image**, containing the Python web app, compiled OpenHFTA engine,
and VOACAP. Install [Docker Engine](https://docs.docker.com/engine/install/) on Linux or
[Docker Desktop](https://docs.docker.com/desktop/) on macOS/Windows, then run:

```bash
docker run -d --name hfta-planner --platform linux/amd64 \
  -p 127.0.0.1:5055:5055 \
  -v hfta-data:/data \
  ghcr.io/w7iv/hfta-stack-planner:v1.0.5
```

Open **http://localhost:5055** in your browser. Data persists in the named Docker volume `hfta-data`,
even when the container stops or is replaced. To stop or restart it:

```bash
docker stop hfta-planner
docker start hfta-planner
```

To remove the container while retaining your projects, use `docker rm -f hfta-planner`.
**Do not delete the `hfta-data` volume** unless you intend to delete its projects.
Only one local instance should bind host port 5055 at a time; if it is occupied, stop the older container
or choose another host port (for example, `-p 127.0.0.1:5056:5055`, then browse to
`http://localhost:5056`).

| Host computer | Docker execution | Current status |
| --- | --- | --- |
| Linux x86-64 (AMD64) | Linux container runs on the host's Linux kernel | **Built and tested in CI** |
| Intel Mac | Linux container runs inside Docker Desktop's Linux VM | Expected to work; not independently verified on macOS |
| Apple Silicon Mac (M-series) | `linux/amd64` image via Docker Desktop emulation | **Experimental**; may be slower or fail |
| Linux ARM64 (e.g. Raspberry Pi / ARM server) | `linux/amd64` image requires installed emulation support | **Experimental**, not verified |
| Windows with Docker Desktop | Linux container in Docker's Linux/WSL2 environment | Alternative to the standalone Windows EXE |

**Architecture limitation:** The published image is currently built for **AMD64 only**; OpenHFTA's pinned
Fortran build uses x86-specific compiler settings. `--platform linux/amd64` requests the existing image;
it **does not** make it a native ARM64 binary. An ARM64 image and a native macOS application would need
separate builds and tests. The project is open source, so contributors can experiment with other platforms.

This is a **local HTTP service**, bound by the example command to `127.0.0.1` only. It does not require
HTTPS for local use; do not expose the container publicly without suitable authentication and TLS.
Online terrain retrieval contacts external elevation services. For the newest released container instead
of this pinned example, substitute `ghcr.io/w7iv/hfta-stack-planner:latest`.

**From source:**
1. Install Python 3.10+ and gfortran. On Windows, use WSL (Ubuntu): `sudo apt install python3-pip gfortran`.
2. Build the OpenHFTA core next to this folder (`../openhfta`), following its README.
3. `pip install -r requirements.txt`
4. `python app.py`, then open http://localhost:5000
   (`PORT` and `HOST` environment variables change the address; the default listens on this computer only).
   Terrain fetching contacts USGS or Terrain Tiles. Opening **Pick location on map** also requests map tiles directly from OpenStreetMap and reveals the viewed map area to that service; it does not request browser geolocation.

Projects are stored in `projects/<name>/` (project.json, terrain, .PRN files, results).
The previous single-page optimiser (multi-antenna height search, tribander trade-off matrix) is still at `/classic`.

**Building the Docker image yourself:**
```
docker build -t hfta-planner .
docker run -p 127.0.0.1:5055:5055 -v hfta-data:/data hfta-planner
```
`127.0.0.1:` keeps the app on this computer only; without it Docker opens the port to the whole network, with no
password. The image builds the OpenHFTA core at a pinned commit and checks it against the original HFTA during the
build. A tag `v*` pushed to GitHub builds the Windows package and the image (`.github/workflows/release.yml`) and
publishes a release; the image is on GitHub Container Registry (set the package to public once in its settings). The image builds the OpenHFTA
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

**What a hosted copy stores, and where it goes** (for users who ask):
- On the server, per user: project files (names, site positions, notes, antennas), terrain profiles, the
  elevation-angle files the user adds or generates, calculation results, and the user name with a salted password
  hash. Nothing else: no e-mail address, no analytics, no scripts from other sites.
- Data is kept until the user deletes it (Report → Delete project; Sites → Remove profiles) or the administrator
  removes the user's folder. There is no automatic retention or deletion. Railway volume backups, if enabled, keep
  copies for as long as Railway's backup settings say.
- Terrain requests leave the server only on the user's click: "Fetch terrain online" sends the site position to
  USGS (3DEP) or to Amazon's Terrain Tiles service, which see that position and the server's address. The VOACAP
  calculation and everything else run on the server.
- Opening **Pick location on map** sends visible map-tile requests directly from the user's browser to OpenStreetMap, revealing the viewed area and the requesting IP address. Map tiles require internet; no location services or tracking scripts are used. Users should avoid opening the map for confidential station positions when sharing the map area with an outside provider is unacceptable.
- The web server's access log (kept by Railway) records addresses, paths and times, not the contents of requests.
- The login cookie holds only the user name, signed; it expires after 30 days or at logout.

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
Targets → **Generate with VOACAP…** lets you check one, several or **all seven standard regions** in a single run. It writes a separate, clearly named `.PRN` file for each selected region (e.g., `My-station-EU-VOACAP.PRN`) **and creates the corresponding target automatically**, using the region's great-circle bearing and available bands. Existing targets are preserved, not duplicated. The Targets page also offers **Add missing targets from VOACAP files** for files generated before this update; custom receive points remain available as a separate mode. A station
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
Current status, open tasks and recent decisions are in `HANDOFF.md`. The items below are done:

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
   0.2 ft in ordinary cases. These tests validate only the numerical approximation for the tested cases; the
   default 2 ft margin is not a certified safety margin. Assumptions are in core/guys.py. Wind, insulators and
   guy loads on the tower are not modeled; qualified engineering is required for safety decisions.

## Profile length: 4.4 km or 10 km
HFTA reads at most 148 points per profile. The standard is 4.4 km at 30 m, as MicroDEM and K6TU make them.
"Fetch terrain online" can instead make 10 km profiles at 68 m spacing. Two things to know before using them:
- Coarser spacing changes the result on rough ground. On the KK6P test terrain, going from 30 m to 60 m moved
  single-antenna FOMs by up to 1.5 dB, the same order as the differences being studied. Compare 10 km profiles only
  with other 10 km profiles.
- A 100 m ridge 8 km out changed the FOM at 1–3° by less than 1 dB in a test. Distant terrain matters only for a
  real ridge above the antenna's horizon.

So the planner also reports the **far horizon**: after each online fetch it scans the ground from the end of the
profile out to 15 km in every direction and shows the highest elevation angle seen from 30 m up the tower (site
card, and per target in "Compare terrain"). A value near or above 1° means a distant ridge that the HFTA profiles
do not contain; that is the case for a 10 km profile. Below that, the standard 4.4 km profile is the better choice.

## Limits
- HFTA computes elevation angles 1–35° only. The FOM counts the arrival-angle weight inside that range and
  ignores the rest, so it cannot score NVIS or other high-angle paths. A target whose table has less than half
  its weight at or below 35° on a band is not evaluated on that band (the reason is shown); 50–90% is evaluated
  with a note. The .PRN plot marks the 35° line and names the bands affected.
- 6 m rows are allowed on tower cards for the tower drawing, the spacing check and the guy check only; they are
  never scored (HFTA stops at 30 MHz and no elevation-angle table covers 50 MHz).
- HFTA's method is validated for 7–30 MHz. Below 7 MHz diffraction is less reliable; above 30 MHz terrain data
  must resolve features of about 1/8 wavelength.
- HFTA has no mutual coupling between stacked antennas; close spacing (under about 0.3 wavelength) is rated
  too well.
- At most 4 antennas of one type per band, as in HFTA.
- The soil presets are the original HFTA list, which descends from the 1940 FCC broadcast-band table that
  K6STI's "HF ground constants" page shows to be unsuitable for HF. This does not matter here: measured on the
  test terrain and on flat ground with every preset and with K6STI's frequency-dependent values for his five
  terrain types, the FOM of horizontal antennas moves by under 0.2 dB on 80 m and under 0.1 dB from 40 m up.
  The ground reflection at low angles is nearly total for horizontal polarisation whatever the soil. Use
  K6STI's constants for verticals and NEC ground-loss work; for this planner, "Average soil" is enough.

## License and third-party rights

See [DISCLAIMER.md](DISCLAIMER.md) for legal, performance, structural-engineering and safety limitations.
These notices do not change the MIT license rights granted to recipients.

Original HFTA Stack Planner code is provided under the [MIT License](LICENSE), subject to the rights of its contributors. Bundled and downloaded components retain their own licenses: see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and `licenses/`. In particular, bundled Plotly.js is MIT-licensed, OpenHFTA is 0BSD, and the VOACAP port includes CC0 contributions. ARRL elevation-angle files are not licensed for redistribution by this project.
