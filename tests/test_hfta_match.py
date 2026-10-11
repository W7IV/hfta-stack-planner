"""Regression test: OpenHFTA core against the original HFTA. tests/data/OUT.PRN was written by the original HFTA
(KK6P rotating-tower terrain, 14.2 MHz, 4-el stack). Every gain at 1-35 degrees must match within 0.1 dB
(HFTA prints one decimal). Run: python tests/test_hfta_match.py"""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import engine
D = Path(__file__).resolve().parent / "data"

def blocks(text):
    out, cur = [], None
    for ln in text.splitlines():
        m = re.match(r'"\s*([\d.]+) MHz\s+Ants: ([\d/.]+) feet"', ln)
        if m: cur = {"freq": float(m.group(1)), "h": [float(x) for x in m.group(2).split("/")], "g": {}}; out.append(cur); continue
        m = re.match(r'"HFTA: (.+)"', ln)
        if m and cur: cur["file"] = m.group(1).strip(); continue
        m = re.match(r'"Antenna: (.+)\."', ln)
        if m and cur: cur["type"] = m.group(1).strip(); continue
        m = re.match(r"\s*(\d+),\s*(-?[\d.]+)", ln)
        if m and cur: cur["g"][int(m.group(1))] = float(m.group(2))
    return out

EXPECTED_BLOCKS, EXPECTED_GAINS = 16, 560   # the reference set as written by the original HFTA

def compare(pattern_fn=None):
    """Returns (n compared, largest difference). Raises AssertionError on any invalid or incomplete data."""
    import math
    pattern_fn = pattern_fn or engine.pattern
    bl = blocks((D / "OUT.PRN").read_text())
    assert len(bl) == EXPECTED_BLOCKS, f"Reference file: {len(bl)} runs parsed, expected {EXPECTED_BLOCKS}"
    worst, n = 0.0, 0
    for b in bl:
        assert b.get("file") and b.get("type") and len(b["g"]) == 35, f"Incomplete reference run: {b.get('file')}, {len(b['g'])} gains"
        d, h = engine.parse_profile_text((D / b["file"]).read_text())
        p = pattern_fn(d, h, b["freq"], b["h"], [1] * len(b["h"]), engine.ANTENNA_TYPES[b["type"]])
        assert len(p) == 140, f"Core returned {len(p)} values, expected 140"
        for e, g in b["g"].items():
            v = float(p[e * 4 - 1])
            assert math.isfinite(v), f"Core returned an invalid value at {e} deg for {b['file']}"
            diff = abs(round(v, 1) - g); worst = max(worst, diff); n += 1
    assert n == EXPECTED_GAINS, f"{n} gains compared, expected {EXPECTED_GAINS}"
    return n, worst

def self_test():
    """The test must FAIL on bad core output. Checked with a fake core: all NaN, one NaN, infinity."""
    import numpy as np
    real = engine.pattern
    for name, bad in (("all NaN", lambda *a, **k: np.full(140, np.nan)),
                      ("one NaN", lambda *a, **k: np.where(np.arange(140) == 39, np.nan, real(*a, **k))),
                      ("infinity", lambda *a, **k: np.where(np.arange(140) == 3, np.inf, real(*a, **k))),
                      ("short output", lambda *a, **k: real(*a, **k)[:100])):
        try: compare(bad)
        except AssertionError: continue
        raise SystemExit(f"Self-test failed: the comparison passed with {name} output")

def main():
    self_test()
    n, worst = compare()
    print(f"{n} gains compared, largest difference {worst:.2f} dB")
    assert worst <= 0.1 + 1e-9, "OpenHFTA does not match the original HFTA"
    print("PASS: matches the original HFTA")

if __name__ == "__main__":
    main()
