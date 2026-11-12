"""Public map API: parcels in view, identify, details, selection, buffer and setback search. No owner data."""
import json
import re
import time
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import SessionLocal, get_session
from app.schemas import (BufferRequest, FeatureOut, IdentifyResult, LookupStats, OutlinesRequest, ParcelDetails,
                         ParcelList, ParcelSummary, PlaceHit, RuleOut, SearchResult, SearchStats,
                         SelectRequest)
from app.search.gazetteer import Gazetteer
from app.spatial.features import FeatureIndex, load_rules
from app.spatial.geometry import polygon_area
from app.spatial.index import QuadtreeIndex, load_polygons
from app.spatial.projection import to_utm, zone_geojson
from app.spatial.queries import identify, in_box, near

router = APIRouter(prefix="/api", tags=["public"])

MAX_VIEW_PARCELS = 6000  # beyond this the map asks the user to zoom in
MAX_VIEW_KM2 = 6.0
MAX_LIST = 5000

_SUMMARY_SQL = text("""
SELECT id, pin, parcel_no, ward_no, map_sheet_code, land_use, parcel_type, registered_area
FROM parcels WHERE id = ANY(:ids) AND status = 'active'
ORDER BY ward_no, map_sheet_code, parcel_no
""")


@lru_cache(maxsize=1)
def gazetteer() -> Gazetteer:
    """Place names for search, loaded once."""
    with SessionLocal() as db:
        return Gazetteer.load(db)


@lru_cache(maxsize=1)
def features() -> FeatureIndex:
    """Roads and rivers, loaded once; they only change when the pipeline reloads the data."""
    with SessionLocal() as db:
        return FeatureIndex.load(db)


def _box(west: float, south: float, east: float, north: float) -> tuple[float, float, float, float]:
    """Lon/lat rectangle to the UTM box around its four corners."""
    corners = [to_utm(x, y) for x, y in ((west, south), (east, south), (east, north), (west, north))]
    xs, ys = [c[0] for c in corners], [c[1] for c in corners]
    return min(xs), min(ys), max(xs), max(ys)


def _stats(index: QuadtreeIndex, t0: float) -> LookupStats:
    return LookupStats(**{k: index.stats.get(k, 0) for k in ("cells", "rows_read", "candidates", "checked")},
                       ms=round((time.perf_counter() - t0) * 1000, 2))


def _summaries(db: Session, ids: list[int]) -> list[ParcelSummary]:
    if not ids:
        return []
    return [ParcelSummary(id=r[0], pin=r[1], kitta=r[2], ward=r[3], map_sheet=r[4], land_use=r[5], parcel_type=r[6],
                          area_m2=float(r[7])) for r in db.execute(_SUMMARY_SQL, {"ids": ids})]


def _parcel_list(db: Session, ids: list[int], stats: LookupStats, zone=None) -> ParcelList:
    rows = _summaries(db, ids[:MAX_LIST])
    return ParcelList(parcels=rows, count=len(ids), total_area_m2=round(sum(p.area_m2 for p in rows), 2),
                      truncated=len(ids) > MAX_LIST, zone=zone, stats=stats)


_OUTLINES_SQL = text("""
SELECT CAST(json_build_object('type', 'FeatureCollection', 'too_many', false, 'stats', CAST(:stats AS json),
  'features', COALESCE(json_agg(json_build_object('type', 'Feature', 'id', id,
    'geometry', CAST(ST_AsGeoJSON(boundary, 6) AS json),
    'properties', json_build_object('pin', pin, 'kitta', parcel_no, 'ward', ward_no, 'land_use', land_use,
      'label', CAST(ST_AsGeoJSON(ST_PointOnSurface(boundary), 6) AS json) -> 'coordinates'))), '[]')) AS text)
FROM parcels WHERE id = ANY(:ids) AND status = 'active'
""")


def _outlines(db: Session, ids: list[int], stats: LookupStats) -> str:
    """GeoJSON FeatureCollection text for the given parcels, built by PostgreSQL."""
    return db.execute(_OUTLINES_SQL, {"ids": ids, "stats": stats.model_dump_json()}).scalar()


@router.get("/parcels/in-view")
def parcels_in_view(west: float, south: float, east: float, north: float, db: Session = Depends(get_session)):
    """GeoJSON outlines of the parcels in the map view, found through the linear quadtree."""
    t0 = time.perf_counter()
    box = _box(west, south, east, north)
    if (box[2] - box[0]) * (box[3] - box[1]) / 1e6 > MAX_VIEW_KM2:
        return {"type": "FeatureCollection", "features": [], "too_many": True, "stats": LookupStats().model_dump()}
    index = QuadtreeIndex(db)
    ids = list(index.candidates(box))
    stats = _stats(index, t0)
    if len(ids) > MAX_VIEW_PARCELS:
        return {"type": "FeatureCollection", "features": [], "too_many": True, "stats": stats.model_dump()}
    body = _outlines(db, ids, stats)
    return Response(body, media_type="application/json")


@router.post("/parcels/outlines")
def parcel_outlines(req: OutlinesRequest, db: Session = Depends(get_session)):
    """Outlines of listed parcels (e.g. search results), so they can be drawn at any zoom."""
    return Response(_outlines(db, req.ids, LookupStats()), media_type="application/json")


@router.get("/parcels/at", response_model=IdentifyResult)
def parcel_at(lat: float, lng: float, tolerance: float = Query(1.5, ge=0, le=25),
              db: Session = Depends(get_session)):
    """The parcel under a clicked point: linear quadtree candidates, then ray casting."""
    t0 = time.perf_counter()
    index = QuadtreeIndex(db)
    pid = identify(index, to_utm(lng, lat), tolerance)
    stats = _stats(index, t0)
    found = _summaries(db, [pid]) if pid is not None else []
    return IdentifyResult(parcel=found[0] if found else None, stats=stats)


def _find_parcels(db: Session, q: str) -> list[ParcelSummary]:
    """Parcels by PIN, by kitta number, or by ward and kitta ("4/123" or "ward 4 kitta 123")."""
    q = q.strip().upper()
    if q.startswith("KTM"):
        sql, params = "pin LIKE :p", {"p": q.replace("%", "").replace("_", "") + "%"}
    elif m := re.fullmatch(r"(?:WARD\s*)?(\d{1,2})\s*(?:/|-|\s+KITTA\s*|\s+)\s*(\d{1,5})", q):
        sql, params = "ward_no = :w AND parcel_no = :k", {"w": int(m[1]), "k": int(m[2])}
    elif m := re.fullmatch(r"(?:KITTA\s*)?(\d{1,5})", q):
        sql, params = "parcel_no = :k", {"k": int(m[1])}
    else:
        return []
    ids = db.execute(text(f"SELECT id FROM parcels WHERE status = 'active' AND {sql} "
                          "ORDER BY ward_no, map_sheet_code LIMIT 20"), params).scalars().all()
    return _summaries(db, list(ids))


@router.get("/parcels/search", response_model=list[ParcelSummary])
def search_parcels(q: str = Query(min_length=1, max_length=40), db: Session = Depends(get_session)):
    """Parcels by PIN, by kitta number, or by ward and kitta."""
    return _find_parcels(db, q)


@router.get("/search", response_model=SearchResult)
def search(q: str = Query(min_length=1, max_length=80), db: Session = Depends(get_session)):
    """Places by fuzzy name (Levenshtein, BK-tree) and parcels by number, with a "did you mean" suggestion."""
    t0 = time.perf_counter()
    found = gazetteer().search(q)
    places = [PlaceHit(id=p.id, name=p.name, name_ne=p.name_ne, kind=p.kind, ward=p.ward, lng=p.lng, lat=p.lat,
                       distance=m.distance, edits=m.score) for p, m in found]
    suggestion = places[0].name if places and places[0].edits >= 1 else None  # best match needed real edits
    stats = SearchStats(vocabulary=gazetteer().index.stats.get("vocabulary", 0),
                        comparisons=gazetteer().index.stats.get("comparisons", 0),
                        ms=round((time.perf_counter() - t0) * 1000, 2))
    return SearchResult(places=places, parcels=_find_parcels(db, q), suggestion=suggestion, stats=stats)


@router.get("/parcels/{parcel_id}", response_model=ParcelDetails)
def parcel_details(parcel_id: int, db: Session = Depends(get_session)):
    """Public details of an active parcel, with the setback zones it lies in."""
    row = db.execute(text("""
        SELECT id, pin, parcel_no, ward_no, map_sheet_code, land_use, parcel_type, registered_area, status,
               geometry_source, accuracy_m, ST_AsGeoJSON(boundary, 7),
               ST_AsGeoJSON(ST_PointOnSurface(boundary), 7)
        FROM parcels WHERE id = :id AND status = 'active'
    """), {"id": parcel_id}).one_or_none()
    if row is None:
        raise HTTPException(404, "parcel not found")
    polygon = load_polygons(db, [parcel_id])[parcel_id]
    return ParcelDetails(
        id=row[0], pin=row[1], kitta=row[2], ward=row[3], map_sheet=row[4], land_use=row[5], parcel_type=row[6],
        area_m2=float(row[7]), status=row[8], geometry_source=row[9],
        accuracy_m=float(row[10]) if row[10] is not None else None,
        boundary_area_m2=round(polygon_area(polygon), 2),
        setbacks=features().setbacks(polygon, load_rules(db)),
        centre=tuple(json.loads(row[12])["coordinates"]), geometry=json.loads(row[11]))


@router.post("/parcels/select", response_model=ParcelList)
def select_parcels(req: SelectRequest, db: Session = Depends(get_session)):
    """Parcels touching a rectangle, or crossed by a line."""
    t0 = time.perf_counter()
    index = QuadtreeIndex(db)
    if req.box is not None:
        ids = in_box(index, _box(*req.box))
    else:
        ids = near(index, [([to_utm(*p) for p in req.line], 0.0)])
    return _parcel_list(db, ids, _stats(index, t0))


@router.post("/parcels/buffer", response_model=ParcelList)
def buffer_parcels(req: BufferRequest, db: Session = Depends(get_session)):
    """Parcels within a distance of a point, a drawn line, or a road or river (optionally by its setback rule)."""
    t0 = time.perf_counter()
    if req.feature_id is not None:
        feature = features().features.get(req.feature_id)
        if feature is None:
            raise HTTPException(404, "feature not found")
        rule = next((r for r in load_rules(db) if r.id == req.rule_id), None) if req.rule_id else None
        if req.rule_id and (rule is None or rule.feature_type != feature.type):
            raise HTTPException(422, "that setback rule does not apply to this feature")
        group = features().group(feature) if req.whole_feature else [feature]
        lines = [(f.line, rule.zone(f) if rule else req.distance_m) for f in group]
    elif req.point is not None:
        lines = [([to_utm(*req.point)], req.distance_m)]
    else:
        lines = [([to_utm(*p) for p in req.line], req.distance_m)]
    index = QuadtreeIndex(db)
    ids = near(index, lines)
    stats = _stats(index, t0)
    return _parcel_list(db, ids, stats, zone=zone_geojson(lines))


@router.get("/features/nearest", response_model=FeatureOut)
def nearest_feature(lat: float, lng: float, types: str = "highway,road,river,stream,power_line",
                    max_distance: float = Query(60, gt=0, le=500), db: Session = Depends(get_session)):
    """The road or river nearest a clicked point, with every way of the same name."""
    found = features().nearest(to_utm(lng, lat), set(types.split(",")), max_distance)
    if found is None:
        raise HTTPException(404, "no road or river near this point")
    feature, distance = found
    group = features().group(feature)
    geometry = db.execute(text("SELECT ST_AsGeoJSON(ST_Collect(geom), 7) FROM features WHERE id = ANY(:ids)"),
                          {"ids": [f.id for f in group]}).scalar()
    return FeatureOut(id=feature.id, name=feature.name, feature_type=feature.type, width_m=feature.width,
                      ways=len(group), distance_m=round(distance, 1), geometry=json.loads(geometry))


@router.get("/setback-rules", response_model=list[RuleOut])
def setback_rules(db: Session = Depends(get_session)):
    return [RuleOut(id=r.id, feature_type=r.feature_type, distance_m=r.distance, measured_from=r.measured_from,
                    source=r.source, note=r.note) for r in load_rules(db)]
