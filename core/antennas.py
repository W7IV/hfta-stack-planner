"""
Antenna library. Each model maps amateur bands to the HFTA antenna type used for that band.
HFTA knows only generic Yagis by element count (Dipole, 2-8 el); a multiband model is entered in HFTA as the
generic type for its element count on that band. Manufacturer data (gain, turning radius, weight) is used only by
the optional layers and the guy check, never by the HFTA numbers.
"""
from __future__ import annotations

BAND_FREQ = {"160": 1.83, "80": 3.6, "40": 7.1, "30": 10.12, "20": 14.2, "17": 18.1, "15": 21.2,
             "12": 24.94, "10": 28.4, "6": 50.1}
BANDS = list(BAND_FREQ)

# Free-space gain (dBi) of each HFTA generic type, measured from the core (peak over flat ground minus 6.0 dB).
MODEL_GAIN_DBI = {"Dipole": 2.1, "2-Ele": 5.4, "3-Ele": 6.9, "4-Ele": 8.4, "5-Ele": 9.35, "6-Ele": 10.8, "8-Ele": 11.8}
ELEMENTS_TO_TYPE = {1: "Dipole", 2: "2-Ele", 3: "3-Ele", 4: "4-Ele", 5: "5-Ele", 6: "6-Ele", 7: "6-Ele", 8: "8-Ele"}
BEAMWIDTH = {"Dipole": 90, "2-Ele": 70, "3-Ele": 65, "4-Ele": 60, "5-Ele": 55, "6-Ele": 50, "8-Ele": 45}

def _b(el, dbd=None):
    t = ELEMENTS_TO_TYPE[el]
    return {"elements": el, "hfta_type": t, "gain_dbi": None if dbd is None else round(dbd + 2.14, 2)}

LIBRARY = {
    # generic single-band types (HFTA native)
    **{f"Generic {t}": {"maker": "generic", "bands": "any", "hfta_type": t, "turning_radius_ft": None,
                        "droop_ft": 2.0, "weight_lb": None, "wind_sqft": None, "notes": "HFTA generic type"}
       for t in ("Dipole", "2-Ele", "3-Ele", "4-Ele", "5-Ele", "6-Ele", "8-Ele")},
    "JK Big-Tri": {"maker": "JK Antennas", "bands": {"20": _b(4, 7.0), "15": _b(5, 8.2), "10": _b(7, 9.0)},
                   "turning_radius_ft": 25.4, "droop_ft": 3.0, "weight_lb": 140, "wind_sqft": 22.2,
                   "notes": "10 m has 7 el; HFTA has no 7-el type, 6-Ele used", "source": "https://jkantennas.com/jkbigtri.html"},
    "JK Mid-Tri": {"maker": "JK Antennas", "bands": {"20": _b(3, 5.3), "15": _b(4, 6.9), "10": _b(5, 7.5)},
                   "turning_radius_ft": 22.0, "droop_ft": 2.5, "weight_lb": 98, "wind_sqft": 16.0, "source": "https://jkantennas.com/jkmidtri.html"},
    "JK MidTri-40": {"maker": "JK Antennas", "bands": {"40": _b(2, 4.2), "20": _b(3, 5.3), "15": _b(4, 6.9), "10": _b(5, 7.5)},
                     "turning_radius_ft": 27.7, "droop_ft": 4.0, "weight_lb": 163, "wind_sqft": 24.75, "source": "https://jkantennas.com/jkmidtri.html"},
    "JK 404C": {"maker": "JK Antennas", "bands": {"40": _b(4, 5.26)}, "turning_radius_ft": 31.25, "droop_ft": 5.0,
                "weight_lb": 160, "wind_sqft": 16.8, "source": "https://jkantennas.com/jk404c.html"},
    "JK 404 Grande": {"maker": "JK Antennas", "bands": {"40": _b(4, 6.16)}, "turning_radius_ft": 43.0, "droop_ft": 6.0,
                      "weight_lb": 325, "wind_sqft": 28.05, "source": "https://jkantennas.com/jk404-grande.html"},
    "JK 801-T rigid dipole": {"maker": "JK Antennas", "bands": {"80": _b(1, 0.0)}, "turning_radius_ft": None, "droop_ft": 6.0,
                              "weight_lb": None, "wind_sqft": None, "notes": "weight and size not yet confirmed"},
}

def bands_of(model: str, band_list=None):
    m = LIBRARY[model]
    if m["bands"] == "any":
        return list(band_list or [])
    return list(m["bands"])

def hfta_type(model: str, band: str) -> str:
    m = LIBRARY[model]
    return m["hfta_type"] if m["bands"] == "any" else m["bands"][band]["hfta_type"]

def gain_correction_db(model: str, band: str):
    """Layer: manufacturer free-space gain minus the HFTA generic type's gain. None when unknown."""
    m = LIBRARY[model]
    if m["bands"] == "any":
        return 0.0
    g = m["bands"][band]["gain_dbi"]
    return None if g is None else round(g - MODEL_GAIN_DBI[hfta_type(model, band)], 2)

def public_library():
    return {k: {**v, "bands": v["bands"] if v["bands"] == "any" else {b: dict(x) for b, x in v["bands"].items()}} for k, v in LIBRARY.items()}
