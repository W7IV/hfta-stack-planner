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

def main():
    worst, n = 0.0, 0
    for b in blocks((D / "OUT.PRN").read_text()):
        d, h = engine.parse_profile_text((D / b["file"]).read_text())
        p = engine.pattern(d, h, b["freq"], b["h"], [1] * len(b["h"]), engine.ANTENNA_TYPES[b["type"]])
        for e, g in b["g"].items():
            diff = abs(round(float(p[e * 4 - 1]), 1) - g); worst = max(worst, diff); n += 1
    print(f"{n} gains compared, largest difference {worst:.2f} dB")
    assert worst <= 0.1 + 1e-9, "OpenHFTA does not match the original HFTA"
    print("PASS: matches the original HFTA")

if __name__ == "__main__":
    main()
