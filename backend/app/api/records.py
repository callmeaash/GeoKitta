"""Officer records: ownership transfer by deed, rokka and fukuwa, and the full parcel history."""
import json
from datetime import date
from fractions import Fraction

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.parcels import ShareIn, _active, _audit, _new_transaction
from app.auth import Officer, current_officer
from app.db import get_session
from app.spatial.geometry import polygon_area
from app.spatial.projection import polygons_from_geojson

router = APIRouter(prefix="/api/officer", tags=["officer records"], dependencies=[Depends(current_officer)])

DEEDS = ("rajinama", "hal_ko_bakaspatra", "danpatra", "ansha_banda", "namasari", "chhod_patra")
REQUESTERS = ("bank", "court", "ciaa", "government", "other")


class TransferRequest(BaseModel):
    deed_type: str = Field(pattern="^(" + "|".join(DEEDS) + ")$")
    deed_date: date
    deed_ref: str | None = Field(None, max_length=40)
    remarks: str | None = Field(None, max_length=500)
    owners: list[ShareIn] = Field(min_length=1, max_length=20, description="the complete set of owners after the deed")

    @field_validator("owners")
    @classmethod
    def shares_add_up(cls, owners):
        if len({o.owner_id for o in owners}) < len(owners):
            raise ValueError("an owner is listed twice")
        if sum(Fraction(o.share) for o in owners) != 1:
            raise ValueError("the new owners' shares must add up to 1")
        return owners

    @field_validator("deed_date")
    @classmethod
    def not_in_future(cls, d):
        if not date(1950, 1, 1) <= d <= date.today():
            raise ValueError("the deed date must be between 1950 and today")
        return d


class RokkaRequest(BaseModel):
    requested_by_type: str = Field(pattern="^(" + "|".join(REQUESTERS) + ")$")
    requested_by_name: str = Field(min_length=2, max_length=150)
    reason: str | None = Field(None, max_length=300)
    start_date: date = Field(default_factory=date.today)


class FukuwaRequest(BaseModel):
    fukuwa_date: date = Field(default_factory=date.today)
    remarks: str | None = Field(None, max_length=300)


def _active_rokka(db: Session, parcel_id: int):
    return db.execute(text("SELECT id, requested_by_name, start_date FROM rokka WHERE parcel_id = :p "
                           "AND fukuwa_date IS NULL ORDER BY start_date"), {"p": parcel_id}).all()


def _owners_text(rows) -> str:
    share = lambda n, d: "full" if n == d else str(Fraction(n, d))  # noqa: E731
    return ", ".join(f"{r[0]} ({share(r[1], r[2])})" for r in rows) or "—"


# ---------- ownership transfer ----------

@router.post("/parcels/{parcel_id}/transfer", status_code=201)
def transfer(parcel_id: int, req: TransferRequest, db: Session = Depends(get_session),
             officer: Officer = Depends(current_officer)):
    """Record a deed: the current ownership periods end and the new owners' periods start on the deed date."""
    row = _active(db, parcel_id)
    if holds := _active_rokka(db, parcel_id):
        raise HTTPException(409, f"transfer blocked: rokka by {holds[0][1]} since {holds[0][2]}; "
                                 "release it (fukuwa) first")
    current = db.execute(text("""
        SELECT po.id, po.owner_id, po.share_num, po.share_den, po.valid_from, o.full_name
        FROM parcel_ownership po JOIN owners o ON o.id = po.owner_id
        WHERE po.parcel_id = :p AND po.valid_to IS NULL
    """), {"p": parcel_id}).all()
    if current and req.deed_date < max(r[4] for r in current):
        raise HTTPException(422, f"the deed date is before the current owners' date ({max(r[4] for r in current)})")
    before = {r[1]: Fraction(r[2], r[3]) for r in current}
    after = {o.owner_id: Fraction(o.share) for o in req.owners}
    if before == after:
        raise HTTPException(422, "the new owners and shares are the same as the current ones")
    names = dict(db.execute(text("SELECT id, full_name FROM owners WHERE id = ANY(:i)"), {"i": list(after)}).all())
    if missing := [i for i in after if i not in names]:
        raise HTTPException(422, f"unknown owner ids: {missing}")

    tid, case_id = _new_transaction(db, officer, req.deed_type, parcel_id, req.deed_ref, req.remarks)
    db.execute(text("UPDATE transactions SET deed_date = :d WHERE id = :t"), {"d": req.deed_date, "t": tid})
    db.execute(text("UPDATE parcel_ownership SET valid_to = :d, ended_txn_id = :t WHERE id = ANY(:i)"),
               {"d": req.deed_date, "t": tid, "i": [r[0] for r in current]})
    for owner_id, share in after.items():
        db.execute(text("INSERT INTO parcel_ownership (parcel_id, owner_id, share_num, share_den, valid_from, "
                        "acquired_txn_id) VALUES (:p, :o, :n, :d, :f, :t)"),
                   {"p": parcel_id, "o": owner_id, "n": share.numerator, "d": share.denominator,
                    "f": req.deed_date, "t": tid})
    _audit(db, officer, "ownership_transferred", parcel_id, tid, {
        "pin": row[1], "case_id": case_id, "deed": req.deed_type,
        "from": [f"{r[5]} ({Fraction(r[2], r[3])})" for r in current],
        "to": [f"{names[i]} ({s})" for i, s in after.items()]})
    db.commit()
    return {"parcel_id": parcel_id, "pin": row[1], "case_id": case_id}


# ---------- rokka (hold) and fukuwa (release) ----------

@router.post("/parcels/{parcel_id}/rokka", status_code=201)
def place_rokka(parcel_id: int, req: RokkaRequest, db: Session = Depends(get_session),
                officer: Officer = Depends(current_officer)):
    """Put a parcel on hold at the request of a bank, court or office; transfers are blocked until fukuwa."""
    row = _active(db, parcel_id)
    if req.start_date > date.today():
        raise HTTPException(422, "the rokka cannot start in the future")
    remarks = f"Rokka for {req.requested_by_name}" + (f": {req.reason}" if req.reason else "")
    tid, case_id = _new_transaction(db, officer, "rokka", parcel_id, None, remarks)
    db.execute(text("UPDATE transactions SET deed_date = :d WHERE id = :t"), {"d": req.start_date, "t": tid})
    rid = db.execute(text("""
        INSERT INTO rokka (parcel_id, requested_by_type, requested_by_name, reason, start_date, placed_txn_id)
        VALUES (:p, :ty, :n, :r, :d, :t) RETURNING id
    """), {"p": parcel_id, "ty": req.requested_by_type, "n": req.requested_by_name, "r": req.reason,
           "d": req.start_date, "t": tid}).scalar()
    _audit(db, officer, "rokka_placed", parcel_id, tid, {"pin": row[1], "case_id": case_id,
                                                        "requested_by": req.requested_by_name})
    db.commit()
    return {"rokka_id": rid, "case_id": case_id}


@router.post("/rokka/{rokka_id}/release")
def release_rokka(rokka_id: int, req: FukuwaRequest, db: Session = Depends(get_session),
                  officer: Officer = Depends(current_officer)):
    hold = db.execute(text("SELECT r.parcel_id, r.start_date, r.fukuwa_date, r.requested_by_name, p.pin "
                           "FROM rokka r JOIN parcels p ON p.id = r.parcel_id WHERE r.id = :id"),
                      {"id": rokka_id}).one_or_none()
    if hold is None:
        raise HTTPException(404, "rokka not found")
    if hold[2] is not None:
        raise HTTPException(409, f"already released on {hold[2]}")
    if not hold[1] <= req.fukuwa_date <= date.today():
        raise HTTPException(422, f"the release date must be between {hold[1]} and today")
    remarks = f"Fukuwa for {hold[3]}" + (f": {req.remarks}" if req.remarks else "")
    tid, case_id = _new_transaction(db, officer, "fukuwa", hold[0], None, remarks)
    db.execute(text("UPDATE transactions SET deed_date = :d WHERE id = :t"), {"d": req.fukuwa_date, "t": tid})
    db.execute(text("UPDATE rokka SET fukuwa_date = :d, released_txn_id = :t WHERE id = :id"),
               {"d": req.fukuwa_date, "t": tid, "id": rokka_id})
    _audit(db, officer, "rokka_released", hold[0], tid, {"pin": hold[4], "case_id": case_id,
                                                        "requested_by": hold[3]})
    db.commit()
    return {"rokka_id": rokka_id, "case_id": case_id}


# ---------- history ----------

_TITLES = {
    "registration": "Parcel registered", "boundary_update": "Boundary updated", "split": "Split (kitta kaat)",
    "merge": "Merged", "rokka": "Rokka placed", "fukuwa": "Rokka released (fukuwa)", "samsodhan": "Details corrected",
}


@router.get("/parcels/{parcel_id}/history")
def history(parcel_id: int, db: Session = Depends(get_session)):
    """Timeline of cases, boundary versions and lineage for one parcel (active or retired)."""
    parcel = db.execute(text("SELECT id, pin, parcel_no, ward_no, status, created_at, ST_AsGeoJSON(boundary, 7) "
                             "FROM parcels WHERE id = :id"), {"id": parcel_id}).one_or_none()
    if parcel is None:
        raise HTTPException(404, "parcel not found")

    parents = db.execute(text("SELECT p.id, p.parcel_no, p.pin, p.status, l.transaction_id FROM parcel_lineage l "
                              "JOIN parcels p ON p.id = l.parent_id WHERE l.child_id = :id"), {"id": parcel_id}).all()
    children = db.execute(text("SELECT p.id, p.parcel_no, p.pin, p.status FROM parcel_lineage l "
                               "JOIN parcels p ON p.id = l.child_id WHERE l.parent_id = :id ORDER BY p.parcel_no"),
                          {"id": parcel_id}).all()
    siblings = db.execute(text("""
        SELECT p.id, p.parcel_no, p.pin, p.status FROM parcel_lineage l JOIN parcels p ON p.id = l.child_id
        WHERE l.parent_id = ANY(:par) AND l.child_id <> :id ORDER BY p.parcel_no
    """), {"par": [p[0] for p in parents], "id": parcel_id}).all()

    cases = db.execute(text("""
        SELECT t.id, t.case_id, t.txn_type, t.status, t.deed_date, t.deed_ref, t.remarks, o.full_name
        FROM transactions t JOIN officers o ON o.id = t.created_by
        WHERE t.parcel_id = :id OR t.id = ANY(:lin)
        ORDER BY t.deed_date DESC NULLS LAST, t.id DESC
    """), {"id": parcel_id, "lin": [p[4] for p in parents]}).all()
    ids = [c[0] for c in cases]
    ended = db.execute(text("SELECT po.ended_txn_id, o.full_name, po.share_num, po.share_den "
                            "FROM parcel_ownership po JOIN owners o ON o.id = po.owner_id "
                            "WHERE po.parcel_id = :p AND po.ended_txn_id = ANY(:t)"),
                       {"p": parcel_id, "t": ids}).all()
    started = db.execute(text("SELECT po.acquired_txn_id, o.full_name, po.share_num, po.share_den "
                              "FROM parcel_ownership po JOIN owners o ON o.id = po.owner_id "
                              "WHERE po.parcel_id = :p AND po.acquired_txn_id = ANY(:t)"),
                         {"p": parcel_id, "t": ids}).all()
    holds = db.execute(text("SELECT placed_txn_id, released_txn_id, requested_by_name, reason FROM rokka "
                            "WHERE parcel_id = :p"), {"p": parcel_id}).all()
    versions = db.execute(text("SELECT id, area_m2, valid_from, valid_to, transaction_id, ST_AsGeoJSON(boundary, 7) "
                               "FROM parcel_geometry_history WHERE parcel_id = :p ORDER BY valid_from"),
                          {"p": parcel_id}).all()
    edits = dict(db.execute(text("SELECT transaction_id, details FROM audit_log WHERE parcel_id = :p "
                                 "AND action = 'details_updated'"), {"p": parcel_id}).all())

    timeline = []
    for tid, case_id, kind, status, when, ref, remarks, officer_name in cases:
        frm = _owners_text([r[1:] for r in ended if r[0] == tid])
        to = _owners_text([r[1:] for r in started if r[0] == tid])
        detail = remarks or ""
        if kind in DEEDS:
            title, detail = "Ownership transfer", f"{frm} → {to}"
        elif kind == "split":
            if parents and tid in [p[4] for p in parents]:
                kin = ", ".join(f"kitta {s[1]}" for s in siblings)
                title = "Created by split (kitta kaat)"
                detail = (f"Split from kitta {parents[0][1]}" + (f" together with {kin}" if kin else "")
                          + f". Owners: {to}.")
            else:
                title = "Split (kitta kaat)"
                detail = "Split into " + ", ".join(f"kitta {c[1]}" for c in children) + "."
        elif kind in ("rokka", "fukuwa"):
            hold = next((h for h in holds if tid in (h[0], h[1])), None)
            title = _TITLES[kind]
            if hold:
                detail = f"{hold[2]}" + (f" — {hold[3]}" if hold[3] and kind == "rokka" else "")
        elif kind == "boundary_update":
            old = next((v for v in versions if v[4] == tid), None)
            title, detail = _TITLES[kind], (f"Previous area {float(old[1]):,.1f} m². {remarks or ''}".strip()
                                            if old else remarks or "")
        elif kind == "samsodhan" and tid in edits:
            e = edits[tid]
            title = _TITLES[kind]
            detail = "; ".join(f"{k.replace('_', ' ')}: {e['before'][k]} → {v}" for k, v in e["after"].items())
        else:
            title = _TITLES.get(kind, kind.replace("_", " ").capitalize())
            if kind == "registration" and to != "—":
                detail = f"Owners: {to}."
        timeline.append({"date": when, "kind": kind, "title": title, "detail": detail, "case_id": case_id,
                         "deed_ref": ref, "status": status, "officer": officer_name})

    current_poly = polygons_from_geojson([parcel[6]])[0]
    boundary_versions = [{"version": n + 1, "area_m2": float(v[1]), "valid_from": v[2], "valid_to": v[3],
                          "geometry": json.loads(v[5])} for n, v in enumerate(versions)]
    boundary_versions.append({"version": len(versions) + 1, "area_m2": round(polygon_area(current_poly), 2),
                              "valid_from": versions[-1][3] if versions else parcel[5], "valid_to": None,
                              "geometry": json.loads(parcel[6])})
    kin = lambda rows: [{"id": r[0], "kitta": r[1], "pin": r[2], "status": r[3]} for r in rows]  # noqa: E731
    return {"parcel": {"id": parcel[0], "pin": parcel[1], "kitta": parcel[2], "ward": parcel[3], "status": parcel[4]},
            "timeline": timeline, "boundaries": boundary_versions[::-1],
            "lineage": {"parents": kin(parents), "siblings": kin(siblings), "children": kin(children)}}
