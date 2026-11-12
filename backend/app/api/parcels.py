"""Officer parcel workflows: register from survey coordinates, update a boundary, split (kitta kaat)."""
import json
from collections import Counter
from fractions import Fraction

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import Officer, current_officer
from app.db import get_session
from app.spatial.geometry import Polygon, box_of, expand, interiors_overlap, polygon_area, within_polygon
from app.spatial.index import QuadtreeIndex, index_parcel, load_polygons, unindex_parcel
from app.validation import (FAIL, PASS, WARN, Check, InputError, Report, polygon_from_points, to_ewkt, to_geojson,
                            validate)

router = APIRouter(prefix="/api/officer/parcels", tags=["officer parcels"], dependencies=[Depends(current_officer)])

DISTRICT, MUNICIPALITY = 27, 2701
SPLIT_AREA_TOLERANCE = 0.01  # children must add up to the parent within 1% (or 0.5 m²)
SOURCES = ("field_survey", "digitized", "synthetic")


class Coordinates(BaseModel):
    points: list[list[float]] = Field(min_length=3, max_length=500)
    crs: str = Field("utm", pattern="^(utm|wgs84)$")


class ShareIn(BaseModel):
    owner_id: int
    share: str = Field(pattern=r"^(1|\d{1,4}/\d{1,4})$")


class CheckRequest(Coordinates):
    registered_area: float | None = Field(None, gt=0)


class RegisterRequest(CheckRequest):
    ward: int = Field(ge=1, le=32)
    map_sheet: str = Field(pattern=r"^\d{9}$")
    kitta: int | None = Field(None, ge=1, le=99999)
    parcel_type: str = Field("private", pattern="^(private|public|government|guthi)$")
    land_use: str = Field("residential", pattern="^(residential|commercial|agricultural|institutional|other)$")
    registered_area: float = Field(gt=0)
    geometry_source: str = Field("field_survey", pattern="^(field_survey|digitized|synthetic)$")
    accuracy_m: float | None = Field(None, gt=0, le=50)
    owners: list[ShareIn] = Field(min_length=1, max_length=20)
    deed_ref: str | None = Field(None, max_length=40)
    remarks: str | None = Field(None, max_length=500)
    accept_issues: bool = Field(False, description="save even though it overlaps another parcel (flagged)")

    @field_validator("owners")
    @classmethod
    def shares_add_up(cls, owners):
        if len({o.owner_id for o in owners}) < len(owners):
            raise ValueError("an owner is listed twice")
        if sum(Fraction(o.share) for o in owners) != 1:
            raise ValueError("the owners' shares must add up to 1")
        return owners


class BoundaryRequest(CheckRequest):
    reason: str = Field("Boundary correction after field survey", max_length=200)
    surveyor: str | None = Field(None, max_length=100)
    geometry_source: str = Field("field_survey", pattern="^(field_survey|digitized|synthetic)$")
    accuracy_m: float | None = Field(None, gt=0, le=50)
    update_registered_area: bool = False
    accept_issues: bool = False


class Child(Coordinates):
    land_use: str | None = Field(None, pattern="^(residential|commercial|agricultural|institutional|other)$")


class SplitRequest(BaseModel):
    children: list[Child] = Field(min_length=2, max_length=10)
    deed_ref: str | None = Field(None, max_length=40)
    remarks: str | None = Field(None, max_length=500)


# ---------- helpers ----------

def _polygon(c: Coordinates) -> Polygon:
    try:
        return polygon_from_points(c.points, c.crs)
    except InputError as e:
        raise HTTPException(422, str(e)) from None


def _active(db: Session, parcel_id: int):
    row = db.execute(text("SELECT id, pin, parcel_no, ward_no, map_sheet_code, registered_area, land_use, parcel_type, "
                          "created_at FROM parcels WHERE id = :id AND status = 'active'"),
                     {"id": parcel_id}).one_or_none()
    if row is None:
        raise HTTPException(404, "no active parcel with this id")
    return row


def _next_kitta(db: Session, ward: int, sheet: str) -> int:
    return db.execute(text("SELECT COALESCE(max(parcel_no), 0) + 1 FROM parcels WHERE municipality_code = :m "
                           "AND ward_no = :w AND map_sheet_code = :s"),
                      {"m": MUNICIPALITY, "w": ward, "s": sheet}).scalar()


def _suggest(db: Session, polygon: Polygon) -> dict:
    """Ward and map sheet of the nearest parcels (within 50 m), and the next free kitta number on that sheet."""
    ids = list(QuadtreeIndex(db).candidates(expand(box_of(polygon[0]), 50)))
    rows = db.execute(text("SELECT ward_no, map_sheet_code FROM parcels WHERE id = ANY(:i)"), {"i": ids}).all()
    if not rows:
        return {"ward": None, "map_sheet": None, "kitta": None}
    ward, sheet = Counter((r[0], r[1]) for r in rows).most_common(1)[0][0]
    return {"ward": ward, "map_sheet": sheet, "kitta": _next_kitta(db, ward, sheet)}


def _new_transaction(db: Session, officer: Officer, txn_type: str, parcel_id: int | None, deed_ref=None,
                     remarks=None) -> tuple[int, str]:
    case_id = str(db.execute(text("SELECT COALESCE(max(CAST(case_id AS bigint)), 2000000) + 1 FROM transactions"))
                  .scalar())
    tid = db.execute(text("""
        INSERT INTO transactions
            (case_id, txn_type, parcel_id, status, deed_ref, deed_date, office, remarks, created_by)
        VALUES (:c, :t, :p, 'approved', :d, current_date, :o, :r, :by) RETURNING id
    """), {"c": case_id, "t": txn_type, "p": parcel_id, "d": deed_ref, "o": officer.office, "r": remarks,
           "by": officer.id}).scalar()
    return tid, case_id


def _record_issues(db: Session, parcel_id: int, report: Report) -> list[str]:
    """Problems the officer chose to save anyway become open issues for review."""
    saved = []
    for o in report.overlaps:
        db.execute(text("INSERT INTO parcel_issues (parcel_id, other_parcel_id, issue_type, severity, details) "
                        "VALUES (:p, :o, 'overlap', 'error', CAST(:d AS jsonb))"),
                   {"p": parcel_id, "o": o.parcel_id,
                    "d": json.dumps({"area_m2": o.area_m2, "geometry": o.geometry, "source": "save"})})
        saved.append(f"overlap with kitta {o.kitta}")
    for c in report.checks:
        if c.status == WARN and c.id in ("area", "sliver"):
            kind = "area_mismatch" if c.id == "area" else "sliver"
            db.execute(text("INSERT INTO parcel_issues (parcel_id, issue_type, severity, details) "
                            "VALUES (:p, :k, 'warning', CAST(:d AS jsonb))"),
                       {"p": parcel_id, "k": kind, "d": json.dumps({"check": c.detail, "source": "save"})})
            saved.append(kind.replace("_", " "))
    return saved


def _audit(db: Session, officer: Officer, action: str, parcel_id: int, tid: int, details: dict) -> None:
    db.execute(text("INSERT INTO audit_log (officer_id, action, parcel_id, transaction_id, details) "
                    "VALUES (:o, :a, :p, :t, CAST(:d AS jsonb))"),
               {"o": officer.id, "a": action, "p": parcel_id, "t": tid, "d": json.dumps(details)})


def _refuse_or_continue(report: Report, accept: bool):
    if any(c.id == "polygon" and c.status == FAIL for c in report.checks):
        raise HTTPException(422, "the boundary is not a valid polygon")
    if not report.ok and not accept:
        return JSONResponse(status_code=409, content={"detail": "the boundary overlaps other parcels",
                                                      "report": report.as_dict()})
    return None


def _insert_parcel(db: Session, polygon: Polygon, ward: int, sheet: str, kitta: int, parcel_type: str,
                   land_use: str, area: float, source: str, accuracy: float | None) -> tuple[int, str]:
    pin = f"KTM-{ward:02d}-{sheet[5:8]}-{kitta:04d}"
    pid = db.execute(text("""
        INSERT INTO parcels (pin, district_code, municipality_code, ward_no, map_sheet_code, parcel_no, parcel_type,
                             land_use, registered_area, status, boundary, geometry_source, accuracy_m)
        VALUES (:pin, :d, :m, :w, :s, :k, :pt, :lu, :a, 'active', ST_GeomFromEWKT(:g), :src, :acc) RETURNING id
    """), {"pin": pin, "d": DISTRICT, "m": MUNICIPALITY, "w": ward, "s": sheet, "k": kitta, "pt": parcel_type,
           "lu": land_use, "a": round(area, 2), "g": to_ewkt(polygon), "src": source, "acc": accuracy}).scalar()
    index_parcel(db, pid, polygon)  # the linear quadtree changes in the same transaction
    return pid, pin


# ---------- register ----------

@router.post("/check")
def check_new(req: CheckRequest, db: Session = Depends(get_session)):
    """Live validation for a new parcel, with the suggested ward, map sheet and kitta number."""
    polygon = _polygon(req)
    report = validate(db, polygon, req.registered_area)
    return {"geometry": to_geojson(polygon), "report": report.as_dict(),
            "suggestion": _suggest(db, polygon) if report.area_m2 else None}


@router.post("", status_code=201)
def register(req: RegisterRequest, db: Session = Depends(get_session), officer: Officer = Depends(current_officer)):
    polygon = _polygon(req)
    report = validate(db, polygon, req.registered_area)
    if (refusal := _refuse_or_continue(report, req.accept_issues)) is not None:
        return refusal
    kitta = req.kitta or _next_kitta(db, req.ward, req.map_sheet)
    taken = db.execute(text("SELECT pin FROM parcels WHERE municipality_code = :m AND ward_no = :w "
                            "AND map_sheet_code = :s AND parcel_no = :k"),
                       {"m": MUNICIPALITY, "w": req.ward, "s": req.map_sheet, "k": kitta}).scalar()
    if taken:
        raise HTTPException(409, f"kitta {kitta} is already used on this map sheet ({taken})")
    found = set(db.execute(text("SELECT id FROM owners WHERE id = ANY(:i)"),
                           {"i": [o.owner_id for o in req.owners]}).scalars())
    if missing := [o.owner_id for o in req.owners if o.owner_id not in found]:
        raise HTTPException(422, f"unknown owner ids: {missing}")

    tid, case_id = _new_transaction(db, officer, "registration", None, req.deed_ref, req.remarks)
    pid, pin = _insert_parcel(db, polygon, req.ward, req.map_sheet, kitta, req.parcel_type, req.land_use,
                              req.registered_area, req.geometry_source, req.accuracy_m)
    db.execute(text("UPDATE transactions SET parcel_id = :p WHERE id = :t"), {"p": pid, "t": tid})
    for o in req.owners:
        f = Fraction(o.share)
        db.execute(text("INSERT INTO parcel_ownership (parcel_id, owner_id, share_num, share_den, valid_from, "
                        "acquired_txn_id) VALUES (:p, :o, :n, :d, current_date, :t)"),
                   {"p": pid, "o": o.owner_id, "n": f.numerator, "d": f.denominator, "t": tid})
    issues = _record_issues(db, pid, report)
    _audit(db, officer, "parcel_registered", pid, tid, {"pin": pin, "case_id": case_id, "area_m2": report.area_m2,
                                                        "issues": issues})
    db.commit()
    return {"parcel_id": pid, "pin": pin, "kitta": kitta, "case_id": case_id, "issues": issues}


# ---------- boundary update ----------

@router.post("/{parcel_id}/boundary/check")
def check_boundary(parcel_id: int, req: CheckRequest, db: Session = Depends(get_session)):
    row = _active(db, parcel_id)
    polygon = _polygon(req)
    report = validate(db, polygon, req.registered_area or float(row[5]), exclude={parcel_id})
    old = load_polygons(db, [parcel_id])[parcel_id]
    return {"geometry": to_geojson(polygon), "old_geometry": to_geojson(old),
            "old_area_m2": round(polygon_area(old), 2), "report": report.as_dict()}


@router.post("/{parcel_id}/boundary")
def update_boundary(parcel_id: int, req: BoundaryRequest, db: Session = Depends(get_session),
                    officer: Officer = Depends(current_officer)):
    row = _active(db, parcel_id)
    polygon = _polygon(req)
    registered = req.registered_area if req.update_registered_area and req.registered_area else float(row[5])
    report = validate(db, polygon, registered, exclude={parcel_id})
    if (refusal := _refuse_or_continue(report, req.accept_issues)) is not None:
        return refusal
    old = load_polygons(db, [parcel_id])[parcel_id]
    remarks = req.reason + (f"; surveyor: {req.surveyor}" if req.surveyor else "")
    tid, case_id = _new_transaction(db, officer, "boundary_update", parcel_id, None, remarks)
    db.execute(text("""
        INSERT INTO parcel_geometry_history (parcel_id, boundary, area_m2, valid_from, valid_to, transaction_id)
        SELECT id, boundary, :area,
               COALESCE((SELECT max(valid_to) FROM parcel_geometry_history WHERE parcel_id = :id), created_at),
               now(), :t
        FROM parcels WHERE id = :id
    """), {"id": parcel_id, "area": round(polygon_area(old), 2), "t": tid})
    db.execute(text("UPDATE parcels SET boundary = ST_GeomFromEWKT(:g), registered_area = :a, geometry_source = :s, "
                    "accuracy_m = :acc, updated_at = now() WHERE id = :id"),
               {"g": to_ewkt(polygon), "a": round(registered, 2), "s": req.geometry_source, "acc": req.accuracy_m,
                "id": parcel_id})
    index_parcel(db, parcel_id, polygon)  # replaces the old quadkeys in the same transaction
    issues = _record_issues(db, parcel_id, report)
    _audit(db, officer, "boundary_updated", parcel_id, tid,
           {"pin": row[1], "case_id": case_id, "old_area_m2": round(polygon_area(old), 2),
            "new_area_m2": report.area_m2, "issues": issues})
    db.commit()
    return {"parcel_id": parcel_id, "pin": row[1], "case_id": case_id, "issues": issues}


# ---------- split (kitta kaat) ----------

def _check_split(db: Session, parent_id: int, req: SplitRequest) -> tuple[list[Polygon], list[Report], list[Check]]:
    _active(db, parent_id)
    parent = load_polygons(db, [parent_id])[parent_id]
    children = [_polygon(c) for c in req.children]
    reports = [validate(db, c, None, exclude={parent_id}) for c in children]
    checks = []
    bad = [n + 1 for n, r in enumerate(reports) if any(c.id == "polygon" and c.status == FAIL for c in r.checks)]
    checks.append(Check("children_valid", FAIL if bad else PASS,
                        "Children are valid polygons" if not bad else "Some children are not valid polygons",
                        f"Child {', '.join(map(str, bad))} must be fixed." if bad else
                        "Closed rings, single parts, no self-crossing."))
    if bad:
        return children, reports, checks
    pairs = [(i + 1, j + 1) for i in range(len(children)) for j in range(i + 1, len(children))
             if interiors_overlap(children[i], children[j])]
    checks.append(Check("children_apart", FAIL if pairs else PASS,
                        "Children overlap each other" if pairs else "Children do not overlap each other",
                        "; ".join(f"child {a} and {b}" for a, b in pairs) if pairs
                        else "They only share boundary lines."))
    outside = [n + 1 for n, c in enumerate(children) if not within_polygon(c, parent)]
    checks.append(Check("inside_parent", FAIL if outside else PASS,
                        "Children go outside the parent" if outside else "Children lie inside the parent",
                        f"Child {', '.join(map(str, outside))} crosses the parent boundary." if outside else
                        "Every corner is inside or on the parent boundary."))
    total, whole = sum(r.area_m2 for r in reports), polygon_area(parent)
    gap = total - whole
    ok = abs(gap) <= max(0.5, SPLIT_AREA_TOLERANCE * whole)
    checks.append(Check("areas_add_up", PASS if ok else FAIL,
                        "Children add up to the parent" if ok else "Children do not add up to the parent",
                        f"{total:,.2f} m² of {whole:,.2f} m² ({gap:+.2f} m²)."))
    hits = sorted({o.kitta for r in reports for o in r.overlaps})
    checks.append(Check("neighbours", FAIL if hits else PASS,
                        "Children overlap neighbouring parcels" if hits else "No overlap with neighbouring parcels",
                        f"Kitta {', '.join(map(str, hits))}." if hits else "Checked with the linear quadtree."))
    return children, reports, checks


@router.post("/{parcel_id}/split/check")
def check_split(parcel_id: int, req: SplitRequest, db: Session = Depends(get_session)):
    children, reports, checks = _check_split(db, parcel_id, req)
    row = _active(db, parcel_id)
    first = _next_kitta(db, row[3], row[4])
    return {"ok": all(c.status != FAIL for c in checks), "checks": [c.__dict__ for c in checks],
            "children": [{"geometry": to_geojson(c), "area_m2": r.area_m2, "kitta": first + n, "report": r.as_dict()}
                         for n, (c, r) in enumerate(zip(children, reports))]}


@router.post("/{parcel_id}/split", status_code=201)
def split(parcel_id: int, req: SplitRequest, db: Session = Depends(get_session),
          officer: Officer = Depends(current_officer)):
    children, reports, checks = _check_split(db, parcel_id, req)
    if any(c.status == FAIL for c in checks):
        return JSONResponse(status_code=409, content={"detail": "the split did not pass validation",
                                                      "checks": [c.__dict__ for c in checks]})
    if db.execute(text("SELECT 1 FROM rokka WHERE parcel_id = :p AND fukuwa_date IS NULL"), {"p": parcel_id}).first():
        raise HTTPException(409, "the parcel is on hold (rokka); release it before splitting")
    row = _active(db, parcel_id)
    owners = db.execute(text("SELECT id, owner_id, share_num, share_den FROM parcel_ownership "
                             "WHERE parcel_id = :p AND valid_to IS NULL"), {"p": parcel_id}).all()
    tid, case_id = _new_transaction(db, officer, "split", parcel_id, req.deed_ref, req.remarks)
    db.execute(text("UPDATE parcels SET status = 'retired', updated_at = now() WHERE id = :p"), {"p": parcel_id})
    unindex_parcel(db, parcel_id)
    db.execute(text("UPDATE parcel_ownership SET valid_to = current_date, ended_txn_id = :t WHERE id = ANY(:i)"),
               {"t": tid, "i": [o[0] for o in owners]})
    kitta = _next_kitta(db, row[3], row[4])
    made = []
    for n, (child, req_child, report) in enumerate(zip(children, req.children, reports)):
        pid, pin = _insert_parcel(db, child, row[3], row[4], kitta + n, row[7], req_child.land_use or row[6],
                                  report.area_m2, "field_survey", None)
        db.execute(text("INSERT INTO parcel_lineage (parent_id, child_id, transaction_id) VALUES (:a, :b, :t)"),
                   {"a": parcel_id, "b": pid, "t": tid})
        for _, owner_id, num, den in owners:  # children keep the parent's owners and shares
            db.execute(text("INSERT INTO parcel_ownership (parcel_id, owner_id, share_num, share_den, valid_from, "
                            "acquired_txn_id) VALUES (:p, :o, :n, :d, current_date, :t)"),
                       {"p": pid, "o": owner_id, "n": num, "d": den, "t": tid})
        _record_issues(db, pid, report)
        made.append({"parcel_id": pid, "pin": pin, "kitta": kitta + n, "area_m2": report.area_m2})
    _audit(db, officer, "parcel_split", parcel_id, tid, {"pin": row[1], "case_id": case_id,
                                                         "children": [m["pin"] for m in made]})
    db.commit()
    return {"parent_id": parcel_id, "parent_pin": row[1], "case_id": case_id, "children": made}
