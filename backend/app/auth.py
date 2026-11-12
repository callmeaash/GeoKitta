"""Officer authentication: argon2 password hashes, a signed JWT in an HttpOnly cookie, and route guards."""
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session

COOKIE = "geokitta_session"
MAX_FAILURES = 5  # failed logins per username before a pause
FAILURE_WINDOW_S = 15 * 60

_hasher = PasswordHasher()
_failures: dict[str, deque] = defaultdict(deque)


@dataclass(frozen=True)
class Officer:
    id: int
    username: str
    full_name: str
    office: str | None
    is_admin: bool


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False  # wrong password, or a disabled account whose hash is not an argon2 hash


def _secret() -> str:
    if len(settings.jwt_secret) < 32:
        raise HTTPException(503, "officer login is not configured: set JWT_SECRET in .env")
    return settings.jwt_secret


def make_token(officer_id: int) -> str:
    now = datetime.now(timezone.utc)
    claims = {"sub": str(officer_id), "iat": now, "exp": now + timedelta(hours=settings.session_hours)}
    return jwt.encode(claims, _secret(), algorithm="HS256")


def set_session(response: Response, officer_id: int) -> None:
    response.set_cookie(COOKIE, make_token(officer_id), max_age=settings.session_hours * 3600, httponly=True,
                        samesite="lax", secure=settings.cookie_secure, path="/api")


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/api")


def too_many_failures(username: str) -> int:
    """Seconds to wait before this username may try again (0 = allowed)."""
    q = _failures[username]
    while q and q[0] < time.monotonic() - FAILURE_WINDOW_S:
        q.popleft()
    return int(q[0] + FAILURE_WINDOW_S - time.monotonic()) + 1 if len(q) >= MAX_FAILURES else 0


def record_failure(username: str) -> None:
    _failures[username].append(time.monotonic())


def clear_failures(username: str) -> None:
    _failures.pop(username, None)


def load_officer(db: Session, officer_id: int) -> Officer | None:
    row = db.execute(text("SELECT id, username, full_name, office, is_admin FROM officers "
                          "WHERE id = :id AND is_active"), {"id": officer_id}).one_or_none()
    return Officer(*row) if row else None


def optional_officer(request: Request, db: Session = Depends(get_session)) -> Officer | None:
    """The signed-in officer, or None for the public."""
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    try:
        claims = jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None  # expired or tampered
    return load_officer(db, int(claims["sub"]))  # a disabled account loses access at once


def current_officer(officer: Officer | None = Depends(optional_officer)) -> Officer:
    """Guard for officer routes."""
    if officer is None:
        raise HTTPException(401, "sign in as an officer")
    return officer


def admin_officer(officer: Officer = Depends(current_officer)) -> Officer:
    if not officer.is_admin:
        raise HTTPException(403, "admin only")
    return officer
