"""Conversion between stored WGS 84 coordinates and UTM 45N metres used for all calculations."""
import json

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import LineString, mapping
from shapely.geometry import Point as ShapelyPoint

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


def zone_geojson(lines: list[tuple[list[Point], float]]) -> dict | None:
    """Outline of the area within each line's distance, in lon/lat, for drawing only (lookups never use it)."""
    shapes = [ShapelyPoint(line[0]).buffer(d, 32) if len(line) == 1 else LineString(line).buffer(d, 8)
              for line, d in lines if d > 0 and line]
    if not shapes:
        return None
    zone = shapely.union_all(shapes).simplify(0.3)
    zone = shapely.transform(zone, lambda xy: np.column_stack(_TO_WGS.transform(xy[:, 0], xy[:, 1])))
    return mapping(shapely.set_precision(zone, 1e-7))
