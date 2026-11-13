"""Admin only: officer accounts and setback rules. Every change goes into the audit log."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import Officer, admin_officer, hash_password
from app.db import get_session

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(admin_officer)])

SYSTEM_ACCOUNTS = ("pipeline",)  # the data import's own account; it never signs in


class OfficerCreate(BaseModel):
    username: str = Field(pattern=r"^[a-z][a-z0-9_.]{2,49}$")
    full_name: str = Field(min_length=3, max_length=100)
    office: str | None = Field(None, max_length=100)
    is_admin: bool = False
    password: str = Field(min_length=10, max_length=200)


class OfficerUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=3, max_length=100)
    office: str | None = Field(None, max_length=100)
    is_admin: bool | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=10, max_length=200)


class RuleIn(BaseModel):
    feature_type: str = Field(pattern="^(highway|road|river|stream|power_line)$")
    distance_m: float = Field(gt=0, le=200)
    measured_from: str = Field(pattern="^(centre_line|bank|line)$")
    source: str = Field(pattern="^(municipal|national)$")
    note: str | None = Field(None, max_length=300)


def _log(db: Session, admin: Officer, action: str, details: dict) -> None:
    db.execute(text("INSERT INTO audit_log (officer_id, action, details) VALUES (:o, :a, CAST(:d AS jsonb))"),
               {"o": admin.id, "a": action, "d": json.dumps(details, default=str)})


# ---------- officer accounts ----------

@router.get("/officers")
def list_officers(db: Session = Depends(get_session)):
    rows = db.execute(text("""
        SELECT o.id, o.username, o.full_name, o.office, o.is_admin, o.is_active, o.created_at, o.last_login_at,
               (SELECT count(*) FROM audit_log a WHERE a.officer_id = o.id AND a.action <> 'login')
        FROM officers o WHERE o.username <> ALL(:sys) ORDER BY o.is_active DESC, o.full_name
    """), {"sys": list(SYSTEM_ACCOUNTS)}).all()
    return [{"id": r[0], "username": r[1], "full_name": r[2], "office": r[3], "is_admin": r[4], "is_active": r[5],
             "created_at": r[6], "last_login_at": r[7], "changes": r[8]} for r in rows]


@router.post("/officers", status_code=201)
def create_officer(req: OfficerCreate, db: Session = Depends(get_session), admin: Officer = Depends(admin_officer)):
    try:
        oid = db.execute(text("INSERT INTO officers (username, password_hash, full_name, office, is_admin) "
                              "VALUES (:u, :h, :n, :o, :a) RETURNING id"),
                         {"u": req.username, "h": hash_password(req.password), "n": req.full_name, "o": req.office,
                          "a": req.is_admin}).scalar()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"the username {req.username} is taken") from None
    _log(db, admin, "officer_created", {"officer_id": oid, "username": req.username, "is_admin": req.is_admin})
    db.commit()
    return {"id": oid, "username": req.username}


def _target(db: Session, officer_id: int):
    row = db.execute(text("SELECT id, username, full_name, office, is_admin, is_active FROM officers WHERE id = :id"),
                     {"id": officer_id}).one_or_none()
    if row is None or row[1] in SYSTEM_ACCOUNTS:
        raise HTTPException(404, "officer not found")
    return row


@router.patch("/officers/{officer_id}")
def update_officer(officer_id: int, req: OfficerUpdate, db: Session = Depends(get_session),
                   admin: Officer = Depends(admin_officer)):
    row = _target(db, officer_id)
    changes = {k: v for k, v in req.model_dump(exclude_unset=True).items()
               if v != {"full_name": row[2], "office": row[3], "is_admin": row[4], "is_active": row[5]}[k]}
    if officer_id == admin.id and (changes.get("is_admin") is False or changes.get("is_active") is False):
        raise HTTPException(409, "you cannot remove your own admin rights or disable your own account")
    if not changes:
        raise HTTPException(422, "nothing to change")
    if changes.get("is_admin") is False or changes.get("is_active") is False:
        admins = db.execute(text("SELECT count(*) FROM officers WHERE is_admin AND is_active AND id <> :id"),
                            {"id": officer_id}).scalar()
        if row[4] and admins == 0:
            raise HTTPException(409, "at least one active admin must remain")
    sets = ", ".join(f"{k} = :{k}" for k in changes)
    db.execute(text(f"UPDATE officers SET {sets} WHERE id = :id"), {**changes, "id": officer_id})
    _log(db, admin, "officer_updated", {"officer_id": officer_id, "username": row[1], "changes": changes})
    db.commit()
    return {"id": officer_id, "changed": changes}


@router.post("/officers/{officer_id}/password")
def reset_password(officer_id: int, req: PasswordReset, db: Session = Depends(get_session),
                   admin: Officer = Depends(admin_officer)):
    row = _target(db, officer_id)
    db.execute(text("UPDATE officers SET password_hash = :h WHERE id = :id"),
               {"h": hash_password(req.password), "id": officer_id})
    _log(db, admin, "password_reset", {"officer_id": officer_id, "username": row[1]})  # never the password itself
    db.commit()
    return {"id": officer_id}


# ---------- setback rules ----------

def _rule_or_404(db: Session, rule_id: int):
    row = db.execute(text("SELECT id, feature_type, distance_m, measured_from, source, note FROM setback_rules "
                          "WHERE id = :id"), {"id": rule_id}).one_or_none()
    if row is None:
        raise HTTPException(404, "rule not found")
    return {"id": row[0], "feature_type": row[1], "distance_m": float(row[2]), "measured_from": row[3],
            "source": row[4], "note": row[5]}


def _save_rule(db: Session, sql: str, params: dict) -> int:
    try:
        return db.execute(text(sql), params).scalar()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "a rule for this feature type and source already exists") from None


@router.post("/setback-rules", status_code=201)
def create_rule(req: RuleIn, db: Session = Depends(get_session), admin: Officer = Depends(admin_officer)):
    rid = _save_rule(db, "INSERT INTO setback_rules (feature_type, distance_m, measured_from, source, note) "
                         "VALUES (:feature_type, :distance_m, :measured_from, :source, :note) RETURNING id",
                     req.model_dump())
    _log(db, admin, "setback_rule_created", {"rule_id": rid, **req.model_dump()})
    db.commit()
    return _rule_or_404(db, rid)


@router.put("/setback-rules/{rule_id}")
def update_rule(rule_id: int, req: RuleIn, db: Session = Depends(get_session), admin: Officer = Depends(admin_officer)):
    before = _rule_or_404(db, rule_id)
    _save_rule(db, "UPDATE setback_rules SET feature_type = :feature_type, distance_m = :distance_m, "
                   "measured_from = :measured_from, source = :source, note = :note WHERE id = :id RETURNING id",
               {**req.model_dump(), "id": rule_id})
    _log(db, admin, "setback_rule_updated", {"rule_id": rule_id, "before": before, "after": req.model_dump()})
    db.commit()
    return _rule_or_404(db, rule_id)


@router.delete("/setback-rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, db: Session = Depends(get_session), admin: Officer = Depends(admin_officer)):
    before = _rule_or_404(db, rule_id)
    db.execute(text("DELETE FROM setback_rules WHERE id = :id"), {"id": rule_id})
    _log(db, admin, "setback_rule_deleted", {"rule_id": rule_id, "before": before})
    db.commit()
