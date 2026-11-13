"""Transfers, rokka/fukuwa, history and issue review, inside the rolled-back transaction of the workflow tests."""
from datetime import date
from fractions import Fraction

from sqlalchemy import text

from tests.test_parcel_workflows import client  # noqa: F401  (the rolled-back officer client fixture)


def parcel_with_one_owner(conn) -> tuple[int, int]:
    """An active parcel owned outright by one person, with no rokka."""
    row = conn.execute(text("""
        SELECT p.id, po.owner_id FROM parcels p JOIN parcel_ownership po ON po.parcel_id = p.id AND po.valid_to IS NULL
        WHERE p.status = 'active' AND po.share_num = po.share_den
          AND NOT EXISTS (SELECT 1 FROM rokka r WHERE r.parcel_id = p.id AND r.fukuwa_date IS NULL)
        ORDER BY p.id LIMIT 1
    """)).one()
    return row[0], row[1]


def two_other_owners(conn, exclude: int) -> list[int]:
    return conn.execute(text("SELECT id FROM owners WHERE owner_type = 'individual' AND id <> :e ORDER BY id LIMIT 2"),
                        {"e": exclude}).scalars().all()


def test_transfer_records_the_deed_and_moves_ownership(client):
    pid, seller = parcel_with_one_owner(client.conn)
    buyers = two_other_owners(client.conn, seller)
    body = {"deed_type": "rajinama", "deed_date": date.today().isoformat(), "deed_ref": "RJ-TEST-1",
            "owners": [{"owner_id": buyers[0], "share": "1/2"}, {"owner_id": buyers[1], "share": "1/2"}]}
    r = client.post(f"/api/officer/parcels/{pid}/transfer", json=body)
    assert r.status_code == 201, r.text
    own = client.get(f"/api/officer/parcels/{pid}/ownership").json()
    assert sorted(o["owner_id"] for o in own["current"]) == sorted(buyers)
    assert sum(Fraction(o["share"]) for o in own["current"]) == 1
    assert any(o["owner_id"] == seller and o["valid_to"] == body["deed_date"] for o in own["history"])
    timeline = client.get(f"/api/officer/parcels/{pid}/history").json()["timeline"]
    assert timeline[0]["title"] == "Ownership transfer" and timeline[0]["case_id"] == r.json()["case_id"]
    assert "→" in timeline[0]["detail"]


def test_transfer_rules(client):
    pid, seller = parcel_with_one_owner(client.conn)
    buyer = two_other_owners(client.conn, seller)[0]
    base = {"deed_type": "rajinama", "deed_date": date.today().isoformat()}
    same = {**base, "owners": [{"owner_id": seller, "share": "1"}]}
    assert client.post(f"/api/officer/parcels/{pid}/transfer", json=same).status_code == 422  # nothing changes
    half = {**base, "owners": [{"owner_id": buyer, "share": "1/2"}]}
    assert client.post(f"/api/officer/parcels/{pid}/transfer", json=half).status_code == 422  # shares add up to 1/2
    old = {**base, "deed_date": "1950-01-02", "owners": [{"owner_id": buyer, "share": "1"}]}
    assert client.post(f"/api/officer/parcels/{pid}/transfer", json=old).status_code == 422  # before current owners
    bad = {**base, "deed_type": "lottery", "owners": [{"owner_id": buyer, "share": "1"}]}
    assert client.post(f"/api/officer/parcels/{pid}/transfer", json=bad).status_code == 422


def test_rokka_blocks_transfer_until_fukuwa(client):
    pid, seller = parcel_with_one_owner(client.conn)
    buyer = two_other_owners(client.conn, seller)[0]
    hold = client.post(f"/api/officer/parcels/{pid}/rokka",
                       json={"requested_by_type": "bank", "requested_by_name": "Test Demo Bank", "reason": "loan"})
    assert hold.status_code == 201
    body = {"deed_type": "rajinama", "deed_date": date.today().isoformat(),
            "owners": [{"owner_id": buyer, "share": "1"}]}
    blocked = client.post(f"/api/officer/parcels/{pid}/transfer", json=body)
    assert blocked.status_code == 409 and "rokka" in blocked.json()["detail"]
    rokka_id = client.get(f"/api/officer/parcels/{pid}/ownership").json()["rokka"][0]["id"]
    assert rokka_id == hold.json()["rokka_id"]
    assert client.post(f"/api/officer/rokka/{rokka_id}/release", json={}).status_code == 200
    assert client.post(f"/api/officer/rokka/{rokka_id}/release", json={}).status_code == 409  # already released
    assert client.post(f"/api/officer/parcels/{pid}/transfer", json=body).status_code == 201
    kinds = [e["kind"] for e in client.get(f"/api/officer/parcels/{pid}/history").json()["timeline"][:3]]
    assert kinds == ["rajinama", "fukuwa", "rokka"]


def test_history_of_real_data(client):
    pid = client.conn.execute(text("SELECT child_id FROM parcel_lineage ORDER BY child_id LIMIT 1")).scalar()
    h = client.get(f"/api/officer/parcels/{pid}/history").json()
    assert h["lineage"]["parents"] and h["boundaries"][0]["valid_to"] is None
    assert any(e["title"] == "Created by split (kitta kaat)" for e in h["timeline"])
    updated = client.conn.execute(text("SELECT parcel_id FROM parcel_geometry_history ORDER BY id LIMIT 1")).scalar()
    hb = client.get(f"/api/officer/parcels/{updated}/history").json()
    assert len(hb["boundaries"]) >= 2 and hb["boundaries"][-1]["version"] == 1


def test_issue_review_cycle(client):
    listing = client.get("/api/officer/issues", params={"status": "open", "issue_type": "overlap"}).json()
    if not listing["issues"]:
        return  # no scan results loaded
    assert listing["counts"]["open"] >= listing["total"] > 0
    issue = listing["issues"][0]
    detail = client.get(f"/api/officer/issues/{issue['id']}").json()
    assert detail["parcel"]["geometry"]["type"] == "Polygon" and detail["other"] and detail["overlap_geometry"]
    assert client.post(f"/api/officer/issues/{issue['id']}/review", json={"status": "resolved"}).status_code == 422
    dispute = {"status": "dispute", "note": "Neighbours disagree"}
    r = client.post(f"/api/officer/issues/{issue['id']}/review", json=dispute)
    assert r.status_code == 200
    after = client.get(f"/api/officer/issues/{issue['id']}").json()
    assert after["status"] == "dispute" and after["reviewed_by"] == "Workflow Test"
    assert client.get("/api/officer/issues", params={"status": "dispute"}).json()["counts"]["dispute"] >= 1
