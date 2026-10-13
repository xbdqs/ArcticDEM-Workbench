from __future__ import annotations
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from pyproj import Transformer
from shapely.geometry import box, shape
from shapely.ops import transform
from . import __version__
from .common import check_cancel, parse_date, utc_now, write_csv, write_json, tls_bundle

API = "https://stac.pgc.umn.edu/api/v1"
COLLECTION = "arcticdem-strips-s2s041-2m"

def validate_bbox(bbox):
    if len(bbox) != 4:
        raise ValueError("AOI requires west, south, east, north in decimal degrees.")
    w, s, e, n = map(float, bbox)
    if not (-180 <= w < e <= 180 and -90 < s < n < 90):
        raise ValueError("Use west < east and south < north; split AOIs crossing the date line.")
    return [w, s, e, n]

def request_json(url, method="GET", body=None, cancel=None):
    for attempt in range(3):
        check_cancel(cancel)
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                     headers={"User-Agent": f"ArcticDEM-Workbench/{__version__}", "Accept": "application/geo+json, application/json", "Content-Type": "application/json"}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=35,context=ssl.create_default_context(cafile=tls_bundle())) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError) as exc:
            if isinstance(exc, urllib.error.HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == 2:
                raise
            time.sleep(attempt + 1)

def image_ids(item):
    ids = item.get("properties", {}).get("pgc:image_ids") or []
    if not ids:
        ids = re.findall(r"(?<![A-F0-9])[A-F0-9]{16}(?![A-F0-9])", item["id"])
    return set(ids)

def item_times(item):
    p = item["properties"]
    start = p.get("start_datetime") or p.get("datetime")
    end = p.get("end_datetime") or start
    if not start:
        raise ValueError(f"Missing acquisition date: {item['id']}")
    return start, end

def search(bbox, start="2007-01-01", end=None, max_items=500, include_xtrack=False,
           log=print, cancel=None, page_size=100):
    bbox = validate_bbox(bbox)
    end = end or date.today().isoformat()
    if parse_date(start) > parse_date(end):
        raise ValueError("Start date must precede end date.")
    if not 1 <= max_items <= 10000:
        raise ValueError("Query cap must be between 1 and 10,000 records.")
    args = {"collections": COLLECTION, "bbox": ",".join(map(str, bbox)),
            "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z", "limit": min(page_size, max_items), "sortby": "datetime"}
    url = API + "/search?" + urllib.parse.urlencode(args)
    items, seen, pages, next_link = [], set(), 0, None
    scanned = []
    while url and len(scanned) < max_items:
        check_cancel(cancel)
        data = request_json(url, cancel=cancel)
        pages += 1
        for item in data.get("features", []):
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            scanned.append(item)
            if include_xtrack or not item["properties"].get("pgc:is_xtrack", False):
                items.append(item)
            if len(scanned) >= max_items:
                break
        log(f"Query page {pages}: {len(scanned)} records scanned, {len(items)} retained.")
        next_link = next((x for x in data.get("links", []) if x["rel"] == "next"), None)
        url = next_link["href"] if next_link else None
        if next_link and next_link.get("method", "GET") != "GET":
            raise RuntimeError("Unexpected STAC pagination method; save the error log for an interface update.")
        if pages > max_items + 1:
            raise RuntimeError("Repeated STAC pagination; query stopped.")
    snapshot = {"type": "FeatureCollection", "features": items,
                "workbench": {"queried_utc": utc_now(), "api": API, "collection": COLLECTION,
                              "bbox": bbox, "start": start, "end": end, "include_xtrack": include_xtrack,
                              "scanned_count": len(scanned), "returned_count": len(items),
                              "query_cap": max_items, "truncated": bool(next_link),
                              "excluded_xtrack_count": len(scanned)-len(items),
                              "next_url": url, "coverage_semantics": "Footprints only; valid pixel overlap is not yet tested."}}
    return snapshot

def item_rows(snapshot):
    rows = []
    bbox = snapshot.get("workbench", {}).get("bbox")
    project = Transformer.from_crs(4326, 3413, always_xy=True).transform
    aoi = transform(project, box(*bbox)) if bbox else None
    for f in snapshot["features"]:
        p = f["properties"]
        start, end = item_times(f)
        fraction = None
        if aoi and f.get("geometry"):
            from shapely import make_valid
            geom = transform(project, make_valid(shape(f["geometry"])))
            fraction = max(0.0, min(1.0, geom.intersection(aoi).area / aoi.area))
        rows.append({"id": f["id"], "start": start, "end": end,
                     "cross_track": bool(p.get("pgc:is_xtrack", False)),
                     "image_ids": ";".join(sorted(image_ids(f))),
                     "footprint_aoi_fraction": round(fraction, 4) if fraction is not None else "",
                     "source_valid_fraction": p.get("pgc:valid_area_percent", ""),
                     "source_matchtag_density": p.get("pgc:valid_area_matchtag_density", ""),
                     "sensor": ";".join(p.get("instruments", [])), "dem_url": f.get("assets", {}).get("dem", {}).get("href", "")})
    return rows

def save_snapshot(snapshot, path):
    write_json(path, snapshot)
    write_csv(Path(path).with_suffix(".csv"), item_rows(snapshot))

def dependency_warnings(items):
    warnings = []
    for i, left in enumerate(items):
        for right in items[i+1:]:
            shared = image_ids(left) & image_ids(right)
            if shared:
                warnings.append(f"Shared source imagery: {left['id']} / {right['id']}: {', '.join(sorted(shared))}")
            if item_times(left)[0][:10] == item_times(right)[0][:10]:
                warnings.append(f"Same acquisition day: {left['id']} / {right['id']}")
    return warnings
