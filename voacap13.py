"""
VOACAP antenna file (type 13: 360 azimuths x 91 elevations, gains in dBi) built from HFTA patterns
over a full set of terrain profiles. Replaces the HFTASweep + AutoIt route (run HFTA 360 times by GUI
automation) with direct calls to the OpenHFTA core.

Layout (matches HFTASweep output, e.g. ROT20Stack.13):
  6 header lines; then for each azimuth 0..359: the azimuth number followed by 91 values,
  10 per line. Elevation 0 = -99.99; elevations 1..35 from HFTA (integer degrees);
  elevations 36..90 repeat the 35-degree value (HFTA computes only to 35 degrees).

Usage:
  python voacap13.py --profiles DIR --freq 14.2 --heights 138 92 46 --antenna 4-Ele --out ROT20Stack.13
Profiles are found by azimuth in the file name (AZI-25.00.PRO, site-25.PRO, ...). Missing azimuths
take the nearest available profile.
"""
from __future__ import annotations

import argparse
import re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import engine


def find_profiles(folder: str) -> dict:
    out = {}
    for p in Path(folder).iterdir():
        if p.suffix.upper() != ".PRO":
            continue
        m = re.search(r"(\d{1,3}(?:\.\d+)?)(?!.*\d)", p.stem)
        if m:
            out[float(m.group(1)) % 360] = p
    return out


def _one(args):
    az, path, freq, heights, phases, ant, sigma, epsr, diffraction = args
    d, h = engine.parse_profile_text(Path(path).read_text(errors="ignore"))
    p = engine.pattern(d, h, freq, heights, phases, ant, sigma, epsr, diffraction)
    return az, [round(float(p[i * 4 - 1]), 1) for i in range(1, 36)]


def sweep(folder, freq, heights, phases, ant_type, sigma=0.005, epsr=13.0, diffraction=True, workers=None):
    prof = find_profiles(folder)
    if not prof:
        raise SystemExit(f"No .PRO files in {folder}")
    keys = sorted(prof)
    def nearest(az):
        return min(keys, key=lambda k: abs((k - az + 180) % 360 - 180))
    jobs = [(az, str(prof[nearest(az)]), freq, heights, phases, ant_type, sigma, epsr, diffraction) for az in range(360)]
    with ProcessPoolExecutor(workers) as ex:
        return dict(ex.map(_one, jobs, chunksize=6))


def apply_fixed_heading(gains: dict, heading: float, beamwidth: float, floor_db: float = -25.0) -> dict:
    """Fixed (non-rotating) antenna: add a main-lobe azimuth loss, -3 dB at +/- beamwidth/2, floor at
    floor_db (front-to-back). HFTA gives only the vertical pattern; this is an approximation."""
    out = {}
    for az, g in gains.items():
        d = (az - heading + 180) % 360 - 180
        loss = max(-12.0 * (d / beamwidth) ** 2, floor_db)
        out[az] = [round(x + loss, 1) for x in g]
    return out


def write13(gains: dict, path: str, title: str) -> None:
    peak = max(max(v) for v in gains.values())
    lines = [f"HFTA AZI {title}'", " 4     4 parameters", f"{0.0:6.2f}  [ 1] Max Gain dBi...:",
             "  13    [ 2] Antenna Type...: 360 x 91 gain values follow", "  0.0   [ 3] Efficiency (for IONCAP)",
             "0.000  [ 4] Frequency"]
    for az in range(360):
        g = gains[az]
        vals = [-99.99] + g + [g[-1]] * 55          # 91 values: 0..90 degrees
        rows = [vals[i:i + 10] for i in range(0, 91, 10)]
        for k, r in enumerate(rows):
            lead = f"{az:5d}  " if k == 0 else " " * 7
            lines.append(lead + "".join(f"{x:7.2f}" for x in r) + " ")
    Path(path).write_text("\n".join(lines) + "\n")
    print(f"{path}: 360 azimuths, peak {peak:.1f} dBi")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", required=True); ap.add_argument("--freq", type=float, required=True)
    ap.add_argument("--heights", type=float, nargs="+", required=True, help="feet")
    ap.add_argument("--phases", type=int, nargs="*", help="1 or -1 per antenna")
    ap.add_argument("--antenna", default="3-Ele", choices=list(engine.ANTENNA_TYPES))
    ap.add_argument("--sigma", type=float, default=0.005); ap.add_argument("--epsr", type=float, default=13.0)
    ap.add_argument("--no-diffraction", action="store_true"); ap.add_argument("--out", required=True)
    ap.add_argument("--fixed-heading", type=float, help="fixed antenna: add azimuth loss around this heading")
    ap.add_argument("--beamwidth", type=float, help="azimuth beamwidth for --fixed-heading (default from element count)")
    a = ap.parse_args()
    ph = a.phases or [1] * len(a.heights)
    g = sweep(a.profiles, a.freq, a.heights, ph, engine.ANTENNA_TYPES[a.antenna], a.sigma, a.epsr, not a.no_diffraction)
    if a.fixed_heading is not None:
        bw = a.beamwidth or {"Dipole": 90, "2-Ele": 70, "3-Ele": 65, "4-Ele": 60, "5-Ele": 55, "6-Ele": 50, "8-Ele": 45}[a.antenna]
        g = apply_fixed_heading(g, a.fixed_heading, bw)
    title = f'" {a.freq:4.1f} MHz    Ants: {"/".join(f"{h:g}" for h in a.heights)} feet" MHz Yagi {a.antenna}'
    write13(g, a.out, title)


if __name__ == "__main__":
    main()
