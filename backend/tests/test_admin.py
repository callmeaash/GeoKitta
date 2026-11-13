"""Admin routes inside the rolled-back transaction of the workflow tests (the test officer is made admin there)."""
import secrets

from sqlalchemy import text

from tests.test_parcel_workflows import client  # noqa: F401


def make_admin(client, admin: bool):
    client.conn.execute(text("UPDATE officers SET is_admin = :a WHERE username = 'workflow.test'"), {"a": admin})


def test_admin_routes_need_the_admin_flag(client):
    make_admin(client, False)
    assert client.get("/api/admin/officers").status_code == 403
    assert client.post("/api/admin/setback-rules", json={}).status_code == 403


def test_officer_accounts(client):
    make_admin(client, True)
    pw = secrets.token_urlsafe(12)
    new = {"username": "new.officer", "full_name": "New Officer", "office": "Test office", "password": pw}
    r = client.post("/api/admin/officers", json=new)
    assert r.status_code == 201
    assert client.post("/api/admin/officers", json=new).status_code == 409  # username taken
    short = {**new, "username": "x2.officer", "password": "short"}
    assert client.post("/api/admin/officers", json=short).status_code == 422
    listing = client.get("/api/admin/officers").json()
    assert "new.officer" in [o["username"] for o in listing] and "pipeline" not in [o["username"] for o in listing]
    oid = r.json()["id"]
    disabled = client.patch(f"/api/admin/officers/{oid}", json={"is_active": False}).json()
    assert disabled["changed"] == {"is_active": False}
    reset = {"password": secrets.token_urlsafe(12)}
    assert client.post(f"/api/admin/officers/{oid}/password", json=reset).status_code == 200
    me = next(o["id"] for o in listing if o["username"] == "workflow.test")
    assert client.patch(f"/api/admin/officers/{me}", json={"is_active": False}).status_code == 409  # not yourself
    audit = client.conn.execute(text("SELECT details::text FROM audit_log WHERE action = 'password_reset' "
                                     "ORDER BY id DESC LIMIT 1")).scalar()
    assert pw not in audit and "new.officer" in audit


def test_setback_rules_change_the_setback_search(client):
    make_admin(client, True)
    rules = client.get("/api/setback-rules").json()
    river = next(r for r in rules if r["feature_type"] == "river")
    body = {k: river[k] for k in ("feature_type", "measured_from", "source", "note")}
    dup = client.post("/api/admin/setback-rules", json={**body, "distance_m": 20})
    assert dup.status_code == 409  # one rule per feature type and source
    wider = client.put(f"/api/admin/setback-rules/{river['id']}", json={**body, "distance_m": 30})
    assert wider.status_code == 200 and wider.json()["distance_m"] == 30
    assert next(r for r in client.get("/api/setback-rules").json() if r["id"] == river["id"])["distance_m"] == 30
    new = client.post("/api/admin/setback-rules", json={"feature_type": "road", "distance_m": 6,
                                                        "measured_from": "centre_line", "source": "municipal"})
    assert new.status_code == 201
    assert client.delete(f"/api/admin/setback-rules/{new.json()['id']}").status_code == 204
    assert client.delete(f"/api/admin/setback-rules/{new.json()['id']}").status_code == 404
