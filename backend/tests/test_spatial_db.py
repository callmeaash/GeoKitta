"""Linear quadtree against the real database: brute-force agreement and index updates (all changes rolled back)."""
import random

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db import engine
from app.spatial import quadkey as qk
from app.spatial.bruteforce import BruteForceIndex
from app.spatial.index import QuadtreeIndex, index_parcel, load_polygons, unindex_parcel
from app.spatial.projection import line_from_geojson
from app.spatial.queries import identify, in_box, near_line


@pytest.fixture(scope="module")
def conn():
    try:
        connection = engine.connect()
    except OperationalError:
        pytest.skip("database not reachable")
    if not connection.execute(text("SELECT EXISTS (SELECT 1 FROM parcel_quadkeys)")).scalar():
        connection.close()
        pytest.skip("quadtree is empty; run python -m app.spatial.reindex")
    yield connection
    connection.close()


@pytest.fixture(scope="module")
def brute(conn):
    return BruteForceIndex.load(conn)


@pytest.fixture(scope="module")
def sample_points(brute):
    rng = random.Random(42)
    ids = rng.sample(sorted(brute._polygons), 60)
    points = []
    for pid in ids:  # a vertex nudged inwards, plus a random spot near the parcel
        ring = brute._polygons[pid][0]
        cx = sum(p[0] for p in ring[:-1]) / (len(ring) - 1)
        cy = sum(p[1] for p in ring[:-1]) / (len(ring) - 1)
        points.append((ring[0][0] * 0.9 + cx * 0.1, ring[0][1] * 0.9 + cy * 0.1))
        points.append((cx + rng.uniform(-30, 30), cy + rng.uniform(-30, 30)))
    return points


def test_identify_matches_brute_force(conn, brute, sample_points):
    quad = QuadtreeIndex(conn)
    for p in sample_points:
        assert identify(quad, p) == identify(brute, p), p
        assert quad.stats["rows_read"] < 200  # a click reads a handful of rows, not the table


def test_candidates_and_selection_match_brute_force(conn, brute, sample_points):
    quad = QuadtreeIndex(conn)
    rng = random.Random(3)
    centre = (qk.ROOT_X + qk.ROOT_SIZE / 2, qk.ROOT_Y + qk.ROOT_SIZE / 2)
    boxes = [(x - s, y - s * 0.6, x + s, y + s * 0.6)
             for (x, y), s in zip(sample_points[:20], [rng.uniform(5, 400) for _ in range(20)])]
    boxes.append((centre[0] - 60, centre[1] - 60, centre[0] + 60, centre[1] + 60))  # across the root's centre lines
    for box in boxes:
        assert quad.candidates(box) == brute.candidates(box)
        assert in_box(quad, box) == in_box(brute, box)


def test_near_line_matches_brute_force(conn, brute):
    rows = conn.execute(text("SELECT ST_AsGeoJSON(geom) FROM features WHERE feature_type IN ('road', 'river') "
                             "ORDER BY id LIMIT 6")).scalars().all()
    quad = QuadtreeIndex(conn)
    for gj in rows:
        line = line_from_geojson(gj)
        assert near_line(quad, line, 15) == near_line(brute, line, 15)


def test_insert_update_delete_change_query_results(conn):
    pid = conn.execute(text("SELECT parcel_id FROM parcel_quadkeys ORDER BY parcel_id LIMIT 1")).scalar()
    polygon = load_polygons(conn, [pid])[pid]
    ring = polygon[0]
    inner = ((ring[0][0] * 9 + sum(p[0] for p in ring[:-1]) / (len(ring) - 1)) / 10,
             (ring[0][1] * 9 + sum(p[1] for p in ring[:-1]) / (len(ring) - 1)) / 10)
    tx = conn.begin_nested() if conn.in_transaction() else conn.begin()
    try:
        quad = QuadtreeIndex(conn)
        assert pid in quad.candidates((*inner, *inner))

        unindex_parcel(conn, pid)  # delete
        assert pid not in quad.candidates((*inner, *inner))

        shift = 2000.0  # update: the parcel moves 2 km east
        moved = [[(x + shift, y) for x, y in r] for r in polygon]
        index_parcel(conn, pid, moved)
        index_parcel(conn, pid, moved)  # re-indexing replaces, never duplicates
        assert pid not in quad.candidates((*inner, *inner))
        assert pid in quad.candidates((inner[0] + shift, inner[1], inner[0] + shift, inner[1]))
        keys = conn.execute(text("SELECT quadkey FROM parcel_quadkeys WHERE parcel_id = :p"), {"p": pid}).scalars()
        keys = keys.all()
        assert 1 <= len(keys) <= 4 and len(set(keys)) == len(keys)
    finally:
        tx.rollback()
    assert pid in QuadtreeIndex(conn).candidates((*inner, *inner))  # rollback restored the entries
