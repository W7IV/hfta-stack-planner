"""Compare two elevation-angle (.PRN) files, band by band: mean angle, histogram overlap, and, what matters for the
planner, the HFTA FOM difference they give for the same antennas. Usage:
    python tools/compare_prn.py reference.PRN candidate.PRN [--terrain tests/data/AZI-30.00.PRO]
The ARRL files are not part of this repository; give their path."""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import engine

HEIGHTS = [([40], "40 ft"), ([70], "70 ft"), ([100], "100 ft"), ([130], "130 ft"), ([160], "160 ft"), ([60, 120], "60/120 ft"), ([50, 100, 150], "50/100/150 ft")]

def table(path):
    lines = Path(path).read_text(errors="ignore").splitlines()
    bands = lines[1].split()[1:]
    rows = {}
    for ln in lines[2:]:
        p = ln.split()
        if len(p) == len(bands) + 1:
            try: rows[int(p[0])] = [float(x) for x in p[1:]]
            except ValueError: pass
    return [b.rstrip("m") for b in bands], rows

def stats(bands, rows, b):
    k = bands.index(b); v = np.array([rows[a][k] for a in sorted(rows)]); a = np.array(sorted(rows))
    tot = v.sum()
    return (float((a * v).sum() / tot) if tot else float("nan")), v / tot if tot else v

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("ref"); ap.add_argument("cand"); ap.add_argument("--terrain", default=None)
    ap.add_argument("--el", type=int, default=4); a = ap.parse_args()
    if a.terrain: d, h = engine.parse_profile_text(Path(a.terrain).read_text())
    else: d, h = list(np.arange(0, 4410, 30.0) * 3.28084), [0.0] * 147
    rb, rr = table(a.ref); cb, cr = table(a.cand)
    ref_txt, cand_txt = Path(a.ref).read_text(errors="ignore"), Path(a.cand).read_text(errors="ignore")
    print(f"{'band':>5} {'mean ref':>9} {'mean cand':>9} {'overlap':>8} {'offset':>7} {'ranking':>8} {'best ref':>14} {'best cand':>14}")
    print("  offset = mean FOM difference (ref - cand) over the test antennas: a constant shift that does not change a ranking.")
    print("  ranking = largest FOM difference after removing that offset: how far the two files can disagree when comparing antennas.")
    worst = 0.0
    for b in rb:
        if b not in cb: print(f"{b:>5}  (not in candidate)"); continue
        mr, pr = stats(rb, rr, b); mc, pc = stats(cb, cr, b)
        ov = float(np.minimum(pr, pc).sum()) if len(pr) == len(pc) else float("nan")
        f = {"80": 3.6, "40": 7.1, "30": 10.12, "20": 14.2, "17": 18.1, "15": 21.2, "12": 24.94, "10": 28.4}[b]
        ar, ac = engine.parse_aoa(ref_txt, f), engine.parse_aoa(cand_txt, f)
        foms = []
        for hs, name in HEIGHTS:
            pat = engine.pattern(d, h, f, hs, [1] * len(hs), engine.ANTENNA_TYPES[f"{a.el}-Ele"])
            foms.append((name, engine.fom(pat, ar), engine.fom(pat, ac)))
        diffs = np.array([x - y for _, x, y in foms if x is not None and y is not None])
        if not len(diffs): print(f"{b:>5} {mr:9.1f} {mc:9.1f}   (no data in one file)"); continue
        off = float(diffs.mean()); rank = float(np.abs(diffs - off).max()); worst = max(worst, rank)
        best_r = max(foms, key=lambda t: t[1] if t[1] is not None else -1e9)[0]; best_c = max(foms, key=lambda t: t[2] if t[2] is not None else -1e9)[0]
        print(f"{b:>5} {mr:9.1f} {mc:9.1f} {ov:8.2f} {off:+7.2f} {rank:8.2f} {best_r:>14} {best_c:>14}")
    print(f"largest ranking difference over all bands: {worst:.2f} dB")

if __name__ == "__main__":
    main()
