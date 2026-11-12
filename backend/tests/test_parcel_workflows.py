"""Register, update boundary and split against the real database inside one transaction that is rolled back."""
import csv
import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import ROOT, settings
from app.db import engine, get_session
from app.main import app
from app.spatial.geometry import box_of
from app.spatial.projection import to_wgs

SURVEY = ROOT / "data" / "generated" / "survey"
PASSWORD = secrets.token_urlsafe(16)


def read_points(name: str) -> list[list[float]]:
    path = SURVEY / name
    if not path.exists():
        pytest.skip(f"no survey sample {name}; run the pipeline")
    with open(path, newline="", encoding="utf-8") as f:
        return [[float(r["easting"]), float(r["northing"])] for r in csv.DictReader(f)]


def survey_file(prefix: str) -> str:
    found = sorted(p.name for p in SURVEY.glob(f"{prefix}*.csv")) if SURVEY.exists() else []
    if not found:
        pytest.skip(f"no survey sample {prefix}*; run the pipeline")
    return found[0]


def centre(points) -> tuple[float, float]:
    b = box_of([tuple(p) for p in points])
    lng, lat = to_wgs((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
    return lat, lng


@pytest.fixture
def client():
    if len(settings.jwt_secret) < 32:
        pytest.skip("JWT_SECRET is not set")
    try:
        conn = engine.connect()
    except OperationalError:
        pytest.skip("database not reachable")
    outer = conn.begin()  # everything below is rolled back at the end

    def session():
        with Session(bind=conn, join_transaction_mode="create_savepoint") as s:
            yield s

    conn.execute(text("INSERT INTO officers (username, password_hash, full_name, office) "
                      "VALUES ('workflow.test', :h, 'Workflow Test', 'Test office')"), {"h": hash_password(PASSWORD)})
    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app) as c:
            r = c.post("/api/auth/login", json={"username": "workflow.test", "password": PASSWORD})
            assert r.status_code == 200
            c.conn = conn
            yield c
    finally:
        app.dependency_overrides.clear()
        outer.rollback()
        conn.close()


def an_owner(conn) -> int:
    return conn.execute(text("SELECT id FROM owners WHERE owner_type = 'individual' ORDER BY id LIMIT 1")).scalar()


def test_register_the_vacant_plot(client):
    pts = read_points("register_vacant_plot.csv")
    check = client.post("/api/officer/parcels/check", json={"points": pts, "crs": "utm"}).json()
    assert check["report"]["ok"] and not check["report"]["overlaps"], check["report"]["checks"]
    s = check["suggestion"]
    assert s["ward"] and s["map_sheet"] and s["kitta"]
    body = {"points": pts, "crs": "utm", "ward": s["ward"], "map_sheet": s["map_sheet"],
            "registered_area": check["report"]["area_m2"],
            "owners": [{"owner_id": an_owner(client.conn), "share": "1"}]}
    r = client.post("/api/officer/parcels", json=body)
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["kitta"] == s["kitta"] and new["pin"].startswith(f"KTM-{s['ward']:02d}-")
    lat, lng = centre(pts)
    assert client.get("/api/parcels/at", params={"lat": lat, "lng": lng}).json()["parcel"]["id"] == new["parcel_id"]
    owners = client.get(f"/api/officer/parcels/{new['parcel_id']}/ownership").json()["current"]
    assert [o["share"] for o in owners] == ["1"]
    assert client.conn.execute(text("SELECT count(*) FROM audit_log WHERE parcel_id = :p AND action = "
                                    "'parcel_registered'"), {"p": new["parcel_id"]}).scalar() == 1
    again = client.post("/api/officer/parcels", json={**body, "kitta": new["kitta"]})
    assert again.status_code == 409  # kitta number already used on the sheet


def test_overlapping_registration_is_refused_unless_flagged(client):
    pid = client.get("/api/parcels/at", params={"lat": 27.7066, "lng": 85.3112}).json()["parcel"]["id"]
    geom = client.get(f"/api/parcels/{pid}").json()["geometry"]
    pts = [list(p) for p in geom["coordinates"][0][:-1]]  # a copy of an existing parcel
    check = client.post("/api/officer/parcels/check", json={"points": pts, "crs": "wgs84"}).json()["report"]
    assert not check["ok"] and pid in [o["parcel_id"] for o in check["overlaps"]]
    body = {"points": pts, "crs": "wgs84", "ward": 1, "map_sheet": "272010010", "registered_area": 100,
            "owners": [{"owner_id": an_owner(client.conn), "share": "1"}]}
    assert client.post("/api/officer/parcels", json=body).status_code == 409
    r = client.post("/api/officer/parcels", json={**body, "accept_issues": True})
    assert r.status_code == 201 and any("overlap" in i for i in r.json()["issues"])
    assert client.conn.execute(text("SELECT count(*) FROM parcel_issues WHERE parcel_id = :p AND issue_type = "
                                    "'overlap' AND other_parcel_id = :o"),
                               {"p": r.json()["parcel_id"], "o": pid}).scalar() == 1


def test_bad_input_is_rejected(client):
    bowtie = [[335000, 3066000], [335010, 3066010], [335010, 3066000], [335000, 3066010]]
    report = client.post("/api/officer/parcels/check", json={"points": bowtie, "crs": "utm"}).json()["report"]
    assert report["checks"][0]["status"] == "fail" and "cross" in report["checks"][0]["detail"]
    owners = [{"owner_id": 1, "share": "1/2"}]
    body = {"points": bowtie, "crs": "utm", "ward": 1, "map_sheet": "272010010", "registered_area": 50,
            "owners": owners}
    assert client.post("/api/officer/parcels", json=body).status_code == 422  # shares do not add up to 1
    latlng_as_utm = {"points": [[85.3, 27.7]] * 3, "crs": "utm"}
    assert client.post("/api/officer/parcels/check", json=latlng_as_utm).status_code == 422


def test_update_boundary_keeps_history_and_moves_the_index(client):
    name = survey_file("update_")
    pin = name[len("update_"):-4]
    pid = client.conn.execute(text("SELECT id FROM parcels WHERE pin = :p AND status = 'active'"), {"p": pin}).scalar()
    if pid is None:
        pytest.skip("sample parcel is not active")
    pts = read_points(name)
    check = client.post(f"/api/officer/parcels/{pid}/boundary/check", json={"points": pts, "crs": "utm"}).json()
    assert check["report"]["ok"], check["report"]["checks"]
    assert check["report"]["area_m2"] < check["old_area_m2"]  # the sample moves one corner inwards
    r = client.post(f"/api/officer/parcels/{pid}/boundary", json={"points": pts, "crs": "utm", "surveyor": "Test"})
    assert r.status_code == 200, r.text
    history = client.conn.execute(text("SELECT count(*) FROM parcel_geometry_history WHERE transaction_id = "
                                       "(SELECT id FROM transactions WHERE case_id = :c)"),
                                  {"c": r.json()["case_id"]}).scalar()
    assert history == 1
    lat, lng = centre(pts)
    assert client.get("/api/parcels/at", params={"lat": lat, "lng": lng}).json()["parcel"]["id"] == pid


def test_split_retires_the_parent_and_creates_children(client):
    a = survey_file("split_")
    pin = a[len("split_"):-6]
    pid = client.conn.execute(text("SELECT id FROM parcels WHERE pin = :p AND status = 'active'"), {"p": pin}).scalar()
    if pid is None:
        pytest.skip("sample parcel is not active")
    kids = [{"points": read_points(f"split_{pin}_{x}.csv"), "crs": "utm"} for x in "AB"]
    check = client.post(f"/api/officer/parcels/{pid}/split/check", json={"children": kids}).json()
    assert check["ok"], check["checks"]
    bad = client.post(f"/api/officer/parcels/{pid}/split/check", json={"children": [kids[0], kids[0]]}).json()
    assert not bad["ok"] and {c["id"]: c["status"] for c in bad["checks"]}["children_apart"] == "fail"
    assert client.post(f"/api/officer/parcels/{pid}/split", json={"children": [kids[0], kids[0]]}).status_code == 409

    parent_owners = client.get(f"/api/officer/parcels/{pid}/ownership").json()["current"]
    r = client.post(f"/api/officer/parcels/{pid}/split", json={"children": kids})
    assert r.status_code == 201, r.text
    children = r.json()["children"]
    assert len(children) == 2 and children[1]["kitta"] == children[0]["kitta"] + 1
    assert client.get(f"/api/parcels/{pid}").status_code == 404  # parent retired
    for child, kid in zip(children, kids):
        lat, lng = centre(kid["points"])
        found = client.get("/api/parcels/at", params={"lat": lat, "lng": lng}).json()["parcel"]
        assert found["id"] == child["parcel_id"]
        owners = client.get(f"/api/officer/parcels/{child['parcel_id']}/ownership").json()["current"]
        assert sorted((o["owner_id"], o["share"]) for o in owners) == \
            sorted((o["owner_id"], o["share"]) for o in parent_owners)
    lineage = client.conn.execute(text("SELECT count(*) FROM parcel_lineage WHERE parent_id = :p"), {"p": pid}).scalar()
    assert lineage == 2


def test_parcel_routes_need_login(client):
    client.cookies.clear()
    assert client.post("/api/officer/parcels/check", json={"points": [[0, 0]] * 3}).status_code == 401
