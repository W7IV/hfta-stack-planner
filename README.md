# HFTA Stack Planner

A local web application around **OpenHFTA**, the open-source port of N6BV's HFTA (HF Terrain Assessment).
It compares tower sites, antenna stacks and switch settings over real terrain, and every number it reports can be
reproduced in the original HFTA.

## The rule
**Every Figure of Merit (FOM) shown is one HFTA run, or simple arithmetic on HFTA runs.**
The arithmetic is limited to:
- the weighted mean over a target's headings (e.g. 44°, 52°, 60° for Europe), and
- the best of a tower's stack-switch settings (whole stack, pairs, single antennas).

Anything HFTA cannot do is a separate, labelled **layer**, switched off by default:

| Layer | What it adds | Default |
|---|---|---|
| Maker gain | manufacturer free-space gain minus HFTA's generic type (e.g. 7-el entered as 6-el) | off |
| Beam loss | loss of a fixed antenna off its heading | off |
| Guy and ice check | geometry check of antennas against guy wires (not a FOM) | separate tab |

The top bar shows **Pure HFTA** while no layer is on.

## Workflow (five steps)
1. **Sites**: one or more tower positions on the property. Terrain from MicroDEM .PRO files, K6TU one-degree
   terrain sets (https://www.k6tu.net), or generated on this computer from a DEM file (GeoTIFF or ESRI ASCII grid;
   USGS 3DEP 1 m LiDAR works). Compare the sites' profiles and ground slope side by side.
2. **Targets**: a path (e.g. Europe 52°), its ARRL elevation-angle file (.PRN), headings and bands.
   The ARRL .PRN files come with the ARRL Antenna Book and are not included.
3. **Towers**: stacks of antennas from the library (generic HFTA types and JK Antennas models), rotating or fixed,
   stack switching, and for rotating towers the guy and ice check (Phillystran or EHS, radial ice, element droop).
   A height scan finds good heights for one antenna.
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

## Limits
- HFTA's method is validated for 7–30 MHz. Below 7 MHz diffraction is less reliable; above 30 MHz terrain data
  must resolve features of about 1/8 wavelength.
- HFTA has no mutual coupling between stacked antennas; close spacing (under about 0.3 wavelength) is rated
  too well.
- At most 4 antennas of one type per band, as in HFTA.
