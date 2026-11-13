"""Issue review: problems found by validation (on save or by the city-wide scan), and the officer's decision."""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import Officer, current_officer
from app.db import get_session

router = APIRouter(prefix="/api/officer/issues", tags=["officer issues"], dependencies=[Depends(current_officer)])

STATUSES = ("open", "resolved", "dispute")
TYPES = ("overlap", "gap", "sliver", "invalid", "area_mismatch")


class Review(BaseModel):
    status: str = Field(pattern="^(open|resolved|dispute)$")
    note: str | None = Field(None, max_length=500)


def _summary(details: dict, issue_type: str) -> str:
    if issue_type == "overlap":
        return f"{details.get('area_m2', 0):,.2f} m² shared area"
    return details.get("check") or details.get("problem") or ""


@router.get("")
def list_issues(status: str = Query("open", pattern="^(open|resolved|dispute)$"),
                issue_type: str | None = Query(None, pattern="^(overlap|gap|sliver|invalid|area_mismatch)$"),
                limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                db: Session = Depends(get_session)):
    """Issues by review status (and type), largest overlaps first, with counts for the tabs and filters."""
    where = "i.review_status = :s" + (" AND i.issue_type = :t" if issue_type else "")
    rows = db.execute(text(f"""
        SELECT i.id, i.issue_type, i.severity, i.details, i.found_at, i.review_status, i.review_note, i.reviewed_at,
               a.id, a.pin, a.parcel_no, a.ward_no, b.id, b.pin, b.parcel_no, o.full_name
        FROM parcel_issues i JOIN parcels a ON a.id = i.parcel_id LEFT JOIN parcels b ON b.id = i.other_parcel_id
        LEFT JOIN officers o ON o.id = i.reviewed_by
        WHERE {where}
        ORDER BY i.severity = 'error' DESC, (i.details ->> 'area_m2')::float DESC NULLS LAST, i.id
        LIMIT :lim OFFSET :off
    """), {"s": status, "t": issue_type, "lim": limit, "off": offset}).all()
    by_status = dict(db.execute(text("SELECT review_status, count(*) FROM parcel_issues GROUP BY 1")).all())
    by_type = dict(db.execute(text("SELECT issue_type, count(*) FROM parcel_issues WHERE review_status = :s "
                                   "GROUP BY 1"), {"s": status}).all())
    return {
        "counts": {s: by_status.get(s, 0) for s in STATUSES},
        "types": {t: by_type.get(t, 0) for t in TYPES},
        "total": by_type.get(issue_type, 0) if issue_type else sum(by_type.values()),
        "issues": [{
            "id": r[0], "type": r[1], "severity": r[2], "summary": _summary(r[3] or {}, r[1]),
            "source": (r[3] or {}).get("source"), "found_at": r[4], "status": r[5], "note": r[6], "reviewed_at": r[7],
            "parcel": {"id": r[8], "pin": r[9], "kitta": r[10], "ward": r[11]},
            "other": {"id": r[12], "pin": r[13], "kitta": r[14]} if r[12] else None, "reviewed_by": r[15],
        } for r in rows],
    }


@router.get("/{issue_id}")
def get_issue(issue_id: int, db: Session = Depends(get_session)):
    """One issue with the shapes to draw: the parcel, the other parcel and the overlapping area."""
    r = db.execute(text("""
        SELECT i.id, i.issue_type, i.severity, i.details, i.found_at, i.review_status, i.review_note, i.reviewed_at,
               a.id, a.pin, a.parcel_no, a.ward_no, a.status, a.registered_area, ST_AsGeoJSON(a.boundary, 7),
               b.id, b.pin, b.parcel_no, b.status, ST_AsGeoJSON(b.boundary, 7), o.full_name,
               ST_Area(ST_Transform(a.boundary, 32645))
        FROM parcel_issues i JOIN parcels a ON a.id = i.parcel_id LEFT JOIN parcels b ON b.id = i.other_parcel_id
        LEFT JOIN officers o ON o.id = i.reviewed_by WHERE i.id = :id
    """), {"id": issue_id}).one_or_none()
    if r is None:
        raise HTTPException(404, "issue not found")
    details = r[3] or {}
    return {
        "id": r[0], "type": r[1], "severity": r[2], "summary": _summary(details, r[1]), "found_at": r[4],
        "status": r[5], "note": r[6], "reviewed_at": r[7], "reviewed_by": r[20], "source": details.get("source"),
        "details": {k: v for k, v in details.items() if k != "geometry"},
        "overlap_geometry": details.get("geometry"),
        "parcel": {"id": r[8], "pin": r[9], "kitta": r[10], "ward": r[11], "status": r[12],
                   "registered_m2": float(r[13]), "boundary_m2": round(float(r[21]), 2), "geometry": json.loads(r[14])},
        "other": {"id": r[15], "pin": r[16], "kitta": r[17], "status": r[18], "geometry": json.loads(r[19])}
        if r[15] else None,
    }


@router.post("/{issue_id}/review")
def review_issue(issue_id: int, req: Review, db: Session = Depends(get_session),
                 officer: Officer = Depends(current_officer)):
    """Resolve an issue, mark it a boundary dispute, or reopen it; the scan does not raise reviewed issues again."""
    row = db.execute(text("SELECT parcel_id, issue_type, review_status FROM parcel_issues WHERE id = :id"),
                     {"id": issue_id}).one_or_none()
    if row is None:
        raise HTTPException(404, "issue not found")
    if req.status != "open" and not (req.note or "").strip():
        raise HTTPException(422, "add a note saying how the issue was resolved or why it is a dispute")
    reopen = req.status == "open"
    db.execute(text("UPDATE parcel_issues SET review_status = :s, review_note = :n, reviewed_by = :o, "
                    f"reviewed_at = {'NULL' if reopen else 'now()'} WHERE id = :id"),
               {"s": req.status, "n": req.note, "o": None if reopen else officer.id, "id": issue_id})
    db.execute(text("INSERT INTO audit_log (officer_id, action, parcel_id, details) "
                    "VALUES (:o, 'issue_reviewed', :p, CAST(:d AS jsonb))"),
               {"o": officer.id, "p": row[0], "d": json.dumps({"issue_id": issue_id, "type": row[1],
                                                               "from": row[2], "to": req.status, "note": req.note})})
    db.commit()
    return {"id": issue_id, "status": req.status}
