# HFTA Stack Planner

A local web application around **OpenHFTA**, the open-source port of N6BV's HFTA (HF Terrain Assessment).
It compares tower sites, antenna stacks and switch settings over real terrain, and every number it reports can be
reproduced in the original HFTA.

## Credits
- **Calculations:** [OpenHFTA](https://github.com/RioDXGroup/openhfta) by RioDXGroup (BSD Zero Clause licence).
  This planner does not include or change OpenHFTA: the Dockerfile downloads it at a fixed commit, builds it, and
  calls it unchanged. Thanks to its authors.
- **HFTA:** written by R. Dean Straw, N6BV (Silent Key), and published by ARRL with *The ARRL Antenna Book*.
  This planner follows HFTA's method so that every result can be checked in HFTA.
- **Elevation-angle (.PRN) files:** copyright ARRL. They are not included; users supply their own.
- Not affiliated with or endorsed by ARRL or the OpenHFTA authors.

## The rule
**Every Figure of Merit (FOM) shown is one HFTA run, or simple arithmetic on HFTA runs.**
The arithmetic is limited to:
- the weighted mean over a target's headings (e.g. 44°, 52°, 60° for Europe), and
- the best of a tower's stack-switch settings (whole stack, pairs, single antennas).

Antennas are entered as HFTA enters them: for each band, the number of elements (Dipole, 2-6 or 8). No brand
models. Two checks are added as notes only; they never change a number:

| Check | What it shows |
|---|---|
| Spacing warnings | Stack spacing in wavelengths (HFTA has no mutual coupling, so close stacks look too good) and the gap between antennas on different bands. Red = too close, amber = close. Limits can be changed per project (default: red below 0.30 wavelength, amber below 0.40; gap red below 10 ft, amber below 15 ft). |
| Guy and ice check | Turning antennas against guy wires, with guy sag and element droop under radial ice. |

## Workflow (five steps)
1. **Sites**: one or more tower positions on the property. Terrain from MicroDEM .PRO files, K6TU one-degree
   terrain sets (https://www.k6tu.net), or generated on this computer from a DEM file (GeoTIFF or ESRI ASCII grid;
   USGS 3DEP 1 m LiDAR works). Compare the sites' profiles and ground slope side by side.
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

## Proof of agreement with HFTA
`python tests/test_hfta_match.py` compares the core with 16 runs written by the original HFTA (560 gains);
all agree within 0.1 dB, the precision HFTA prints.

## Running it (on your own computer)
The app runs locally; nothing is sent to a server.

1. Install Python 3.10+ and gfortran. On Windows, use WSL (Ubuntu): `sudo apt install python3-pip gfortran`.
2. Build the OpenHFTA core next to this folder (`../openhfta`), following its README.
3. `pip install -r requirements.txt`
4. `python app.py`, then open http://localhost:5000
   (`PORT` and `HOST` environment variables change the address; the default listens on this computer only).

Projects are stored in `projects/<name>/` (project.json, terrain, .PRN files, results).
The previous single-page optimiser (multi-antenna height search, tribander trade-off matrix) is still at `/classic`.

**With Docker (any system, no compiler needed):**
```
docker build -t hfta-planner .
docker run -p 5055:5055 -v hfta-data:/data hfta-planner
```
Then open http://localhost:5055. Projects are kept in the Docker volume `hfta-data`. The image builds the OpenHFTA
core at a pinned commit and checks it against the original HFTA during the build.

## Hosted test copy (Railway)
1. Push this folder to a private GitHub repository.
2. Railway: New project → Deploy from GitHub repo. Railway finds the `Dockerfile`.
3. Add a volume mounted at `/data` (projects are stored there).
4. Variables: `APP_PASSWORD` (required on the internet; the browser asks for it, any user name) and
   `HFTA_WORKERS` (number of vCPUs of the service).
5. Settings → Networking → Generate domain.

**Moving a project:** Report → "Project with files (zip)" on one copy, then "Open project zip" on the other.
The zip holds the terrain and .PRN files; results are recomputed. The ARRL .PRN files are copyright: keep such
zips and any hosted copy private.

| Variable | Meaning | Default |
|---|---|---|
| `PORT` | web port | 5000 (`python app.py`), 5055 (container); Railway sets it |
| `APP_PASSWORD` | password for the browser | none |
| `PROJECTS_DIR` | where projects are stored | `./projects` (`/data/projects` in the container) |
| `HFTA_WORKERS` | calculation processes | number of CPUs |
| `OPENHFTA_DIR` | OpenHFTA checkout | `../openhfta` (`/opt/openhfta` in the container) |

## Development list
Items waiting for the self-hosted server. Nothing here is started.

1. **Docker image with VOACAP.** Add `voacapl` (open-source VOACAP command line, ITS public domain) to the
   image next to OpenHFTA. Then the planner can make `.PRN` elevation-angle files for any site and target,
   the way N6BV made the ARRL files: VOACAP runs over 12 months × 24 hours × low/medium/high solar activity,
   histogram of the arrival angle of the strongest mode per band, written in the ARRL `.PRN` layout.
   Today the `.PRN` files exist only for US origins, so a station outside the US cannot use steps 2–5.
   - Any origin: the station's own lat/lon, anywhere in the world (Europe, Asia, Oceania, Alaska, ...).
   - First step: generate a file for the W1-MA origin and compare it with the ARRL W1 file, to prove the method
     before anyone relies on it.
   - Options beyond the ARRL files: chosen months (e.g. contest season, late October–November), chosen hours
     (e.g. night-time for 40 m), expected solar activity instead of the whole-cycle average, and custom targets
     (one entity or a narrow direction instead of a broad region).
   - Generated files must be marked as VOACAP-generated, never presented as ARRL data.
   - Limit: VOACAP gives one or a few modes per hour, so the angle histogram is coarser than measured data.

2. **Terrain for any country.** "Fetch terrain online" uses USGS 3DEP, United States only. Research notes:
   - *SRTM* (Shuttle Radar Topography Mission, February 2000) is what MicroDEM used when HFTA was new.
     The ARRL HFTA notes say 30 m data is enough for HF and 90 m is acceptable. SRTM covers 56°S to 60°N only:
     Ketchikan (55°N) is inside, Anchorage, Fairbanks and most of Scandinavia north of Oslo are outside.
     The radar measures tree tops, not the ground, as do all the global sets below.
     NASA's own copies (Earthdata, SRTMGL1 v3, 1 arc-second, voids filled) need a free login, so they cannot be
     fetched by one button.
   - *AWS Terrain Tiles* (`elevation-tiles-prod` bucket, Mapzen/Tilezen) is the practical source. The `skadi`
     folder holds 1°×1° tiles in the SRTM `.hgt` layout (3601×3601, 16-bit big-endian metres, gzip, about 25 MB),
     no key, no account. The tiles merge SRTM worldwide, 3DEP for the US including Alaska, national open DEMs for
     much of Europe, Canada, Australia and New Zealand, and ArcticDEM/GMTED north of 60°, so one reader covers
     US and overseas sites and closes the SRTM gap in the north. There is no service guarantee; attribution is
     required (Tilezen lists the sources). URL: `https://elevation-tiles-prod.s3.amazonaws.com/skadi/N55/N55W132.hgt.gz`.
   - *Copernicus GLO-30* (TanDEM-X, 2011–2015) is the newer alternative: global including the poles, 30 m,
     free on AWS without a key, Cloud-Optimised GeoTIFF tiles. Larger files; the existing GeoTIFF reader works.
   - Plan: add an `.hgt` reader (about ten lines: `np.fromfile('>i2')`, 3601×3601, no-data −32768,
     origin at the tile's south-west corner) and a second fetch route that picks Terrain Tiles for any lat/lon
     and keeps 3DEP for the US. Profiles that cross a tile edge need the neighbouring tile.

## Limits
- HFTA's method is validated for 7–30 MHz. Below 7 MHz diffraction is less reliable; above 30 MHz terrain data
  must resolve features of about 1/8 wavelength.
- HFTA has no mutual coupling between stacked antennas; close spacing (under about 0.3 wavelength) is rated
  too well.
- At most 4 antennas of one type per band, as in HFTA.
