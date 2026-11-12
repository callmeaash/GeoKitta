"""Parcel validation on save: valid polygon, overlaps (quadtree + exact check), area mismatch and slivers."""
import json
import math
from dataclasses import asdict, dataclass, field

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from app.spatial.geometry import Point, Polygon, box_of, interiors_overlap, perimeter, polygon_area, ring_problem
from app.spatial.index import QuadtreeIndex
from app.spatial.projection import to_utm, to_wgs

AREA_TOLERANCE = 0.05  # boundary area may differ from the registered area by 5%; the planted mismatches are 8-20%
SLIVER_WIDTH_M = 1.0  # mean width 2A/P below this is a sliver (a 0.35 m strip has about 0.35 m)
MIN_OVERLAP_M2 = 0.1  # smaller shared areas are rounding noise along shared edges
MAX_POINTS = 500

FAIL, WARN, PASS = "fail", "warn", "pass"


class InputError(ValueError):
    """The coordinates cannot be turned into a polygon at all."""


@dataclass
class Check:
    id: str
    status: str
    title: str
    detail: str = ""


@dataclass
class Overlap:
    parcel_id: int
    pin: str
    kitta: int
    area_m2: float
    geometry: dict | None = None  # the shared area, for drawing in red


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)
    overlaps: list[Overlap] = field(default_factory=list)
    area_m2: float = 0.0
    perimeter_m: float = 0.0
    candidates: int = 0  # parcels the quadtree returned for the overlap check

    @property
    def ok(self) -> bool:
        return all(c.status != FAIL for c in self.checks)

    @property
    def clean(self) -> bool:
        return all(c.status == PASS for c in self.checks)

    def as_dict(self) -> dict:
        return {**asdict(self), "ok": self.ok, "clean": self.clean}


def polygon_from_points(points: list[list[float]], crs: str) -> Polygon:
    """Survey corners (UTM metres or lon/lat) to a closed UTM ring, rounded the way it will be stored."""
    if not 3 <= len(points) <= MAX_POINTS:
        raise InputError(f"a boundary needs 3 to {MAX_POINTS} corner points")
    try:
        pts = [(float(p[0]), float(p[1])) for p in points]
    except (TypeError, ValueError, IndexError):
        raise InputError("every point needs two numbers") from None
    if not all(math.isfinite(v) for p in pts for v in p):
        raise InputError("coordinates must be numbers")
    if crs == "wgs84":
        if not all(-180 <= x <= 180 and -90 <= y <= 90 for x, y in pts):
            raise InputError("longitude/latitude out of range; are these UTM metres?")
        lonlat = pts
    elif crs == "utm":
        if not all(100_000 <= x <= 900_000 and 0 <= y <= 10_000_000 for x, y in pts):
            raise InputError("easting/northing out of range for UTM 45N; are these longitude/latitude?")
        lonlat = [to_wgs(x, y) for x, y in pts]
    else:
        raise InputError("crs must be utm or wgs84")
    lonlat = [(round(x, 7), round(y, 7)) for x, y in lonlat]  # storage precision, about 1 cm
    if lonlat[0] != lonlat[-1]:
        lonlat.append(lonlat[0])  # close the ring
    return [[to_utm(x, y) for x, y in lonlat]]


def to_geojson(polygon: Polygon) -> dict:
    return {"type": "Polygon", "coordinates": [[list(to_wgs(x, y)) for x, y in ring] for ring in polygon]}


def to_ewkt(polygon: Polygon) -> str:
    rings = ", ".join("(" + ", ".join(f"{lon:.7f} {lat:.7f}" for lon, lat in (to_wgs(x, y) for x, y in ring)) + ")"
                      for ring in polygon)
    return f"SRID=4326;POLYGON({rings})"


def check_polygon(polygon: Polygon) -> Check:
    problem = ring_problem(polygon[0])
    if problem:
        return Check("polygon", FAIL, "Boundary is not a valid polygon", problem[0].upper() + problem[1:] + ".")
    return Check("polygon", PASS, "Valid polygon", f"Closed ring with {len(polygon[0]) - 1} corners, no self-crossing.")


def check_area(area: float, registered: float | None) -> Check:
    if not registered:
        return Check("area", PASS, "Area calculated", f"{area:,.1f} m² enclosed by the boundary.")
    diff = (area - registered) / registered
    text_ = f"Boundary {area:,.1f} m² vs registered {registered:,.1f} m² ({diff:+.1%})."
    if abs(diff) > AREA_TOLERANCE:
        return Check("area", WARN, "Area does not match the registered area", text_)
    return Check("area", PASS, "Area matches the registered area", text_)


def check_shape(area: float, perim: float) -> Check:
    width = 2 * area / perim if perim else 0
    circ = 4 * math.pi * area / perim ** 2 if perim else 0
    detail = f"Mean width {width:.2f} m, circularity {circ:.2f}."
    if width < SLIVER_WIDTH_M:  # circularity alone also flags long roadside strips, so it is reported only
        return Check("sliver", WARN, "Very thin parcel (possible sliver)", detail)
    return Check("sliver", PASS, "Shape is not a sliver", detail)


def overlap_areas(db: Session | Connection, polygon: Polygon, ids: list[int]) -> dict[int, tuple[float, dict]]:
    """Shared area with each listed parcel, for the report; measured by PostGIS, decided by our own test."""
    if not ids:
        return {}
    rows = db.execute(text("""
        SELECT id, ST_Area(ST_Transform(x, 32645)), ST_AsGeoJSON(x, 7) FROM (
          SELECT id, ST_Intersection(boundary, ST_GeomFromEWKT(:g)) AS x FROM parcels WHERE id = ANY(:ids)) s
    """), {"g": to_ewkt(polygon), "ids": ids}).all()
    return {r[0]: (float(r[1]), json.loads(r[2])) for r in rows}


def find_overlaps(db: Session | Connection, polygon: Polygon, exclude: set[int]) -> tuple[list[Overlap], int]:
    """Active parcels sharing area with the polygon: quadtree candidates, then the hand-written exact test."""
    index = QuadtreeIndex(db)
    boxes = index.candidates(box_of(polygon[0]))
    ids = [pid for pid in boxes if pid not in exclude]
    hits = [pid for pid, other in index.polygons(ids).items() if interiors_overlap(polygon, other)]
    areas = overlap_areas(db, polygon, hits)
    keep = [pid for pid in hits if areas[pid][0] >= MIN_OVERLAP_M2]
    rows = db.execute(text("SELECT id, pin, parcel_no FROM parcels WHERE id = ANY(:i)"), {"i": keep})
    names = {r[0]: r[1:] for r in rows}
    found = [Overlap(pid, names[pid][0], names[pid][1], round(areas[pid][0], 2), areas[pid][1]) for pid in keep]
    return found, len(ids)


def validate(db: Session | Connection, polygon: Polygon, registered: float | None, exclude: set[int] = frozenset(),
             overlaps: bool = True) -> Report:
    """All checks for one boundary. `exclude` holds parcels it may overlap (itself, or the parent of a split)."""
    report = Report()
    report.checks.append(check_polygon(polygon))
    if not report.ok:
        return report
    report.area_m2 = round(polygon_area(polygon), 2)
    report.perimeter_m = round(perimeter(polygon), 2)
    if overlaps:
        report.overlaps, report.candidates = find_overlaps(db, polygon, set(exclude))
        if report.overlaps:
            names = ", ".join(f"kitta {o.kitta} ({o.area_m2:,.1f} m²)" for o in report.overlaps)
            report.checks.append(Check("overlap", FAIL, "Overlaps existing parcels", f"Shares area with {names}."))
        else:
            report.checks.append(Check("overlap", PASS, "No overlap with neighbouring parcels",
                                       f"{report.candidates} nearby parcels checked; shared edges only touch."))
    report.checks.append(check_area(report.area_m2, registered))
    report.checks.append(check_shape(report.area_m2, report.perimeter_m))
    return report


def centre_lonlat(polygon: Polygon) -> Point:
    b = box_of(polygon[0])
    return to_wgs((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
