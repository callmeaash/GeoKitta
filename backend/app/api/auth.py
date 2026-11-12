"""Officer sign in and sign out."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import (Officer, clear_failures, clear_session, current_officer, record_failure, set_session,
                      too_many_failures, verify_password)
from app.db import get_session
from app.schemas import LoginRequest, OfficerOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _out(o: Officer) -> OfficerOut:
    return OfficerOut(id=o.id, username=o.username, full_name=o.full_name, office=o.office, is_admin=o.is_admin)


@router.post("/login", response_model=OfficerOut)
def login(req: LoginRequest, response: Response, db: Session = Depends(get_session)):
    username = req.username.strip().lower()
    wait = too_many_failures(username)
    if wait:
        raise HTTPException(429, f"too many failed attempts; try again in {wait // 60 + 1} minutes")
    row = db.execute(text("SELECT id, username, full_name, office, is_admin, password_hash FROM officers "
                          "WHERE username = :u AND is_active"), {"u": username}).one_or_none()
    if row is None or not verify_password(row[5], req.password):
        record_failure(username)
        raise HTTPException(401, "wrong username or password")  # same message whether or not the user exists
    clear_failures(username)
    officer = Officer(*row[:5])
    db.execute(text("UPDATE officers SET last_login_at = now() WHERE id = :id"), {"id": officer.id})
    db.execute(text("INSERT INTO audit_log (officer_id, action) VALUES (:id, 'login')"), {"id": officer.id})
    db.commit()
    set_session(response, officer.id)
    return _out(officer)


@router.post("/logout", status_code=204)
def logout(response: Response):
    clear_session(response)


@router.get("/me", response_model=OfficerOut)
def me(officer: Officer = Depends(current_officer)):
    return _out(officer)
