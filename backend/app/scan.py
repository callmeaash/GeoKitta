"""Validate every active parcel and record problems in parcel_issues: python -m app.scan (from backend/)."""
import json
import sys
import time

from sqlalchemy import Connection, text

from app.db import engine
from app.spatial.geometry import box_of, interiors_overlap, perimeter, polygon_area, ring_problem
from app.spatial.memory import MemoryQuadtree
from app.spatial.projection import polygons_from_geojson
from app.validation import MIN_OVERLAP_M2, PASS, check_area, check_shape


def find_issues(conn: Connection, progress=None) -> tuple[list[dict], dict]:
    """Issue rows for every active parcel; overlap pairs come from the in-memory quadtree plus the exact test."""
    rows = conn.execute(text("SELECT id, registered_area, ST_AsGeoJSON(boundary) FROM parcels "
                             "WHERE status = 'active' ORDER BY id")).all()
    ids = [r[0] for r in rows]
    polygons = dict(zip(ids, polygons_from_geojson([r[2] for r in rows])))
    registered = {r[0]: float(r[1]) for r in rows}
    boxes = {pid: box_of(p[0]) for pid, p in polygons.items()}
    tree = MemoryQuadtree(list(boxes.items()))

    issues, pairs, compared = [], [], 0
    for n, pid in enumerate(ids, start=1):
        poly = polygons[pid]
        problem = ring_problem(poly[0])
        if problem:
            issues.append({"parcel_id": pid, "issue_type": "invalid", "severity": "error", "other": None,
                           "details": {"problem": problem}})
            continue
        area, perim = polygon_area(poly), perimeter(poly)
        for check, issue_type in ((check_area(area, registered[pid]), "area_mismatch"),
                                  (check_shape(area, perim), "sliver")):
            if check.status != PASS:
                details = {"check": check.detail, "area_m2": round(area, 2), "registered_m2": registered[pid],
                           "mean_width_m": round(2 * area / perim, 2)}
                issues.append({"parcel_id": pid, "issue_type": issue_type, "severity": "warning", "other": None,
                               "details": details})
        for other in tree.search(boxes[pid]):
            if other > pid:  # each pair once
                compared += 1
                if interiors_overlap(poly, polygons[other]):
                    pairs.append((pid, other))
        if progress and n % 20000 == 0:
            progress(n, len(ids))

    areas = {}
    if pairs:
        for a, b, area, geo in conn.execute(text("""
            SELECT a.id, b.id, ST_Area(ST_Transform(ST_Intersection(a.boundary, b.boundary), 32645)),
                   ST_AsGeoJSON(ST_Intersection(a.boundary, b.boundary), 7)
            FROM unnest(CAST(:a AS int[]), CAST(:b AS int[])) AS p(a, b)
            JOIN parcels a ON a.id = p.a JOIN parcels b ON b.id = p.b
        """), {"a": [p[0] for p in pairs], "b": [p[1] for p in pairs]}):
            areas[(a, b)] = (float(area), json.loads(geo))
    for a, b in pairs:
        area, geo = areas[(a, b)]
        if area >= MIN_OVERLAP_M2:  # smaller shared areas are rounding noise along shared edges
            issues.append({"parcel_id": a, "issue_type": "overlap", "severity": "error", "other": b,
                           "details": {"area_m2": round(area, 2), "geometry": geo}})
    overlaps = sum(1 for i in issues if i["issue_type"] == "overlap")
    stats = {"parcels": len(ids), "pairs_compared": compared, "overlap_pairs": overlaps}
    return issues, stats


def save_issues(conn: Connection, issues: list[dict]) -> int:
    """Replace open scan issues; issues an officer already reviewed are not raised again."""
    conn.execute(text("DELETE FROM parcel_issues WHERE review_status = 'open' AND details ->> 'source' = 'scan'"))
    reviewed = {(r[0], r[1], r[2]) for r in conn.execute(text(
        "SELECT parcel_id, issue_type, other_parcel_id FROM parcel_issues WHERE review_status <> 'open'"))}
    new = [i for i in issues if (i["parcel_id"], i["issue_type"], i["other"]) not in reviewed]
    if new:
        conn.execute(text("""
            INSERT INTO parcel_issues (parcel_id, other_parcel_id, issue_type, severity, details)
            VALUES (:parcel_id, :other, :issue_type, :severity, CAST(:details AS jsonb))
        """), [{**i, "details": json.dumps({**i["details"], "source": "scan"})} for i in new])
    return len(new)


def main() -> int:
    t0 = time.perf_counter()
    with engine.begin() as conn:
        issues, stats = find_issues(conn, lambda n, total: print(f"  checked {n:,} of {total:,} parcels", flush=True))
        saved = save_issues(conn, issues)
    by_type: dict[str, int] = {}
    for i in issues:
        by_type[i["issue_type"]] = by_type.get(i["issue_type"], 0) + 1
    print(f"scanned {stats['parcels']:,} parcels, compared {stats['pairs_compared']:,} neighbouring pairs "
          f"in {time.perf_counter() - t0:.0f} s")
    print(f"issues: {by_type or 'none'}; {saved} saved as open")
    return 0


if __name__ == "__main__":
    sys.exit(main())
