# HFTA Stack Planner

Web interface for the OpenHFTA terrain-analysis core (port of N6BV's HFTA).
Purpose: choose antenna heights and evaluate Yagi stacks by Figure of Merit (FOM)
over the arrival angles of one or more paths.

## Features
- **Bands**: one band, or several bands on the same physical heights (preset: tribander 20-15-10).
  Each band has its own frequency, element count, boom length and weight. On a tribander, enter
  the elements and electrical boom length that are active on each band.
- **Band matrix**: FOM of every antenna sub-group on every band, side by side.
- **Trade-off matrix** (optimiser): best overall, best for each band, and the top results, with the
  loss on each band against that band's best. Band weight sliders re-rank all results instantly.
- **Search modes**: free spacing, equal spacing (bottom height + one spacing), or both with the
  cost of equal spacing in dB.
- **Limits**: minimum spacing in wavelengths of the lowest band (default 0.5 λ), maximum tower height.
- **Geometry table**: heights and spacings in wavelengths per band, and spacing ÷ boom length.
  Boom length is information only; the core does not use it.
- 1 to 4 antennas of one type (Dipole, 2-6 and 8 elements); height and phase (0°/180°) for each.
- One or more paths. Each path = terrain profile (.PRO) + ARRL arrival-angle file (.PRN) + weight.
- **Analyse stack**: pattern and FOM of the full stack, each antenna alone, and every sub-group.
  Δ column shows the change against the best single antenna.
- **Optimise heights**: searches height ranges (any antenna can be held fixed) with a step and
  minimum spacing. Ranks by weighted FOM over all paths. Shows the best result, top 15, a FOM map,
  and the height range that stays within 0.5 dB of the best.
  Large searches (> 500 combinations) use a coarse grid first, then a fine grid near the 5 best.
- Warning when the frequency is outside 7–30 MHz (method less reliable) or the .PRN file lacks the band.

## Limits (from the calculation core)
- All antennas in a stack are the same type. Max 4. Phase 0° or 180° only.
- Horizontal polarisation only. Terrain profile max 148 points.
- About 0.25 s per pattern per path on one processor. Calculations run in parallel processes.

## Run (Linux)
```
git clone https://github.com/RioDXGroup/openhfta.git ../openhfta
cd ../openhfta && make            # needs gfortran
cd ../hfta-gui
pip install -r requirements.txt
python app.py                      # open http://localhost:5000
```
Environment: `OPENHFTA_DIR` (default `../openhfta`), `OPENHFTA_LIB` (path to the core library),
`HFTA_WORKERS` (processes, default = CPU count), `PORT`.

The Fortran core is not thread-safe (COMMON blocks). Never call it from threads; use processes.

## Files
- `engine.py` — wrapper around the core: parsing, pattern, FOM, height grids. Numerics unchanged.
- `app.py` — Flask routes `/api/analyse`, `/api/optimise`, `/api/job/<id>`.
- `templates/index.html`, `static/app.js`, `static/style.css` — interface. `static/plotly.min.js` is
  bundled so the page works offline.
- `samples/` — two terrain profiles from the OpenHFTA test set and `TEST-ONLY-synthetic.PRN`.
  The .PRN is invented data for testing only. Use the ARRL Antenna Book files for real work.
