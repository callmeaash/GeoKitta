"""Validation checks: hand-written geometry tests, then the planted defects in the real data."""
import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config import ROOT
from app.db import engine
from app.spatial.geometry import box_ring, interiors_overlap, ring_problem, within_polygon
from app.spatial.index import load_polygons
from app.validation import FAIL, PASS, WARN, InputError, check_area, check_shape, polygon_from_points, validate

SQ = [box_ring((0, 0, 10, 10))]


def shifted(poly, dx, dy=0.0):
    return [[(x + dx, y + dy) for x, y in ring] for ring in poly]


@pytest.mark.parametrize("ring, problem", [
    ([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)], None),
    ([(0, 0), (10, 10), (10, 0), (0, 10), (0, 0)], "cross"),  # bow-tie
    ([(0, 0), (10, 0), (10, 0), (0, 10), (0, 0)], "same point"),
    ([(0, 0), (10, 0), (5, 0), (5, 5), (0, 0)], "folds back"),  # spike along the first edge
    ([(0, 0), (10, 0), (0, 0)], "at least 3"),
    ([(0, 0), (10, 0), (10, 10), (0, 10)], "closed"),
])
def test_ring_problem(ring, problem):
    found = ring_problem(ring)
    assert (found is None) if problem is None else (problem in found)


def test_interiors_overlap_cases():
    assert not interiors_overlap(SQ, shifted(SQ, 10))  # neighbours sharing an edge only touch
    assert not interiors_overlap(SQ, shifted(SQ, 10, 10))  # touching at one corner
    assert not interiors_overlap(SQ, shifted(SQ, 10.005))  # 5 mm gap is still "touching"
    assert interiors_overlap(SQ, shifted(SQ, 9.5))  # shifted half a metre into the neighbour
    assert interiors_overlap(SQ, SQ)  # identical copy: no corner strictly inside, no crossing
    assert interiors_overlap(SQ, [box_ring((2, 2, 4, 4))])  # one inside the other
    assert interiors_overlap(SQ, [box_ring((0, 0, 5, 10))])  # inside, sharing three edges
    plus_h, plus_v = [box_ring((0, 4, 10, 6))], [box_ring((4, 0, 6, 10))]
    assert interiors_overlap(plus_h, plus_v)  # plus sign: only edge crossings reveal it


def test_within_polygon_for_split_children():
    left, right = [box_ring((0, 0, 5, 10))], [box_ring((5, 0, 10, 10))]
    assert within_polygon(left, SQ) and within_polygon(right, SQ)
    assert not within_polygon([box_ring((5, 0, 11, 10))], SQ)
    u = [[(0, 0), (10, 0), (10, 10), (6, 10), (6, 4), (4, 4), (4, 10), (0, 10), (0, 0)]]
    assert not within_polygon([box_ring((3, 5, 7, 6))], u)  # corners inside the U, middle crosses the notch


def test_area_and_shape_checks():
    assert check_area(100, 104).status == PASS and check_area(100, 110).status == WARN
    assert check_shape(0.35 * 20, 2 * 20.35).status == WARN  # a 0.35 m strip
    assert check_shape(200, 60).status == PASS  # 10 x 20 m plot
    assert check_shape(3 * 200, 2 * 203).status == PASS  # long 3 m roadside strip is not a sliver


def test_input_conversion():
    poly = polygon_from_points([[335000, 3066000], [335010, 3066000], [335010, 3066010]], "utm")
    assert poly[0][0] == poly[0][-1] and len(poly[0]) == 4  # ring closed automatically
    assert abs(poly[0][1][0] - 335010) < 0.02  # survives the trip through stored lat/lng
    with pytest.raises(InputError):
        polygon_from_points([[85.3, 27.7], [85.31, 27.7], [85.31, 27.71]], "utm")  # lat/lng given as UTM
    with pytest.raises(InputError):
        polygon_from_points([[1, 2], [3, 4]], "utm")


# ---------- planted defects in the loaded data ----------

@pytest.fixture(scope="module")
def planted():
    key = ROOT / "data" / "generated" / "defects.json"
    if not key.exists():
        pytest.skip("no answer key")
    try:
        conn = engine.connect()
    except OperationalError:
        pytest.skip("database not reachable")
    defects = [d for d in json.loads(key.read_text("utf-8")) if d["type"] != "duplicate_owner"]
    pins = {p for d in defects for p in d["pins"]}  # side overlaps may since have been split, so only these
    ids = dict(conn.execute(text("SELECT pin, id FROM parcels WHERE pin = ANY(:p) AND status = 'active'"),
                            {"p": list(pins)}).all())
    if len(ids) < len(pins):
        conn.close()
        pytest.skip("answer key does not match the loaded data")
    yield conn, defects, ids
    conn.close()


def test_every_planted_geometry_defect_is_caught_on_save(planted):
    conn, defects, ids = planted
    polys = load_polygons(conn, ids.values())
    regs = dict(conn.execute(text("SELECT id, registered_area FROM parcels WHERE id = ANY(:i)"),
                             {"i": list(ids.values())}).all())
    for d in defects:
        a = ids[d["pins"][0]]
        report = validate(conn, polys[a], float(regs[a]), exclude={a})
        status = {c.id: c.status for c in report.checks}
        if d["type"] in ("overlap", "overlap_cross"):
            b = ids[d["pins"][1]]
            assert interiors_overlap(polys[a], polys[b]), d
            assert status["overlap"] == FAIL and b in [o.parcel_id for o in report.overlaps], d
        elif d["type"] == "sliver":
            assert status["sliver"] == WARN, d
        elif d["type"] == "area_mismatch":
            assert status["area"] == WARN, d


def test_scan_recorded_every_planted_defect(planted):
    conn, defects, ids = planted
    rows = conn.execute(text("SELECT issue_type, parcel_id, other_parcel_id FROM parcel_issues "
                             "WHERE details ->> 'source' = 'scan'")).all()
    if not rows:
        pytest.skip("run python -m app.scan first")
    found = {(r[0], r[1]) for r in rows} | {(r[0], r[2]) for r in rows if r[2]}
    kind = {"overlap": "overlap", "overlap_cross": "overlap", "sliver": "sliver", "area_mismatch": "area_mismatch"}
    for d in defects:
        for pin in d["pins"]:
            assert (kind[d["type"]], ids[pin]) in found, d
