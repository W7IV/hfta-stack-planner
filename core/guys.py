"""
Guy-wire clearance for rotating towers (not part of HFTA). A guy attached at H with anchor radius R is a straight
line when bare; under radial ice it sags (parabolic, constant initial tension: an upper value). An antenna sweeps a
circle of its turning radius r.
  Antenna below a guy:  clearance = iced wire height at r - h - margin            (element droop not credited)
  Antenna above a guy:  clearance = min(h - H - margin, h - droop - bare wire height at r - margin)
"""
import math

WIRES = {  # weight lb/ft, diameter in, default initial tension lb (10% of rated breaking strength)
    "Phillystran HPTG-11200I": (0.070, 0.44, 1120),
    "Phillystran HPTG-6700I": (0.045, 0.34, 670),
    "3/16 EHS steel": (0.073, 0.1875, 399),
    "1/4 EHS steel": (0.121, 0.25, 670),
    "5/16 EHS steel": (0.205, 0.3125, 1120),
}

def sag_at(H, R, r, wire, tension, ice_in, density=56.0):
    wl, d, _ = WIRES[wire]
    wi = math.pi * ((d / 2 + ice_in) ** 2 - (d / 2) ** 2) / 144 * density if ice_in > 0 else 0.0
    c = R / math.hypot(H, R)
    f = ((wl + wi) / c) * R ** 2 / (8 * tension * c)
    x = r / R
    return 4 * f * x * (1 - x)

def check(antennas, levels, ice_in=1.0, margin=2.0, density=56.0):
    """antennas: [{name, h, turning_radius, droop}], levels: [{h, r, wire, tension}]. Returns rows per antenna."""
    out = []
    for a in antennas:
        r, h = a["turning_radius"], a["h"]
        if not r:
            out.append({**a, "clearance": None, "limit": "turning radius unknown", "detail": []}); continue
        detail = []
        for lv in levels:
            H, R = lv["h"], lv["r"]
            bare = H * (1 - r / R)
            iced = bare - sag_at(H, R, r, lv["wire"], lv.get("tension") or WIRES[lv["wire"]][2], ice_in, density)
            if h >= H:
                c = min(h - H - margin, h - (a.get("droop") or 0) * (ice_in > 0) - bare - margin)
                why = f"above the {H:g} ft guy"
            else:
                c = iced - h - margin; why = f"below the {H:g} ft guy (iced wire {iced:.1f} ft at {r:g} ft out)"
            detail.append({"guy_h": H, "anchor_r": R, "bare_wire_ft": round(bare, 1), "iced_wire_ft": round(iced, 1), "clearance": round(c, 1), "why": why})
        worst = min(detail, key=lambda d: d["clearance"]) if detail else None
        out.append({**a, "clearance": worst["clearance"] if worst else None, "limit": worst["why"] if worst else "no guys", "detail": detail})
    return out
