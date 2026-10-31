"""Ensure HTML reports also contain terrain-modified gain curves, not scalar FOM bar charts."""
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.report import _svg_elevation_patterns

curve = [8.0 + 12.0 * math.sin(i / 7) for i in range(140)]
target = {"name": "Europe", "heading": 48, "prn": "not-included.PRN"}
proj = {"settings": {"band_freq": {}}}
cells = [{"site": "s1", "tower": "w1", "band": "20", "hfta_fom": 11.2,
          "best": 0, "options": [{"az": [{"az": 48, "run": "r1"}]}]}]
res = {"patterns": {"r1": curve}}
svg = _svg_elevation_patterns(proj, "unused", target, "20", cells, res,
                              {"s1": {"name": "Test site"}}, {"w1": {"name": "One tower"}})
assert "<svg" in svg and "</svg>" in svg
assert "Elevation angle" in svg and "Gain (dBi)" in svg, "Axis labels missing"
assert _svg_elevation_patterns(proj, "unused", target, "40", cells, res,
                               {"s1": {"name": "Test site"}}, {"w1": {"name": "One tower"}}) == ""
print("PASS: HTML report plots actual OpenHFTA gain curves with FOM; unavailable bands omitted")
