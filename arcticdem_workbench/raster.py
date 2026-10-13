from __future__ import annotations
import math
import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import reproject, transform_bounds, transform_geom
from rasterio.windows import Window, from_bounds
from pyproj import Proj, Transformer
from shapely.geometry import mapping, Polygon
from .common import check_cancel, sha256, write_json, tls_bundle
from .catalog import item_times, image_ids, validate_bbox
from .http_range import RangeOpener

MAX_CELLS = 12_000_000
REMOTE_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff",
              "GDAL_HTTP_CONNECTTIMEOUT": "15", "GDAL_HTTP_TIMEOUT": "45", "GDAL_HTTP_MAX_RETRY": "2", "GDAL_HTTP_RETRY_DELAY": "1"}

def remote_env():
    options=dict(REMOTE_ENV)
    candidate=tls_bundle()
    options.update(GDAL_HTTP_CAINFO=candidate,CURL_CA_BUNDLE=candidate)
    return options

@dataclass
class Grid:
    transform: object
    crs: object
    width: int
    height: int

    @property
    def shape(self):
        return self.height, self.width

    @property
    def bounds(self):
        return rasterio.transform.array_bounds(self.height, self.width, self.transform)

    def profile(self):
        return dict(driver="GTiff", width=self.width, height=self.height, count=1,
                    crs=self.crs, transform=self.transform, dtype="float32", nodata=-9999.0,
                    compress="deflate", tiled=True, blockxsize=256, blockysize=256, BIGTIFF="IF_SAFER")

def write_raster(path, data, grid, dtype="float32", nodata=-9999.0, tags=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = grid.profile()
    profile.update(dtype=dtype, nodata=nodata)
    tmp = path.with_suffix(".partial.tif")
    with rasterio.open(tmp, "w", **profile) as dst:
        out = np.where(np.isfinite(data), data, nodata).astype(dtype)
        dst.write(out, 1)
        if tags:
            dst.update_tags(**{k: str(v) for k, v in tags.items()})
    tmp.replace(path)

def clip_asset(url, bbox, output, log=print, cancel=None):
    """Read a native-resolution COG window. No up/downsampling before quality masking."""
    check_cancel(cancel)
    output = Path(output)
    signature = hashlib.sha256(json.dumps([url, bbox], sort_keys=True).encode()).hexdigest()
    sidecar = output.with_suffix(".cache.json")
    if output.exists() and sidecar.exists():
        cached = json.loads(sidecar.read_text(encoding="utf-8"))
        if cached.get("signature") == signature and sha256(output) == cached.get("sha256"):
            log(f"Reused verified clip: {output.name}")
            return str(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # The Python opener honours the same verified TLS/proxy context as STAC queries.
    # It reads bounded HTTP ranges, never rasterio.open(file_like) which can copy an entire asset.
    name='remote_'+hashlib.sha256(url.encode()).hexdigest()[:16]+'.tif'
    with rasterio.Env(**remote_env()), rasterio.open(name,opener=RangeOpener(url,name,cancel)) as src:
        if not src.crs or src.transform.b != 0 or src.transform.d != 0:
            raise ValueError("A georeferenced north-up raster is required.")
        b = transform_bounds("EPSG:4326", src.crs, *validate_bbox(bbox), densify_pts=41)
        w = from_bounds(*b, transform=src.transform)
        left, top = max(0, math.floor(w.col_off)), max(0, math.floor(w.row_off))
        right, bottom = min(src.width, math.ceil(w.col_off+w.width)), min(src.height, math.ceil(w.row_off+w.height))
        if right <= left or bottom <= top:
            raise ValueError("AOI does not intersect this raster.")
        if (right-left)*(bottom-top) > MAX_CELLS:
            raise ValueError("Native clip exceeds 12 million pixels. Use a smaller AOI for this first release.")
        win = Window(left, top, right-left, bottom-top)
        log(f"Reading COG window {int(win.width)} x {int(win.height)}: {output.name}")
        data = src.read(1, window=win)
        check_cancel(cancel)
        grid = Grid(src.window_transform(win), src.crs, int(win.width), int(win.height))
        write_raster(output, data, grid, dtype=str(data.dtype), nodata=src.nodata,
                     tags={"source_url": url, "aoi_bbox_wgs84": json.dumps(bbox), "crop_only": True})
    write_json(sidecar, {"signature": signature, "sha256": sha256(output), "url": url, "bbox": bbox})
    return str(output)

def download_items(items, bbox, directory, log=print, cancel=None):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    entries, failures = [], []
    for item in items:
        check_cancel(cancel)
        root = directory / item["id"]
        root.mkdir(exist_ok=True)
        write_json(root / "source_item.json", item)
        paths = {}
        try:
            for key, fname in (("dem", "dem.tif"), ("mask", "bitmask.tif"), ("matchtag", "matchtag.tif")):
                asset = item.get("assets", {}).get(key)
                if not asset:
                    raise ValueError(f"Required quality asset missing: {key}")
                paths[key] = clip_asset(asset["href"], bbox, root/fname, log, cancel)
        except InterruptedError:
            raise
        except Exception as exc:
            failures.append({"id": item["id"], "error": str(exc)})
            log(f"FAILED {item['id']}: {exc}")
            write_json(directory/"epochs.json", {"bbox": bbox, "epochs": entries, "failures": failures})
            continue
        start, end = item_times(item)
        entry = {"id": item["id"], "date": start, "end_date": end, "image_ids": sorted(image_ids(item)),
                 "dem": paths["dem"], "mask": paths["mask"], "matchtag": paths["matchtag"],
                 "vertical_datum": "WGS84 ellipsoidal height (PGC native)", "units": "m", "source_item": str(root/"source_item.json")}
        entries.append(entry)
        write_json(directory/"epochs.json", {"bbox": bbox, "epochs": entries, "failures": failures})
    if not entries:
        raise RuntimeError("No complete DEM + quality-mask clip was downloaded. Inspect download errors.")
    return {"bbox": bbox, "epochs": entries, "failures": failures}

def make_grid(entries, resolution=2.0, bbox=None):
    if not 2 <= float(resolution) <= 100:
        raise ValueError("Output grid resolution must be between 2 and 100 metres.")
    crs = rasterio.crs.CRS.from_epsg(3413)
    if bbox:
        bounds = transform_bounds(4326, crs, *validate_bbox(bbox), densify_pts=81)
    else:
        extents = []
        for e in entries:
            with rasterio.open(e["dem"]) as src:
                if not src.crs:
                    raise ValueError(f"Missing horizontal CRS: {e['dem']}")
                extents.append(transform_bounds(src.crs, crs, *src.bounds, densify_pts=41))
        bounds = (max(b[0] for b in extents), max(b[1] for b in extents), min(b[2] for b in extents), min(b[3] for b in extents))
    l, b, r, t = bounds
    if l >= r or b >= t:
        raise ValueError("No common raster bounding extent. Specify a smaller shared AOI.")
    l, b, r, t = math.floor(l/resolution)*resolution, math.floor(b/resolution)*resolution, math.ceil(r/resolution)*resolution, math.ceil(t/resolution)*resolution
    width, height = round((r-l)/resolution), round((t-b)/resolution)
    if width*height > MAX_CELLS or width*height*len(entries) > 40_000_000:
        raise ValueError("AOI/stack exceeds the first-release memory cap. Crop further or use a coarser processing grid.")
    return Grid(from_origin(l, t, resolution, resolution), crs, width, height)

def read_to_grid(path, grid, categorical=False):
    dest = np.full(grid.shape, np.nan, dtype="float32")
    with rasterio.open(path) as src:
        reproject(source=rasterio.band(src, 1), destination=dest,
                  src_transform=src.transform, src_crs=src.crs, src_nodata=src.nodata,
                  dst_transform=grid.transform, dst_crs=grid.crs, dst_nodata=np.nan,
                  resampling=Resampling.nearest if categorical else Resampling.bilinear)
    return dest

def load_epoch(entry, grid, require_match=True):
    """Mask at native resolution before bilinear reprojection to prevent cloud/nodata bleed."""
    with rasterio.open(entry["dem"]) as src:
        bounds = transform_bounds(grid.crs, src.crs, *grid.bounds, densify_pts=41)
        w = from_bounds(*bounds, transform=src.transform)
        l, t = max(0, math.floor(w.col_off)-2), max(0, math.floor(w.row_off)-2)
        r, b = min(src.width, math.ceil(w.col_off+w.width)+2), min(src.height, math.ceil(w.row_off+w.height)+2)
        if r <= l or b <= t:
            return np.full(grid.shape, np.nan, dtype="float32")
        if (r-l)*(b-t) > 30_000_000:
            raise ValueError("Native read window is too large. Crop the local input first.")
        win = Window(l, t, r-l, b-t)
        arr = src.read(1, window=win, masked=True).astype("float32").filled(np.nan)
        native = Grid(src.window_transform(win), src.crs, r-l, b-t)
        if entry.get("mask"):
            mask = read_to_grid(entry["mask"], native, categorical=True)
            arr[~np.isfinite(mask) | (mask != 0)] = np.nan
        if require_match and entry.get("matchtag"):
            match = read_to_grid(entry["matchtag"], native, categorical=True)
            arr[~np.isfinite(match) | (match != 1)] = np.nan
        dest = np.full(grid.shape, np.nan, dtype="float32")
        reproject(arr, dest, src_transform=native.transform, src_crs=native.crs, src_nodata=np.nan,
                  dst_transform=grid.transform, dst_crs=grid.crs, dst_nodata=np.nan, resampling=Resampling.bilinear)
        # Require the entire bilinear support to be valid, not just one contributing pixel.
        support = np.zeros(grid.shape, dtype="float32")
        reproject(np.isfinite(arr).astype("float32"), support, src_transform=native.transform, src_crs=native.crs,
                  dst_transform=grid.transform, dst_crs=grid.crs, dst_nodata=0, resampling=Resampling.bilinear)
        dest[support < 0.999] = np.nan
    return dest

def read_mask(path, grid):
    if not path:
        return np.zeros(grid.shape, dtype=bool)
    path = Path(path)
    if path.suffix.lower() in (".json", ".geojson"):
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
        if obj.get("crs"):
            raise ValueError("GeoJSON masks must be WGS84 longitude/latitude without a legacy CRS member.")
        if obj["type"] == "FeatureCollection":
            geoms = [f["geometry"] for f in obj["features"]]
        elif obj["type"] == "Feature":
            geoms = [obj["geometry"]]
        else:
            geoms = [obj]
        if not geoms or any(g["type"] not in ("Polygon", "MultiPolygon") for g in geoms):
            raise ValueError("Mask GeoJSON requires Polygon or MultiPolygon features.")
        shapes = [(transform_geom(4326, grid.crs, g), 1) for g in geoms]
        return rasterize(shapes, out_shape=grid.shape, transform=grid.transform, fill=0, dtype="uint8").astype(bool)
    values = read_to_grid(path, grid, categorical=True)
    return np.isfinite(values) & (values > 0)

def aoi_mask(bbox, grid, polygon_path=None):
    if polygon_path:
        return read_mask(polygon_path,grid)
    if not bbox:
        return np.ones(grid.shape, dtype=bool)
    w,s,e,n = bbox
    ring = [(x,s) for x in np.linspace(w,e,81)] + [(e,y) for y in np.linspace(s,n,81)] + [(x,n) for x in np.linspace(e,w,81)] + [(w,y) for y in np.linspace(n,s,81)]
    geo = transform_geom(4326, grid.crs, mapping(Polygon(ring)))
    return rasterize([(geo,1)], out_shape=grid.shape, transform=grid.transform, dtype="uint8").astype(bool)

def ground_pixel_areas(grid):
    """Local ellipsoidal area approximation: projected pixel area / local areal scale."""
    # Grid is always EPSG:3413; scale is latitude-dependent and the projection is conformal.
    areas = np.empty(grid.shape, dtype="float32")
    proj = Proj(grid.crs)
    inv = Transformer.from_crs(grid.crs, 4326, always_xy=True)
    xs = grid.transform.c + (np.arange(grid.width)+0.5)*grid.transform.a
    for first in range(0, grid.height, 128):
        rows = np.arange(first, min(first+128, grid.height))
        ys = grid.transform.f+(rows+0.5)*grid.transform.e
        xx, yy = np.meshgrid(xs, ys)
        lon, lat = inv.transform(xx, yy)
        factor = np.asarray(proj.get_factors(lon, lat).areal_scale)
        areas[first:first+len(rows)] = abs(grid.transform.a*grid.transform.e)/factor
    return areas
