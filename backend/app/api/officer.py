"""Officer-only API: dashboard, owner search and registration with the duplicate check, parcel ownership."""
import json
from fractions import Fraction
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import Officer, current_officer
from app.db import SessionLocal, get_session
from app.schemas import (AuditRow, Dashboard, Holding, OwnerCreate, OwnerDetails, OwnerHit, OwnerOfParcel,
                         ParcelOwnershipOut, ParcelSummary, RokkaOut, SimilarOwner, SimilarRequest, TxnRow)
from app.search.index import NameIndex
from app.search.text import max_edits, words

router = APIRouter(prefix="/api/officer", tags=["officer"], dependencies=[Depends(current_officer)])

LIN_SUFFIX = {"organisation": "O", "government": "G", "communal": "C"}
GENDER_SUFFIX = {"male": "M", "female": "F", "other": "X"}

_OWNER_SQL = text("""
SELECT o.id, o.lin, o.full_name, o.full_name_ne, o.owner_type, o.gender, o.date_of_birth, o.district_code,
       (SELECT count(*) FROM parcel_ownership po WHERE po.owner_id = o.id AND po.valid_to IS NULL)
FROM owners o WHERE o.id = ANY(:ids)
""")


@lru_cache(maxsize=1)
def owners_index() -> NameIndex:
    """All owner names, for fuzzy search and the duplicate check; built once, then updated on each save."""
    with SessionLocal() as db:
        return NameIndex(db.execute(text("SELECT id, full_name FROM owners")).all())


def _hits(db: Session, ids: list[int], matches: dict | None = None) -> list[OwnerHit]:
    """Owner rows in the order of ids, with the search distances when they came from a search."""
    rows = {r[0]: r for r in db.execute(_OWNER_SQL, {"ids": ids})}
    out = []
    for i in ids:
        if (r := rows.get(i)) is None:
            continue
        m = (matches or {}).get(i)
        out.append(OwnerHit(id=i, lin=r[1], full_name=r[2], full_name_ne=r[3], owner_type=r[4], gender=r[5],
                            date_of_birth=r[6], district_code=r[7], parcels=r[8],
                            distance=m.distance if m else 0, edits=m.score if m else 0))
    return out


def _found(db: Session, matches) -> list[OwnerHit]:
    return _hits(db, [m.id for m in matches], {m.id: m for m in matches})


@router.get("/dashboard", response_model=Dashboard)
def dashboard(db: Session = Depends(get_session)):
    counts = db.execute(text("""
        SELECT (SELECT count(*) FROM parcels WHERE status = 'active'),
               (SELECT count(*) FROM owners),
               (SELECT count(*) FROM parcel_issues WHERE review_status = 'open'),
               (SELECT count(*) FROM rokka WHERE fukuwa_date IS NULL),
               (SELECT count(*) FROM transactions WHERE deed_date >= current_date - 30)
    """)).one()
    txns = db.execute(text("""
        SELECT t.case_id, t.txn_type, t.status, t.deed_date, t.parcel_id, p.pin, p.parcel_no, p.ward_no, o.full_name
        FROM transactions t JOIN officers o ON o.id = t.created_by LEFT JOIN parcels p ON p.id = t.parcel_id
        ORDER BY t.deed_date DESC NULLS LAST, t.id DESC LIMIT 8
    """)).all()
    audit = db.execute(text("""
        SELECT a.action, o.full_name, a.created_at, a.parcel_id, a.details
        FROM audit_log a JOIN officers o ON o.id = a.officer_id ORDER BY a.created_at DESC, a.id DESC LIMIT 8
    """)).all()
    return Dashboard(active_parcels=counts[0], owners=counts[1], open_issues=counts[2], active_rokka=counts[3],
                     transactions_30_days=counts[4],
                     recent_transactions=[TxnRow(case_id=r[0], txn_type=r[1], status=r[2], deed_date=r[3],
                                                 parcel_id=r[4], pin=r[5], kitta=r[6], ward=r[7], officer=r[8])
                                          for r in txns],
                     recent_activity=[AuditRow(action=r[0], officer=r[1], created_at=r[2], parcel_id=r[3],
                                               details=r[4] or {}) for r in audit])


@router.get("/owners", response_model=list[OwnerHit])
def search_owners(q: str = Query(min_length=2, max_length=150), db: Session = Depends(get_session)):
    """Owners by name (Levenshtein over folded spellings) or by LIN."""
    if q.strip()[:2].isdigit():
        ids = db.execute(text("SELECT id FROM owners WHERE lin LIKE :p ORDER BY lin LIMIT 25"),
                         {"p": q.strip().upper().replace("%", "") + "%"}).scalars().all()
        return _hits(db, list(ids))
    return _found(db, owners_index().search(q, limit=25))


def _holdings(db: Session, where: str, params: dict) -> list[Holding]:
    rows = db.execute(text(f"""
        SELECT po.parcel_id, po.share_num, po.share_den, po.valid_from, po.valid_to, t.case_id, t.txn_type,
               p.pin, p.parcel_no, p.ward_no, p.map_sheet_code, p.land_use, p.parcel_type, p.registered_area
        FROM parcel_ownership po JOIN parcels p ON p.id = po.parcel_id
        LEFT JOIN transactions t ON t.id = po.acquired_txn_id
        WHERE {where} ORDER BY po.valid_from DESC
    """), params).all()
    return [Holding(parcel=ParcelSummary(id=r[0], pin=r[7], kitta=r[8], ward=r[9], map_sheet=r[10], land_use=r[11],
                                         parcel_type=r[12], area_m2=float(r[13])),
                    share=str(Fraction(r[1], r[2])), valid_from=r[3], valid_to=r[4], case_id=r[5], txn_type=r[6])
            for r in rows]


@router.get("/owners/{owner_id}", response_model=OwnerDetails)
def owner_details(owner_id: int, db: Session = Depends(get_session)):
    row = db.execute(text("SELECT citizenship_no, address, phone FROM owners WHERE id = :id"),
                     {"id": owner_id}).one_or_none()
    if row is None:
        raise HTTPException(404, "owner not found")
    hit = _hits(db, [owner_id])[0]
    return OwnerDetails(**hit.model_dump(), citizenship_no=row[0], address=row[1], phone=row[2],
                        current=_holdings(db, "po.owner_id = :id AND po.valid_to IS NULL", {"id": owner_id}),
                        past=_holdings(db, "po.owner_id = :id AND po.valid_to IS NOT NULL", {"id": owner_id}))


def similar_owners(db: Session, req: SimilarRequest, limit: int = 8) -> list[SimilarOwner]:
    """Existing owners with a close name; likely duplicates also share the date of birth (individuals)."""
    allowance = sum(max_edits(w) for w in words(req.full_name))
    matches = [m for m in owners_index().search(req.full_name, limit=200, prefix=False) if m.score <= allowance]
    out = []
    for h in _found(db, matches):
        same_dob = req.date_of_birth is not None and h.date_of_birth == req.date_of_birth
        same_district = req.district_code is not None and h.district_code == req.district_code
        likely = h.owner_type == req.owner_type and (same_dob if req.owner_type == "individual" else h.edits == 0)
        out.append(SimilarOwner(**h.model_dump(), same_dob=same_dob, same_district=same_district,
                                likely_duplicate=likely))
    out.sort(key=lambda s: (not s.likely_duplicate, not s.same_dob, s.edits, s.distance, s.full_name))
    return out[:limit]


@router.post("/owners/similar", response_model=list[SimilarOwner])
def check_similar(req: SimilarRequest, db: Session = Depends(get_session)):
    return similar_owners(db, req)


@router.post("/owners", response_model=OwnerHit, status_code=201)
def register_owner(req: OwnerCreate, db: Session = Depends(get_session), officer: Officer = Depends(current_officer)):
    """Register an owner; refused with 409 when a likely duplicate exists unless confirm_new is set."""
    similar = similar_owners(db, SimilarRequest(owner_type=req.owner_type, full_name=req.full_name,
                                                date_of_birth=req.date_of_birth, district_code=req.district_code))
    duplicates = [s for s in similar if s.likely_duplicate]
    if duplicates and not req.confirm_new:
        return JSONResponse(status_code=409, content={
            "detail": "a very similar owner already exists",
            "similar": [json.loads(s.model_dump_json()) for s in duplicates]})
    owner_id = db.execute(text("SELECT nextval(pg_get_serial_sequence('owners', 'id'))")).scalar()
    suffix = GENDER_SUFFIX[req.gender] if req.owner_type == "individual" else LIN_SUFFIX[req.owner_type]
    lin = f"{req.district_code:02d}-{owner_id:06d}-{suffix}"
    fields = req.model_dump(exclude={"confirm_new"})
    db.execute(text("""
        INSERT INTO owners (id, lin, owner_type, full_name, full_name_ne, gender, date_of_birth, citizenship_no,
                            district_code, address, phone)
        VALUES (:id, :lin, :owner_type, :full_name, :full_name_ne, :gender, :date_of_birth, :citizenship_no,
                :district_code, :address, :phone)
    """), {**fields, "id": owner_id, "lin": lin})
    details = {"owner_id": owner_id, "lin": lin, "name": req.full_name,
               "ignored_duplicates": [d.lin for d in duplicates]}
    db.execute(text("INSERT INTO audit_log (officer_id, action, details) VALUES (:o, 'owner_registered', "
                    "CAST(:d AS jsonb))"), {"o": officer.id, "d": json.dumps(details)})
    db.commit()
    owners_index().add(owner_id, req.full_name)
    return _hits(db, [owner_id])[0]


@router.get("/parcels/{parcel_id}/ownership", response_model=ParcelOwnershipOut)
def parcel_ownership(parcel_id: int, db: Session = Depends(get_session)):
    """Current owners with exact shares, the ownership history and any active rokka."""
    rows = db.execute(text("""
        SELECT o.id, o.lin, o.full_name, o.owner_type, po.share_num, po.share_den, po.valid_from, po.valid_to,
               t.case_id, t.txn_type, t.deed_ref
        FROM parcel_ownership po JOIN owners o ON o.id = po.owner_id
        LEFT JOIN transactions t ON t.id = po.acquired_txn_id
        WHERE po.parcel_id = :id ORDER BY po.valid_to IS NOT NULL, po.valid_from DESC, o.full_name
    """), {"id": parcel_id}).all()
    if not rows and db.execute(text("SELECT 1 FROM parcels WHERE id = :id"), {"id": parcel_id}).first() is None:
        raise HTTPException(404, "parcel not found")
    owners = [OwnerOfParcel(owner_id=r[0], lin=r[1], full_name=r[2], owner_type=r[3], share=str(Fraction(r[4], r[5])),
                            valid_from=r[6], valid_to=r[7], case_id=r[8], txn_type=r[9], deed_ref=r[10]) for r in rows]
    rokka = db.execute(text("SELECT id, requested_by_type, requested_by_name, reason, start_date FROM rokka "
                            "WHERE parcel_id = :id AND fukuwa_date IS NULL ORDER BY start_date"),
                       {"id": parcel_id}).all()
    return ParcelOwnershipOut(parcel_id=parcel_id, current=[o for o in owners if o.valid_to is None],
                              history=[o for o in owners if o.valid_to is not None],
                              rokka=[RokkaOut(id=r[0], requested_by_type=r[1], requested_by_name=r[2], reason=r[3],
                                              start_date=r[4]) for r in rokka])
