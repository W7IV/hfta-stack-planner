"""
Spacing warnings. Not part of HFTA and never changes an HFTA number: it only flags layouts where HFTA is likely
to be optimistic or where antennas may interact.

1. Stack spacing (antennas on the same band). HFTA has no mutual coupling, so it gives every stack the ideal
   stacking gain. Close spacing loses part of it. NEC-2 check (this project, 40 m, average ground):
       4 x 2-el at 0.22 wavelength: 2.2 dB less than ideal;  2 x 4-el at 0.43 wavelength: 0.7 dB;  at 0.47: 0.5 dB.
   red   : spacing below red_wl wavelengths   ("Too close")
   amber : spacing below amber_wl wavelengths ("Close")
2. Vertical gap between antennas that share no band (for example a 40 m Yagi under a tribander). HFTA does not
   model this interaction at all.
   red   : gap below gap_red_ft;  amber : gap below gap_amber_ft
Default limits are in project.SPACING_DEFAULTS and can be changed per project.
"""
from __future__ import annotations
import itertools
from . import antennas as A

NOTE_STACK = ("HFTA has no mutual coupling and gives the full stacking gain at any spacing. "
              "NEC-2 check: 0.22 wavelength lost 2.2 dB, 0.43 wavelength lost 0.7 dB.")
NOTE_GAP = "HFTA does not model interaction between antennas on different bands."

def check(antennas, freq_of, rules):
    """antennas: [{'h', 'el'}]; freq_of(band) -> MHz; rules: spacing settings. Returns a list of warnings, worst first."""
    out = []
    bands = sorted({b for a in antennas for b in A.bands_of(a)}, key=A.BANDS.index)
    for b in bands:
        hs = sorted(a["h"] for a in antennas if b in A.el_of(a))
        lam = A.wavelength_ft(freq_of(b))
        for lo, hi in zip(hs, hs[1:]):
            wl = (hi - lo) / lam
            lvl = "red" if wl < rules["red_wl"] else "amber" if wl < rules["amber_wl"] else None
            if lvl:
                out.append({"level": lvl, "kind": "stack", "band": b, "heights": [lo, hi], "ft": round(hi - lo, 1), "wl": round(wl, 2),
                            "text": f"{b} m: antennas at {lo:g} and {hi:g} ft are {hi - lo:g} ft = {wl:.2f} wavelength apart. "
                                    f"{'Too close' if lvl == 'red' else 'Close'}: HFTA overstates the stacking gain"
                                    f"{' by 1 dB or more' if lvl == 'red' else ', probably by 0.5-1 dB'}."})
    for a, c in itertools.combinations(antennas, 2):
        if set(A.bands_of(a)) & set(A.bands_of(c)): continue
        gap = abs(a["h"] - c["h"])
        lvl = "red" if gap < rules["gap_red_ft"] else "amber" if gap < rules["gap_amber_ft"] else None
        if lvl:
            lo, hi = sorted([a, c], key=lambda x: x["h"])
            out.append({"level": lvl, "kind": "gap", "band": None, "heights": [lo["h"], hi["h"]], "ft": round(gap, 1), "wl": None,
                        "text": f"{A.describe(lo)} at {lo['h']:g} ft and {A.describe(hi)} at {hi['h']:g} ft are only {gap:g} ft apart. "
                                f"{'Too close' if lvl == 'red' else 'Close'}: interaction likely, not modelled by HFTA."})
    return sorted(out, key=lambda w: (w["level"] != "red", w["kind"] != "stack", w["heights"][0]))

def worst(warnings):
    return "red" if any(w["level"] == "red" for w in warnings) else "amber" if warnings else None
