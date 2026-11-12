"""Officer login and officer-only API against the real database; test accounts and owners are removed after."""
import json
import re
import secrets
from fractions import Fraction

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.api import officer as officer_api
from app.auth import COOKIE, hash_password
from app.config import ROOT, settings
from app.db import engine
from app.main import app

USERNAME = "test.officer"
PASSWORD = secrets.token_urlsafe(16)
OFFICER_ROUTES = ["/api/officer/dashboard", "/api/officer/owners?q=ram", "/api/officer/owners/1",
                  "/api/officer/parcels/1/ownership"]


def _cleanup(conn):
    ids = conn.execute(text("SELECT id FROM officers WHERE username = :u"), {"u": USERNAME}).scalars().all()
    if ids:
        owners = conn.execute(text("SELECT CAST(details ->> 'owner_id' AS int) FROM audit_log "
                                   "WHERE officer_id = ANY(:i) AND action = 'owner_registered'"), {"i": ids})
        owner_ids = [o for o in owners.scalars() if o]
        conn.execute(text("DELETE FROM audit_log WHERE officer_id = ANY(:i)"), {"i": ids})
        conn.execute(text("DELETE FROM owners WHERE id = ANY(:o)"), {"o": owner_ids})
        for o in owner_ids:
            officer_api.owners_index().remove(o)
        conn.execute(text("DELETE FROM officers WHERE id = ANY(:i)"), {"i": ids})


@pytest.fixture(scope="module")
def client():
    if len(settings.jwt_secret) < 32:
        pytest.skip("JWT_SECRET is not set")
    try:
        with engine.begin() as conn:
            _cleanup(conn)
            conn.execute(text("INSERT INTO officers (username, password_hash, full_name, office) "
                              "VALUES (:u, :h, 'Test Officer', 'Test office')"),
                         {"u": USERNAME, "h": hash_password(PASSWORD)})
    except OperationalError:
        pytest.skip("database not reachable")
    with TestClient(app) as c:
        yield c
    with engine.begin() as conn:
        _cleanup(conn)


def _login(c):
    r = c.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r


def test_officer_routes_need_login(client):
    client.cookies.clear()
    for route in OFFICER_ROUTES:
        assert client.get(route).status_code == 401, route
    assert client.post("/api/officer/owners", json={}).status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_login_sets_an_httponly_cookie_and_logout_clears_it(client):
    client.cookies.clear()
    r = _login(client)
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=") and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    assert PASSWORD not in cookie
    assert client.get("/api/auth/me").json()["username"] == USERNAME
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401


def test_wrong_password_and_tampered_cookie_are_refused(client):
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"username": USERNAME, "password": "wrong-password"})
    assert r.status_code == 401 and r.json()["detail"] == "wrong username or password"
    client.cookies.set(COOKIE, "not.a.token", path="/api")
    assert client.get("/api/officer/dashboard").status_code == 401
    client.cookies.clear()


def test_repeated_failures_are_paused(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "nobody.here", "password": "x"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "nobody.here", "password": "x"}).status_code == 429


def test_dashboard_and_owner_search(client):
    _login(client)
    d = client.get("/api/officer/dashboard").json()
    assert d["active_parcels"] > 0 and d["owners"] > 0 and len(d["recent_transactions"]) > 0
    assert any(a["action"] == "login" for a in d["recent_activity"])
    hits = client.get("/api/officer/owners", params={"q": "Lakshmi"}).json()
    assert hits and all("laxmi" in h["full_name"].lower() or "lakshmi" in h["full_name"].lower() for h in hits)
    lin = hits[0]["lin"]
    assert client.get("/api/officer/owners", params={"q": lin}).json()[0]["lin"] == lin
    owner = client.get(f"/api/officer/owners/{hits[0]['id']}").json()
    assert owner["lin"] == lin and isinstance(owner["current"], list)


def test_parcel_ownership_shares_add_up(client):
    _login(client)
    pid = client.get("/api/parcels/at", params={"lat": 27.7066, "lng": 85.3112}).json()["parcel"]["id"]
    body = client.get(f"/api/officer/parcels/{pid}/ownership").json()
    assert body["current"]
    assert sum(Fraction(o["share"]) for o in body["current"]) == 1


def _planted_pair(client):
    key = ROOT / "data" / "generated" / "defects.json"
    if not key.exists():
        pytest.skip("no answer key")
    pair = next(d for d in json.loads(key.read_text("utf-8")) if d["type"] == "duplicate_owner")
    hits = client.get("/api/officer/owners", params={"q": pair["original_lin"]}).json()
    if not hits:
        pytest.skip("answer key does not match the loaded data")
    return pair, hits[0]


def test_planted_duplicate_is_flagged_and_registration_is_guarded(client):
    _login(client)
    pair, original = _planted_pair(client)
    new = {"owner_type": "individual", "full_name": pair["duplicate"], "gender": original["gender"],
           "date_of_birth": original["date_of_birth"], "district_code": original["district_code"]}
    similar = client.post("/api/officer/owners/similar", json=new).json()
    flagged = [s for s in similar if s["likely_duplicate"]]
    assert original["lin"] in [s["lin"] for s in flagged]

    r = client.post("/api/officer/owners", json=new)
    assert r.status_code == 409 and original["lin"] in [s["lin"] for s in r.json()["similar"]]

    r = client.post("/api/officer/owners", json={**new, "confirm_new": True})
    assert r.status_code == 201
    saved = r.json()
    assert re.fullmatch(r"\d{2}-\d{6}-[MFX]", saved["lin"]) and saved["parcels"] == 0
    assert saved["id"] in [m.id for m in officer_api.owners_index().search(pair["duplicate"], limit=500)]


def test_bad_owner_data_is_rejected(client):
    _login(client)
    assert client.post("/api/officer/owners", json={"owner_type": "individual", "full_name": "No Birthday"}
                       ).status_code == 422
    assert client.post("/api/officer/owners", json={"owner_type": "individual", "full_name": "Future Person",
                                                    "gender": "male", "date_of_birth": "2999-01-01"}).status_code == 422
