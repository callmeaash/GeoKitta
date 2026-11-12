"""Conversion between stored WGS 84 coordinates and UTM 45N metres used for all calculations."""
import json

import numpy as np
from pyproj import Transformer

from app.spatial.geometry import Point, Polygon

_TO_UTM = Transformer.from_crs(4326, 32645, always_xy=True)
_TO_WGS = Transformer.from_crs(32645, 4326, always_xy=True)


def to_utm(lon: float, lat: float) -> Point:
    x, y = _TO_UTM.transform(lon, lat)
    return float(x), float(y)


def to_wgs(x: float, y: float) -> Point:
    lon, lat = _TO_WGS.transform(x, y)
    return float(lon), float(lat)


def line_from_geojson(geojson: str) -> list[Point]:
    """GeoJSON line string (lon/lat) to UTM points."""
    flat = np.array([pt[:2] for pt in json.loads(geojson)["coordinates"]], dtype=float)
    xs, ys = _TO_UTM.transform(flat[:, 0], flat[:, 1])
    return list(zip(xs.tolist(), ys.tolist()))


def polygons_from_geojson(texts: list[str]) -> list[Polygon]:
    """GeoJSON polygons (lon/lat) to UTM rings, transforming all coordinates in one call."""
    parsed = [json.loads(t)["coordinates"] for t in texts]
    rings = [ring for p in parsed for ring in p]
    counts = [len(p) for p in parsed]
    if not rings:
        return []
    flat = np.array([pt[:2] for ring in rings for pt in ring], dtype=float)
    xs, ys = _TO_UTM.transform(flat[:, 0], flat[:, 1])
    out_rings, i = [], 0
    for ring in rings:
        n = len(ring)
        out_rings.append(list(zip(xs[i:i + n].tolist(), ys[i:i + n].tolist())))
        i += n
    polygons, j = [], 0
    for c in counts:
        polygons.append(out_rings[j:j + c])
        j += c
    return polygons
