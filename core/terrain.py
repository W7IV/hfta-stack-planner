"""
Terrain profiles for candidate tower sites. Four sources:
  1. MicroDEM .PRO files (the classic HFTA workflow): one file per azimuth.
  2. K6TU terrain sets (https://www.k6tu.net): HFTA-ready .PRO files, typically one per degree.
  3. Generated here from a DEM file (GeoTIFF or ESRI ASCII grid) on the user's own computer.
  4. Fetched automatically from USGS 3DEP (US coverage) given only lat/lon.
Imported files are stored unchanged under the site folder, so the replay pack points to the same files the user
would load into HFTA. Generated files use the HFTA .PRO format: first line 'meters', then 'distance elevation'.
"""
from __future__ import annotations
import hashlib, io, math, os, re, shutil, urllib.request, uuid, zipfile
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

MAX_PRO_BYTES = 200_000          # a 148-point profile is a few kB
MAX_ZIP_MEMBERS = 5000
MAX_ZIP_TOTAL = 200_000_000

def _plain_name(name: str):
    """File name only (no folder), and only characters that are safe in a path. None if unusable."""
    n = re.split(r"[\\/]", name)[-1]
    return n if re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.\- ]{0,120}", n) and ".." not in n else None

def import_files(site_dir: Path, files) -> dict:
    """files: iterable of (filename, bytes). Accepts .PRO files and .zip archives of them.
    A file for a heading the site already has replaces the old file of that heading (reported as 'replaced'),
    so each heading has exactly one profile."""
    site_dir.mkdir(parents=True, exist_ok=True)
    added, skipped, replaced = [], [], []
    def take(name, data):
        name = _plain_name(name)
        if not name or not name.lower().endswith(".pro"):
            return
        az = azimuth_from_name(name)
        try:
            engine.parse_profile_text(data.decode("latin-1"))
        except Exception as e:
            skipped.append(f"{name}: {e}"); return
        if az is None:
            skipped.append(f"{name}: no azimuth in the file name"); return
        for old in site_dir.glob("*"):
            if old.suffix.lower() == ".pro" and old.name != name and azimuth_from_name(old.name) == az:
                old.unlink(); replaced.append(old.name)
        (site_dir / name).write_bytes(data); added.append(name)
    for name, data in files:
        if name.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                infos = [i for i in z.infolist() if not i.is_dir()]
                if len(infos) > MAX_ZIP_MEMBERS or sum(i.file_size for i in infos) > MAX_ZIP_TOTAL:
                    raise ValueError("The zip is too large (too many files or too many bytes when unpacked)")
                for i in infos:
                    if not i.filename.lower().endswith(".pro"): continue       # never unpack other files
                    if i.file_size > MAX_PRO_BYTES: skipped.append(f"{i.filename}: too large for a profile"); continue
                    take(i.filename, z.read(i))
        else:
            take(name, data)
    return {"added": added, "skipped": skipped, "replaced": replaced}

def file_digest(site_dir: Path, name: str) -> str:
    """SHA-256 of a terrain file's bytes: part of every run key, so a changed file is never matched to old results."""
    return hashlib.sha256((site_dir / name).read_bytes()).hexdigest()[:16]

def _swap_in(out_dir: Path, stage: Path):
    """Replace the .PRO set in out_dir by the files in stage. The old set is kept until the new set is complete."""
    old = out_dir.parent / f".old-{out_dir.name}-{uuid.uuid4().hex[:6]}"
    out_dir.mkdir(parents=True, exist_ok=True); old.mkdir()
    for p in list(out_dir.glob("*")):
        if p.suffix.lower() == ".pro": os.replace(p, old / p.name)
    try:
        for p in stage.glob("*"): os.replace(p, out_dir / p.name)
    except BaseException:
        for p in out_dir.glob("*"):
            if p.suffix.lower() == ".pro" and not (old / p.name).exists(): p.unlink()
        for p in old.glob("*"): os.replace(p, out_dir / p.name)
        raise
    finally:
        shutil.rmtree(old, ignore_errors=True); shutil.rmtree(stage, ignore_errors=True)

def _stage_dir(out_dir: Path) -> Path:
    d = out_dir.parent / f".stage-{out_dir.name}-{uuid.uuid4().hex[:6]}"; d.mkdir(parents=True); return d

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
                page = tf.pages[0]
                if page.shape and int(np.prod(page.shape)) > 60_000_000:
                    raise ValueError(f"DEM too large ({' x '.join(map(str, page.shape))} pixels). Cut it to the area around the site.")
                self.z = page.asarray().astype(np.float64)
                tags = {t.name: t.value for t in page.tags.values()}
                sx, sy = tags["ModelPixelScaleTag"][:2]; tp = tags["ModelTiepointTag"]
                self.x0, self.y0, self.dx, self.dy = tp[3] - tp[0] * sx, tp[4] + tp[1] * sy, sx, sy
                nod = tags.get("GDAL_NODATA")
                self.nodata = float(nod) if nod not in (None, "") else None
                gk = tags.get("GeoKeyDirectoryTag")
                keys = {gk[i]: gk[i + 3] for i in range(4, len(gk), 4)} if gk is not None else {}
                if keys.get(1025) == 2:
                    # GTRasterTypeGeoKey = RasterPixelIsPoint: the tie point is the centre of its pixel, not its corner.
                    self.x0 -= sx / 2; self.y0 += sy / 2
                if crs is None and gk is not None:
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
    """Write one .PRO per azimuth. Distances 0..length in steps of spacing (at most 148 points, HFTA limit).
    The new set replaces the existing .PRO files only when every profile has been written, so a failure leaves the
    old set as it was and the folder always holds one consistent set."""
    for v, what, lo_, hi_ in ((az_step, "Azimuth step", 0.1, 90), (spacing_m, "Point spacing", 1, 1000), (length_m, "Profile length", 100, 100000)):
        if not (np.isfinite(v) and lo_ <= v <= hi_): raise ValueError(f"{what} must be {lo_}..{hi_}")
    dist = np.arange(0, length_m + 0.1, spacing_m)[:148]
    if np.isnan(dem.sample([lat], [lon])[0]):
        raise ValueError("The site is outside the DEM, or the DEM has no data at the site.")
    # Write the new set to a staging folder; the existing profiles stay in place until every new one is written.
    stage = _stage_dir(out_dir); written, short = [], []
    try:
        for az in np.arange(0, 360, az_step):
            la, lo = _destination(lat, lon, az, dist); z = dem.sample(la, lo)
            good = ~np.isnan(z)
            if not good[0]:
                raise ValueError("The site is outside the DEM, or the DEM has no data at the site.")
            n = int(np.argmin(good)) if not good.all() else len(z)
            if n < 2:
                raise ValueError(f"At azimuth {az:g}° the DEM has data only at the site itself. Use a larger DEM.")
            if n < len(z): short.append(float(az))
            name = f"{prefix}-AZI-{az:.2f}.PRO"
            body = "meters\n" + "".join(f"{d:12.0f} {e:8.1f}\n" for d, e in zip(dist[:n], z[:n]))
            engine.parse_profile_text(body)
            (stage / name).write_text(body); written.append(name)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True); raise
    _swap_in(out_dir, stage)
    return {"written": len(written), "spacing_m": spacing_m, "length_m": float(dist[-1]), "short_azimuths": short,
            "ground_elevation_m": round(float(dem.sample([lat], [lon])[0]), 1)}

def write_flat(out_dir: Path, prefix: str = "FLAT"):
    """Replace the site's whole terrain set by flat ground (one profile per degree)."""
    out_dir.mkdir(parents=True, exist_ok=True); stage = _stage_dir(out_dir)
    body = "meters\n" + "".join(f"{d:12.0f} {0.0:8.1f}\n" for d in range(0, 4410, 30))
    for az in range(0, 360, 1):
        (stage / f"{prefix}-AZI-{az}.00.PRO").write_text(body)
    _swap_in(out_dir, stage)

# ---------------- USGS 3DEP online fetch ----------------
_3DEP_URL = (
    "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
    "?bbox={west},{south},{east},{north}&bboxSR=4326&imageSR=4326&size=1024,1024"
    "&format=tiff&pixelType=F32&noDataInterpretation=esriNoDataMatchAny"
    "&interpolation=RSP_BilinearInterpolation&f=image"
)
# imageSR=4326 matters: without it the service returns the image in its own projection (metres), and the
# lat/lon sampling then finds no data at the site.

def fetch_dem_and_generate(lat: float, lon: float, out_dir: Path, prefix: str,
                           az_step: float = 1.0, spacing_m: float = 30.0, length_m: float = 4410.0) -> dict:
    """Download a GeoTIFF patch from USGS 3DEP (United States incl. Alaska and Hawaii; no key needed),
    centred on lat/lon and large enough for the profile length, then call generate_from_dem.
    The temporary DEM file is deleted afterwards."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Latitude must be -90..90 and longitude -180..180 (decimal degrees, west negative).")
    # Half-size of the box in degrees: profile length plus a margin, converted from metres.
    half_m = length_m * 1.25 + 500
    buf_lat = half_m / 111_320.0
    buf_lon = buf_lat / max(0.15, math.cos(math.radians(lat)))
    west, east = lon - buf_lon, lon + buf_lon
    south, north = lat - buf_lat, lat + buf_lat
    url = _3DEP_URL.format(west=west, south=south, east=east, north=north)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir.parent / f"dem_fetch-{out_dir.name}.tif"   # one temp file per site, so two sites can run at once
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hfta-stack-planner/1.0"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            ctype = resp.headers.get("Content-Type", "")
            data = resp.read()
        if "tiff" not in ctype.lower():
            # The service answers errors as JSON with HTTP 200.
            msg = data[:300].decode("utf-8", "replace")
            raise ValueError(f"USGS 3DEP did not return a DEM ({ctype}): {msg}")
        tmp.write_bytes(data)
        dem = DEM(tmp, crs="geographic")
        # 3DEP marks no-data with a very large negative number and the tag is not always present.
        dem.z[(dem.z < -1000) | (dem.z > 20000)] = np.nan
        if np.isnan(dem.z).all():
            raise ValueError("USGS 3DEP has no elevation data here. The service covers the United States only.")
        # Check the returned image is where we asked for it, and say exactly what came back if not.
        H, W = dem.z.shape; x1, y1 = dem.x0 + W * dem.dx, dem.y0 - H * dem.dy
        if not (dem.x0 <= lon <= x1 and y1 <= lat <= dem.y0) or abs(dem.x0) > 180 or abs(dem.y0) > 90:
            raise ValueError(f"USGS 3DEP returned an image that does not cover the site: image x {dem.x0:.5f}..{x1:.5f}, "
                             f"y {y1:.5f}..{dem.y0:.5f}, pixel {dem.dx:.6g} x {dem.dy:.6g}; site {lat:.5f}, {lon:.5f}.")
        z0 = float(dem.sample([lat], [lon])[0])
        if z0 != z0:
            raise ValueError(f"USGS 3DEP has no data at the site itself ({lat:.5f}, {lon:.5f}), only around it. "
                             "Try a position a few metres away.")
        result = generate_from_dem(dem, lat, lon, out_dir, prefix, az_step, spacing_m, length_m)
        result["source"] = "USGS 3DEP (online)"
        return result
    finally:
        if tmp.exists():
            tmp.unlink()
