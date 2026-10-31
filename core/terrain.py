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
import hashlib, io, math, os, re, shutil, time, urllib.error, urllib.request, uuid, zipfile
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
    """azimuth (float) -> file name. When a heading has more than one file (two imports with different name
    prefixes, made before imports replaced same-heading files), the newest file is used: the same rule as an
    import, where the latest file for a heading replaces the older one. duplicates() reports such sites."""
    out, when = {}, {}
    for p in sorted(site_dir.glob("*")):
        if p.suffix.lower() == ".pro":
            az = azimuth_from_name(p.name)
            if az is not None:
                t = p.stat().st_mtime
                if az not in out or t > when[az]:
                    out[az], when[az] = p.name, t
    return out

def set_label(name: str) -> str:
    """The part of a profile file name that is not the azimuth: 'New-ROT-site-' for New-ROT-site-AZI-52.00.PRO,
    '' for AZI-52.00.PRO. Files of one import or fetch share a label."""
    stem = Path(name).stem; m = AZ_RE.search(stem)
    head = (stem[:m.start()] if m else stem).rstrip("-_ ")
    head = re.sub(r"(?i)[-_ ]*azi$", "", head)
    return head.rstrip("-_ ").lower()

def duplicates(site_dir: Path) -> "dict | None":
    """Headings that have more than one profile file. None when every heading has one file. Otherwise
    {"headings": n, "used": {"label", "n", "newest"}, "unused": {"label", "n", "newest"}} where used is the set
    profile_index() chooses (the newest files) and unused the other files."""
    by_az = {}
    for p in site_dir.glob("*"):
        if p.suffix.lower() == ".pro":
            az = azimuth_from_name(p.name)
            if az is not None:
                by_az.setdefault(az, []).append(p)
    dup = {az: ps for az, ps in by_az.items() if len(ps) > 1}
    if not dup:
        return None
    used, unused = {}, {}
    for ps in dup.values():
        ps = sorted(ps, key=lambda p: p.stat().st_mtime)
        for p, bucket in ((ps[-1], used), *((q, unused) for q in ps[:-1])):
            lab = set_label(p.name) or "(no prefix)"; e = bucket.setdefault(lab, {"label": lab, "n": 0, "newest": 0.0, "example": p.name})
            e["n"] += 1; e["newest"] = max(e["newest"], p.stat().st_mtime)
    fmt = lambda d: [{**v, "newest": time.strftime("%Y-%m-%d %H:%M", time.gmtime(v["newest"]))} for v in sorted(d.values(), key=lambda v: -v["n"])]
    return {"headings": len(dup), "used": fmt(used), "unused": fmt(unused)}

def remove_duplicates(site_dir: Path, keep: str) -> int:
    """Delete the other files of every heading that has more than one. keep='newer' keeps the file profile_index()
    uses; keep='older' keeps the oldest file of each heading instead. Returns the number of files deleted."""
    if keep not in ("newer", "older"):
        raise ValueError("keep must be 'newer' or 'older'")
    by_az = {}
    for p in site_dir.glob("*"):
        if p.suffix.lower() == ".pro" and azimuth_from_name(p.name) is not None:
            by_az.setdefault(azimuth_from_name(p.name), []).append(p)
    n = 0
    for ps in by_az.values():
        if len(ps) < 2: continue
        ps = sorted(ps, key=lambda p: p.stat().st_mtime)
        for p in (ps[:-1] if keep == "newer" else ps[1:]):
            p.unlink(); n += 1
    return n

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

def far_horizon(dem, lat: float, lon: float, az_step: float = 5.0, start_m: float = 4410.0, end_m: float = 15000.0,
                step_m: float = 100.0, antenna_m: float = 30.0) -> dict:
    """Terrain beyond the HFTA profile: the highest elevation angle, seen from an antenna antenna_m above the site,
    of ground between start_m and end_m in each direction. HFTA never sees this ground (its profile ends at
    start_m); a value near or above the lowest arrival angles (about 1 degree) means a distant ridge that the
    profiles do not show. Returns {"step": az_step, "deg": [per azimuth], "max_deg", "max_az"} (None where no data)."""
    z0 = float(dem.sample([lat], [lon])[0])
    dist = np.arange(start_m, end_m + 0.1, step_m); out = []
    for az in np.arange(0, 360, az_step):
        la, lo = _destination(lat, lon, az, dist); z = dem.sample(la, lo); ok = ~np.isnan(z)
        if ok.sum() < 3: out.append(None); continue
        ang = np.degrees(np.arctan2(z[ok] - (z0 + antenna_m), dist[ok]))
        out.append(round(float(ang.max()), 2))
    vals = [(v, i) for i, v in enumerate(out) if v is not None]
    best = max(vals) if vals else (None, None)
    return {"step": az_step, "start_m": start_m, "end_m": end_m, "antenna_m": antenna_m, "deg": out,
            "max_deg": best[0], "max_az": None if best[1] is None else float(best[1] * az_step)}

def write_flat(out_dir: Path, prefix: str = "FLAT"):
    """Replace the site's whole terrain set by flat ground (one profile per degree)."""
    out_dir.mkdir(parents=True, exist_ok=True); stage = _stage_dir(out_dir)
    body = "meters\n" + "".join(f"{d:12.0f} {0.0:8.1f}\n" for d in range(0, 4410, 30))
    for az in range(0, 360, 1):
        (stage / f"{prefix}-AZI-{az}.00.PRO").write_text(body)
    _swap_in(out_dir, stage)

class TerrainServiceTemporaryError(Exception):
    """An upstream/network failure that is reasonable for the user to retry, not missing terrain coverage."""


def fetch_terrain_response(req, service: str, timeout: int = 180):
    """Read upstream data, translating temporary HTTP/network failures into a retryable error."""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 429 or 500 <= exc.code <= 599:
            raise TerrainServiceTemporaryError(
                f"{service} temporarily unavailable (HTTP {exc.code}). Please try again shortly."
            ) from exc
        raise ValueError(f"{service} rejected the request (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise TerrainServiceTemporaryError(
            f"{service} could not be reached or timed out. Please try again shortly."
        ) from exc


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
        ctype, data = fetch_terrain_response(req, "USGS 3DEP")
        if "tiff" not in ctype.lower():
            # ArcGIS can return a JSON error with HTTP 200, including transient server errors.
            msg = data[:300].decode("utf-8", "replace")
            low = msg.lower()
            if any(term in low for term in ("temporar", "busy", "timeout", "timed out",
                                             "unavailable", "overload", "internal server error",
                                             '"code":500', '"code": 500', '"code":503', '"code": 503')):
                raise TerrainServiceTemporaryError(
                    "USGS 3DEP temporarily could not provide elevation data. Please try again shortly."
                )
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
        # Far horizon to 15 km from a second, coarse image (30 km across, about 60 m per pixel): enough for the
        # elevation angle of distant ridges, not used for the profiles.
        try:
            fb = 15_500 / 111_320.0; fbl = fb / max(0.15, math.cos(math.radians(lat)))
            url2 = _3DEP_URL.format(west=lon - fbl, south=lat - fb, east=lon + fbl, north=lat + fb).replace("size=1024,1024", "size=512,512")
            ctype2, data2 = fetch_terrain_response(
                urllib.request.Request(url2, headers={"User-Agent": "hfta-stack-planner/1.0"}), "USGS 3DEP"
            )
            if "tiff" in ctype2.lower():
                tmp.write_bytes(data2); far = DEM(tmp, crs="geographic"); far.z[(far.z < -1000) | (far.z > 20000)] = np.nan
                result["far_horizon"] = far_horizon(far, lat, lon, end_m=15000)
        except Exception as e:  # noqa: BLE001  (the horizon is extra information; the profiles are already written)
            result["far_horizon_error"] = str(e)[:200]
        return result
    finally:
        if tmp.exists():
            tmp.unlink()

# ---------------- AWS Terrain Tiles (worldwide) ----------------
# 1 degree x 1 degree tiles in the SRTM .hgt layout (Mapzen/Tilezen "skadi": SRTM worldwide, 3DEP in the US, national
# open DEMs in much of Europe, Canada, Australia and New Zealand, ArcticDEM/GMTED north of 60 degrees). No key, no account.
# Attribution: Tilezen / Mapzen Terrain Tiles; data from the sources listed at github.com/tilezen/joerd.
_TILES_URL = "https://elevation-tiles-prod.s3.amazonaws.com/skadi/{ns}{lat:02d}/{ns}{lat:02d}{ew}{lon:03d}.hgt.gz"
TERRAIN_TILES_SOURCE = "AWS Terrain Tiles (Tilezen; SRTM/3DEP/national DEMs, 30 m)"

def tile_name(lat_floor: int, lon_floor: int) -> str:
    ns, ew = ("N" if lat_floor >= 0 else "S"), ("E" if lon_floor >= 0 else "W")
    return f"{ns}{abs(lat_floor):02d}{ew}{abs(lon_floor):03d}"

def tile_url(lat_floor: int, lon_floor: int) -> str:
    ns, ew = ("N" if lat_floor >= 0 else "S"), ("E" if lon_floor >= 0 else "W")
    return _TILES_URL.format(ns=ns, lat=abs(lat_floor), ew=ew, lon=abs(lon_floor))

class HGT:
    """One .hgt tile: a square grid of 16-bit big-endian metres, 3601 (1 arc-second) or 1201 (3 arc-second) per side,
    first row at the north edge, nodes exactly on the degree lines (the south-west node is the tile's corner)."""
    NODATA = -32768
    def __init__(self, data: bytes, lat_floor: int, lon_floor: int):
        n = int(round(math.sqrt(len(data) / 2)))
        if n * n * 2 != len(data) or n < 2: raise ValueError(f"Not an .hgt tile ({len(data)} bytes)")
        self.n, self.lat0, self.lon0 = n, lat_floor, lon_floor
        z = np.frombuffer(data, dtype=">i2").astype(np.float64).reshape(n, n)
        z[z == self.NODATA] = np.nan; self.z = z
    def sample(self, lat, lon):
        lat, lon = np.asarray(lat, dtype=float), np.asarray(lon, dtype=float); m = self.n - 1
        c = (lon - self.lon0) * m; r = (self.lat0 + 1 - lat) * m
        c0, r0 = np.clip(np.floor(c).astype(int), 0, m - 1), np.clip(np.floor(r).astype(int), 0, m - 1)
        fc, fr = np.clip(c - c0, 0, 1), np.clip(r - r0, 0, 1)
        z = self.z
        return (z[r0, c0] * (1 - fc) * (1 - fr) + z[r0, c0 + 1] * fc * (1 - fr) + z[r0 + 1, c0] * (1 - fc) * fr + z[r0 + 1, c0 + 1] * fc * fr)

class TerrainTiles:
    """A DEM made of .hgt tiles, loaded on demand through `loader(lat_floor, lon_floor) -> bytes or None`.
    Has the same sample(lat, lon) interface as DEM, so generate_from_dem works unchanged."""
    def __init__(self, loader):
        self.loader, self.tiles = loader, {}
    def tile(self, la: int, lo: int):
        k = (la, lo)
        if k not in self.tiles:
            data = self.loader(la, lo)
            self.tiles[k] = HGT(data, la, lo) if data else None
        return self.tiles[k]
    def sample(self, lat, lon):
        lat, lon = np.atleast_1d(np.asarray(lat, dtype=float)), np.atleast_1d(np.asarray(lon, dtype=float))
        lon = ((lon + 180) % 360) - 180
        out = np.full(lat.shape, np.nan)
        la, lo = np.floor(lat).astype(int), np.floor(lon).astype(int)
        for key in set(zip(la.tolist(), lo.tolist())):
            t = self.tile(*key)
            if t is None: continue
            m = (la == key[0]) & (lo == key[1]); out[m] = t.sample(lat[m], lon[m])
        return out

def tiles_needed(lat: float, lon: float, length_m: float) -> list:
    """Tiles that the profiles around (lat, lon) can touch."""
    half = length_m * 1.05 / 111_320.0; half_lon = half / max(0.15, math.cos(math.radians(lat)))
    las = range(int(math.floor(lat - half)), int(math.floor(lat + half)) + 1)
    los = range(int(math.floor(lon - half_lon)), int(math.floor(lon + half_lon)) + 1)
    return [(a, ((b + 180) % 360) - 180) for a in las for b in los if -90 <= a < 90]

def download_tile(la: int, lo: int, cache_dir: Path, timeout: int = 180):
    """The tile's bytes (unpacked), from the cache folder or downloaded. None when the service has no tile there
    (open ocean), which the service answers with 403/404."""
    import gzip, urllib.error
    cache_dir.mkdir(parents=True, exist_ok=True); f = cache_dir / f"{tile_name(la, lo)}.hgt"
    if f.exists(): return f.read_bytes()
    req = urllib.request.Request(tile_url(la, lo), headers={"User-Agent": "hfta-stack-planner/1.0"})
    try:
        _, raw = fetch_terrain_response(req, "Terrain Tiles", timeout=timeout)
    except ValueError as exc:
        if isinstance(exc.__cause__, urllib.error.HTTPError) and exc.__cause__.code in (403, 404):
            return None  # No published terrain tile in this cell (for example, open ocean).
        raise
    data = gzip.decompress(raw)
    if len(data) > 40_000_000: raise ValueError("Terrain tile larger than expected")
    tmp = f.with_suffix(".tmp"); tmp.write_bytes(data); os.replace(tmp, f)
    return data

def fetch_tiles_and_generate(lat: float, lon: float, out_dir: Path, prefix: str, cache_dir: Path,
                             az_step: float = 1.0, spacing_m: float = 30.0, length_m: float = 4410.0) -> dict:
    """Terrain profiles for any place in the world from AWS Terrain Tiles. Tiles are kept in cache_dir (about 25 MB
    each) so a second site in the same degree square needs no download."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Latitude must be -90..90 and longitude -180..180 (decimal degrees, west negative).")
    need = tiles_needed(lat, lon, length_m)
    dem = TerrainTiles(lambda la, lo: download_tile(la, lo, cache_dir))
    for la, lo in need: dem.tile(la, lo)                      # download first, so a network error comes before any writing
    if dem.tile(int(math.floor(lat)), int(math.floor(lon))) is None:
        raise ValueError(f"Terrain Tiles has no data for {tile_name(int(math.floor(lat)), int(math.floor(lon)))} (open sea?).")
    result = generate_from_dem(dem, lat, lon, out_dir, prefix, az_step, spacing_m, length_m)
    result["source"] = TERRAIN_TILES_SOURCE
    for la, lo in tiles_needed(lat, lon, 15000): dem.tile(la, lo)
    result["far_horizon"] = far_horizon(dem, lat, lon, start_m=length_m, end_m=15000)
    result["tiles"] = [tile_name(*k) for k in need if dem.tiles.get(k) is not None]
    result["resolution_m"] = round(30.9 * 3601 / dem.tile(int(math.floor(lat)), int(math.floor(lon))).n, 1)
    return result

def in_usa(lat: float, lon: float) -> bool:
    """Rough test for USGS 3DEP coverage: the 48 states, Alaska and Hawaii."""
    return (24 <= lat <= 49.5 and -125 <= lon <= -66.5) or (51 <= lat <= 72 and (lon <= -129 or lon >= 172)) or (18.5 <= lat <= 22.5 and -161 <= lon <= -154)
