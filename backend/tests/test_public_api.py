"""Public API against the real database; skipped when it is not available."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db import engine
from app.main import app

ASAN = (85.3112, 27.7066)
OWNER_WORDS = ("owner", "lin", "share", "citizenship", "full_name")


@pytest.fixture(scope="module")
def client():
    try:
        with engine.connect() as c:
            if not c.execute(text("SELECT EXISTS (SELECT 1 FROM parcel_quadkeys)")).scalar():
                pytest.skip("quadtree is empty")
    except OperationalError:
        pytest.skip("database not reachable")
    with TestClient(app) as c:
        yield c


def _no_owner_fields(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert not any(w in k.lower() for w in OWNER_WORDS), k
            _no_owner_fields(v)
    elif isinstance(obj, list):
        for v in obj:
            _no_owner_fields(v)


def test_identify_and_details(client):
    r = client.get("/api/parcels/at", params={"lat": ASAN[1], "lng": ASAN[0]})
    assert r.status_code == 200
    body = r.json()
    assert body["parcel"] and body["stats"]["rows_read"] < 200
    d = client.get(f"/api/parcels/{body['parcel']['id']}").json()
    assert d["pin"] == body["parcel"]["pin"] and d["geometry"]["type"] == "Polygon"
    assert abs(d["boundary_area_m2"] - d["area_m2"]) < d["area_m2"] * 0.2
    _no_owner_fields(d)


def test_click_on_empty_land_finds_nothing(client):
    r = client.get("/api/parcels/at", params={"lat": 27.60, "lng": 85.20})  # outside KMC
    assert r.status_code == 200 and r.json()["parcel"] is None


def test_in_view_returns_outlines_or_asks_to_zoom(client):
    w, s, e, n = ASAN[0] - 0.001, ASAN[1] - 0.001, ASAN[0] + 0.001, ASAN[1] + 0.001
    fc = client.get("/api/parcels/in-view", params={"west": w, "south": s, "east": e, "north": n}).json()
    assert fc["features"] and not fc["too_many"]
    f = fc["features"][0]
    assert set(f["properties"]) == {"pin", "kitta", "ward", "land_use", "label"}
    big = client.get("/api/parcels/in-view", params={"west": 85.25, "south": 27.65, "east": 85.37, "north": 27.75})
    assert big.json()["too_many"] is True


def test_select_and_buffer(client):
    box = [ASAN[0] - 0.0005, ASAN[1] - 0.0005, ASAN[0] + 0.0005, ASAN[1] + 0.0005]
    sel = client.post("/api/parcels/select", json={"box": box}).json()
    assert sel["count"] > 0 and sel["count"] == len(sel["parcels"])
    line = client.post("/api/parcels/select", json={"line": [box[:2], box[2:]]}).json()
    assert 0 < line["count"] < sel["count"]
    buf = client.post("/api/parcels/buffer", json={"point": list(ASAN), "distance_m": 40}).json()
    assert buf["count"] > 0 and buf["zone"]["type"] == "Polygon"
    _no_owner_fields(buf)


def test_bad_requests_are_rejected(client):
    assert client.post("/api/parcels/select", json={}).status_code == 422
    assert client.post("/api/parcels/buffer", json={"point": list(ASAN), "line": [ASAN, ASAN]}).status_code == 422
    assert client.get("/api/parcels/999999999").status_code == 404


def test_search_by_pin_and_kitta(client):
    pin = client.get("/api/parcels/at", params={"lat": ASAN[1], "lng": ASAN[0]}).json()["parcel"]["pin"]
    assert client.get("/api/parcels/search", params={"q": pin.lower()}).json()[0]["pin"] == pin
    ward, kitta = int(pin.split("-")[1]), int(pin.split("-")[3])
    hits = client.get("/api/parcels/search", params={"q": f"ward {ward} kitta {kitta}"}).json()
    assert pin in [h["pin"] for h in hits]


def test_outlines_for_result_ids(client):
    pid = client.get("/api/parcels/at", params={"lat": ASAN[1], "lng": ASAN[0]}).json()["parcel"]["id"]
    fc = client.post("/api/parcels/outlines", json={"ids": [pid]}).json()
    assert [f["id"] for f in fc["features"]] == [pid]
    assert client.post("/api/parcels/outlines", json={"ids": list(range(5001))}).status_code == 422
