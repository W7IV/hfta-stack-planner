"""
Terrain profiles for candidate tower sites. Three sources:
  1. MicroDEM .PRO files (the classic HFTA workflow): one file per azimuth.
  2. K6TU terrain sets (https://www.k6tu.net): HFTA-ready .PRO files, typically one per degree.
  3. Generated here from a DEM file (GeoTIFF or ESRI ASCII grid) on the user's own computer.
Imported files are stored unchanged under the site folder, so the replay pack points to the same files the user
would load into HFTA. Generated files use the HFTA .PRO format: first line 'meters', then 'distance elevation'.
"""
from __future__ import annotations
import io, math, re, zipfile
from pathlib import Path
import numpy as np
import engine

AZ_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)(?!.*\d)")

def azimuth_from_name(name: str):
    m = AZ_RE.search(Path(name).stem)
    if not m:
        return None
    a = float(m.group(1))
    return a % 360 if a <= 360 else None

def import_files(site_dir: Path, files) -> dict:
    """files: iterable of (filename, bytes). Accepts .PRO files and .zip archives of them."""
    site_dir.mkdir(parents=True, exist_ok=True)
    added, skipped = [], []
    def take(name, data):
        name = Path(name).name
        if not name.lower().endswith(".pro"):
            return
        az = azimuth_from_name(name)
        try:
            engine.parse_profile_text(data.decode("latin-1"))
        except Exception as e:
            skipped.append(f"{name}: {e}"); return
        if az is None:
            skipped.append(f"{name}: no azimuth in the file name"); return
        (site_dir / name).write_bytes(data); added.append(name)
    for name, data in files:
        if name.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for n in z.namelist():
                    if not n.endswith("/"):
                        take(n, z.read(n))
        else:
            take(name, data)
    return {"added": added, "skipped": skipped}

def profile_index(site_dir: Path) -> dict:
    """azimuth (float) -> file name."""
    out = {}
    for p in sorted(site_dir.glob("*")):
        if p.suffix.lower() == ".pro":
            az = azimuth_from_name(p.name)
            if az is not None:
                out[az] = p.name
    return out

def nearest(index: dict, az: float):
    if not index:
        return None, None
    k = min(index, key=lambda a: abs((a - az + 180) % 360 - 180))
    return k, index[k]

def load_profile(site_dir: Path, name: str):
    return engine.parse_profile_text((site_dir / name).read_text(errors="ignore"))

FLAT = (list(np.arange(0, 4410, 30.0) * 3.28084), [0.0] * 147)

# ---------------- terrain summary for comparing sites ----------------
def summary(site_dir: Path, step: int = 5) -> dict:
    """Per azimuth: ground slope over the first 300 m and 1,000 m (positive = falls away), and the terrain horizon
    angle seen from 10 m above the tower base. For comparing sites only; HFTA uses the full profile."""
    idx = profile_index(site_dir); rows = []
    for az in range(0, 360, step):
        k, name = nearest(idx, az)
        if name is None:
            break
        d, h = load_profile(site_dir, name); d = np.array(d) / 3.28084; h = np.array(h) / 3.28084
        h0 = h[0]
        def drop(dist):
            j = np.searchsorted(d, dist)
            return float((h0 - np.interp(dist, d, h)) / dist * 100) if d[-1] >= dist else None
        with np.errstate(divide="ignore", invalid="ignore"):
            ang = np.degrees(np.arctan2(h[1:] - (h0 + 10), d[1:]))
        rows.append({"az": az, "file": name, "slope300": drop(300), "slope1000": drop(1000), "horizon_deg": round(float(np.max(ang)), 2)})
    return {"n_files": len(idx), "azimuths": sorted(idx), "rows": rows}

# ---------------- DEM -> profiles ----------------
def _utm_forward(lat, lon, zone):
    """WGS84/GRS80 lat/lon (deg) -> UTM easting/northing (m), Krueger series (mm accuracy)."""
    a, f = 6378137.0, 1 / 298.257222101; k0 = 0.9996
    n = f / (2 - f); A = a / (1 + n) * (1 + n**2 / 4 + n**4 / 64)
    al = [None, n/2 - 2*n**2/3 + 5*n**3/16, 13*n**2/48 - 3*n**3/5, 61*n**3/240]
    lam0 = math.radians(-183 + 6 * zone); phi = np.radians(lat); lam = np.radians(lon) - lam0
    e = 2 * math.sqrt(n) / (1 + n)
    t = np.sinh(np.arctanh(np.sin(phi)) - e * np.arctanh(e * np.sin(phi)))
    xi = np.arctan2(t, np.cos(lam)); eta = np.arctanh(np.sin(lam) / np.sqrt(1 + t**2))
    E = eta + sum(al[j] * np.cos(2*j*xi) * np.sinh(2*j*eta) for j in (1, 2, 3))
    N = xi + sum(al[j] * np.sin(2*j*xi) * np.cosh(2*j*eta) for j in (1, 2, 3))
    return 500000 + k0 * A * E, k0 * A * N * (1 if np.all(np.asarray(lat) >= 0) else 1) + (0 if np.all(np.asarray(lat) >= 0) else 10000000)

def _destination(lat, lon, az_deg, dist_m):
    R = 6371008.8; p1, l1, b = math.radians(lat), math.radians(lon), np.radians(az_deg); dr = np.asarray(dist_m) / R
    p2 = np.arcsin(math.sin(p1) * np.cos(dr) + math.cos(p1) * np.sin(dr) * np.cos(b))
    l2 = l1 + np.arctan2(np.sin(b) * np.sin(dr) * math.cos(p1), np.cos(dr) - math.sin(p1) * np.sin(p2))
    return np.degrees(p2), np.degrees(l2)

class DEM:
    """Minimal DEM reader. GeoTIFF (north-up, geographic degrees or UTM metres) via tifffile, or ESRI ASCII grid.
    crs: 'geographic' or 'utm:<zone>' (from GeoKeys when present, else given by the user)."""
    def __init__(self, path: Path, crs: str = None, z_units: str = "m"):
        path = Path(path); self.zf = 0.3048 if z_units == "ft" else 1.0
        if path.suffix.lower() in (".tif", ".tiff"):
            import tifffile
            with tifffile.TiffFile(path) as tf:
                page = tf.pages[0]; self.z = page.asarray().astype(np.float64)
                tags = {t.name: t.value for t in page.tags.values()}
                sx, sy = tags["ModelPixelScaleTag"][:2]; tp = tags["ModelTiepointTag"]
                self.x0, self.y0, self.dx, self.dy = tp[3] - tp[0] * sx, tp[4] + tp[1] * sy, sx, sy
                nod = tags.get("GDAL_NODATA")
                self.nodata = float(nod) if nod not in (None, "") else None
                gk = tags.get("GeoKeyDirectoryTag")
                if crs is None and gk is not None:
                    keys = {gk[i]: gk[i + 3] for i in range(4, len(gk), 4)}
                    pcs, gcs = keys.get(3072), keys.get(2048)
                    if pcs and (26901 <= pcs <= 26923 or 32601 <= pcs <= 32660 or 6330 <= pcs <= 6348):
                        crs = f"utm:{pcs % 100 if pcs < 32700 else pcs - 32600}"
                        if 6330 <= pcs <= 6348: crs = f"utm:{pcs - 6330 + 10}"
                    elif gcs and not pcs:
                        crs = "geographic"
        else:   # ESRI ASCII grid
            lines = path.read_text().splitlines(); hdr = {}
            for i in range(6):
                k, v = lines[i].split()[:2]; hdr[k.lower()] = float(v)
            self.z = np.loadtxt(lines[6:]); c = hdr["cellsize"]
            xll = hdr.get("xllcorner", hdr.get("xllcenter", 0) - c / 2); yll = hdr.get("yllcorner", hdr.get("yllcenter", 0) - c / 2)
            self.x0, self.dx, self.dy = xll, c, c; self.y0 = yll + c * self.z.shape[0]; self.nodata = hdr.get("nodata_value")
        if crs is None:
            raise ValueError("Coordinate system not found in the DEM. Give it: 'geographic' or 'utm:<zone>'.")
        self.crs = crs
        if self.nodata is not None:
            self.z[self.z == self.nodata] = np.nan
    def sample(self, lat, lon):
        lat, lon = np.asarray(lat), np.asarray(lon)
        if self.crs == "geographic":
            x, y = lon, lat
        else:
            x, y = _utm_forward(lat, lon, int(self.crs.split(":")[1]))
        c = (x - self.x0) / self.dx - 0.5; r = (self.y0 - y) / self.dy - 0.5
        c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int); fc, fr = c - c0, r - r0
        H, W = self.z.shape
        ok = (c0 >= 0) & (r0 >= 0) & (c0 + 1 < W) & (r0 + 1 < H)
        c0, r0 = np.clip(c0, 0, W - 2), np.clip(r0, 0, H - 2)
        z = (self.z[r0, c0] * (1 - fc) * (1 - fr) + self.z[r0, c0 + 1] * fc * (1 - fr) +
             self.z[r0 + 1, c0] * (1 - fc) * fr + self.z[r0 + 1, c0 + 1] * fc * fr) * self.zf
        return np.where(ok, z, np.nan)

def generate_from_dem(dem: DEM, lat: float, lon: float, out_dir: Path, prefix: str,
                      az_step: float = 1.0, spacing_m: float = 30.0, length_m: float = 4410.0) -> dict:
    """Write one .PRO per azimuth. Distances 0..length in steps of spacing (at most 148 points, HFTA limit)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    dist = np.arange(0, length_m + 0.1, spacing_m)[:148]
    written, short = [], []
    for az in np.arange(0, 360, az_step):
        la, lo = _destination(lat, lon, az, dist); z = dem.sample(la, lo)
        good = ~np.isnan(z)
        if not good[0]:
            raise ValueError("The site is outside the DEM, or the DEM has no data at the site.")
        n = int(np.argmin(good)) if not good.all() else len(z)
        if n < len(z): short.append(float(az))
        name = f"{prefix}-AZI-{az:.2f}.PRO"
        body = "meters\n" + "".join(f"{d:12.0f} {e:8.1f}\n" for d, e in zip(dist[:n], z[:n]))
        (out_dir / name).write_text(body); written.append(name)
    return {"written": len(written), "spacing_m": spacing_m, "length_m": float(dist[-1]), "short_azimuths": short,
            "ground_elevation_m": round(float(dem.sample([lat], [lon])[0]), 1)}

def write_flat(out_dir: Path, prefix: str = "FLAT"):
    out_dir.mkdir(parents=True, exist_ok=True)
    body = "meters\n" + "".join(f"{d:12.0f} {0.0:8.1f}\n" for d in range(0, 4410, 30))
    for az in range(0, 360, 1):
        (out_dir / f"{prefix}-AZI-{az}.00.PRO").write_text(body)
