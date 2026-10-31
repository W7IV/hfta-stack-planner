# Third-party components and redistribution notices

The root MIT LICENSE covers original HFTA Stack Planner code and documentation only, to the extent owned by its contributors. It does **not** relicense third-party code, files, map data, models, or data supplied by users.

## OpenHFTA (RioDXGroup)
Source: https://github.com/RioDXGroup/openhfta
License: BSD Zero Clause (0BSD). The build pins commit `7d62e863f1d27372c97df3ac6ef53092fb58bd50`.
The Windows distribution bundles a compiled OpenHFTA library; Docker builds it from source. Upstream 0BSD terms apply. The Windows build already copies upstream LICENSE files into `openhfta/`.

## VOACAP / voacapl
Source: https://github.com/jawatson/voacapl
License: Original U.S. Government VOACAP work is described by NTIA/ITS as not subject to U.S. copyright; J. A. Watson's modifications are made available under CC0 in the upstream `COPYING` file. Build commit: `c12a98b`.
Both distributions bundle a compiled version; preserve the upstream `COPYING` and `AUTHORS` files in distributions. Rights outside the U.S. in portions of the underlying government work may depend on local law.

## Plotly.js
Source: https://github.com/plotly/plotly.js
License: MIT. Copyright (c) 2016-2024 Plotly Technologies Inc., per upstream MIT LICENSE consulted 2026-10-30.
`static/plotly.min.js` is bundled. The full MIT notice must accompany copies; see `licenses/PLOTLY-MIT.txt`. Verify the precise embedded Plotly.js version and component attributions before the next stable release.

## Natural Earth map data
Source: https://www.naturalearthdata.com/
License: Public domain (per Natural Earth terms of use). `static/land110.js` contains geographic map content; confirm its exact data provenance during final release review.
The checked-in map file was converted from world-atlas 2.0.2 and contains a permissive copyright notice for Michael Bostock (2013-2019); preserve the notice embedded at the top of `static/land110.js` in every distribution. Attribution to Natural Earth is optional: "Made with Natural Earth."

## OpenStreetMap map tiles (interactive location picker)\nSource: https://www.openstreetmap.org/\nThe optional map picker displays raster tiles requested directly from OpenStreetMap when the user opens the map. The tiles are not bundled, pre-fetched, or included in project exports; user-visible attribution is provided on the map. Map data © OpenStreetMap contributors, licensed under ODbL, subject to the OpenStreetMap Foundation tile usage policy (https://operations.osmfoundation.org/policies/tiles/). Map viewing reveals the displayed area to OpenStreetMap. The picker code itself is original MIT-licensed HFTA Stack Planner code, not copied from another site.\n\n## ARRL HFTA and arrival-angle files
Original HFTA by R. Dean Straw, N6BV, published by ARRL. Not included in this project. ARRL .PRN elevation-angle files must not be bundled or republished without permission. Private project archives can include user-supplied files; public/shareable exports must omit copyrighted files. This project is not endorsed by ARRL.

## Runtime libraries
Python, Flask, NumPy, openpyxl, tifffile, matplotlib, gunicorn and their transitive dependencies are installed or packaged separately under their individual licenses. The Windows package embeds a Python distribution; a complete binary license inventory, including compiler runtimes and Python packages, should be generated and reviewed before announcing v1.0. This notice is **not** a complete software bill of materials.
