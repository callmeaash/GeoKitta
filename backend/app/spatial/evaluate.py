"""Linear quadtree vs brute-force loop at several data sizes: python -m app.spatial.evaluate (from backend/)."""
import json
import random
import statistics
import sys
import time

from sqlalchemy import text

from app.config import ROOT
from app.db import engine
from app.spatial import quadkey as qk
from app.spatial.bruteforce import BruteForceIndex
from app.spatial.geometry import box_of
from app.spatial.index import QuadtreeIndex
from app.spatial.queries import identify, in_box

SIZES = (200, 10_000, 50_000, None)  # None = every active parcel
POINT_QUERIES = 300
BOX_QUERIES = 100
BOX_HALF_M = 150  # 300 m selection boxes
OUT = ROOT / "data" / "evaluation" / "quadtree.json"


def nearest_to_centre(everything: BruteForceIndex, n: int | None) -> list[int]:
    """The n parcels nearest the root centre, so each test set is one compact part of the city."""
    cx, cy = qk.ROOT_X + qk.ROOT_SIZE / 2, qk.ROOT_Y + qk.ROOT_SIZE / 2
    ids = sorted(everything._polygons, key=lambda pid: _centre_distance(everything._polygons[pid][0], cx, cy))
    return ids if n is None else ids[:n]


def _centre_distance(ring, cx, cy) -> float:
    b = box_of(ring)
    return ((b[0] + b[2]) / 2 - cx) ** 2 + ((b[1] + b[3]) / 2 - cy) ** 2


def run_queries(index, points, boxes) -> dict:
    """Run every query; time the candidate search and the whole query separately."""
    out = {"point": [], "box": []}
    for kind, queries in (("point", points), ("box", boxes)):
        for q in queries:
            t0 = time.perf_counter()
            index.candidates(q if kind == "box" else (q[0] - 1.5, q[1] - 1.5, q[0] + 1.5, q[1] + 1.5))
            search_ms = (time.perf_counter() - t0) * 1000
            read = index.stats["rows_read"]
            t0 = time.perf_counter()
            result = identify(index, q) if kind == "point" else in_box(index, q)
            out[kind].append({"search_ms": search_ms, "total_ms": (time.perf_counter() - t0) * 1000,
                              "read": read, "candidates": index.stats["candidates"], "result": result})
    return out


def summary(runs: list[dict]) -> dict:
    return {"rows_or_boxes_checked": round(statistics.mean(r["read"] for r in runs), 1),
            "candidates": round(statistics.mean(r["candidates"] for r in runs), 1),
            "search_ms_median": round(statistics.median(r["search_ms"] for r in runs), 3),
            "total_ms_median": round(statistics.median(r["total_ms"] for r in runs), 3)}


def main() -> int:
    rng = random.Random(2026)
    report = []
    with engine.connect() as conn:
        everything = BruteForceIndex.load(conn)
        for n in SIZES:
            ids = nearest_to_centre(everything, n)
            brute = BruteForceIndex({pid: everything._polygons[pid] for pid in ids})
            conn.execute(text("DROP TABLE IF EXISTS eval_quadkeys"))
            conn.execute(text("CREATE TEMP TABLE eval_quadkeys (LIKE parcel_quadkeys INCLUDING ALL)"))
            conn.execute(text("INSERT INTO eval_quadkeys SELECT * FROM parcel_quadkeys WHERE parcel_id = ANY(:ids)"),
                         {"ids": ids})
            conn.execute(text("ANALYZE eval_quadkeys"))
            quad = QuadtreeIndex(conn, "eval_quadkeys")

            sample = [rng.choice(ids) for _ in range(POINT_QUERIES)]
            points = []
            for pid in sample:  # half inside a parcel, half anywhere near one
                b = box_of(everything._polygons[pid][0])
                cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
                points.append((cx + rng.uniform(-20, 20), cy + rng.uniform(-20, 20)))
            boxes = [(x - BOX_HALF_M, y - BOX_HALF_M, x + BOX_HALF_M, y + BOX_HALF_M) for x, y in points[:BOX_QUERIES]]

            q_runs, b_runs = run_queries(quad, points, boxes), run_queries(brute, points, boxes)
            same = all(a["result"] == b["result"] for k in ("point", "box") for a, b in zip(q_runs[k], b_runs[k]))
            row = {"parcels": len(ids), "results_identical": same}
            for kind in ("point", "box"):
                row[kind] = {"linear_quadtree": summary(q_runs[kind]), "brute_force": summary(b_runs[kind])}
            report.append(row)
            q, b = row["point"]["linear_quadtree"], row["point"]["brute_force"]
            qb, bb = row["box"]["linear_quadtree"], row["box"]["brute_force"]
            print(f"{len(ids):>7} parcels | click: quadtree reads {q['rows_or_boxes_checked']:>6} rows "
                  f"{q['search_ms_median']:>7.2f} ms, brute force checks {b['rows_or_boxes_checked']:>8} "
                  f"{b['search_ms_median']:>8.2f} ms | 300 m box: {qb['rows_or_boxes_checked']:>7} rows "
                  f"{qb['search_ms_median']:>7.2f} ms vs {bb['search_ms_median']:>8.2f} ms | identical: {same}",
                  flush=True)
        conn.rollback()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), "utf-8")
    print(f"wrote {OUT}")
    return 0 if all(r["results_identical"] for r in report) else 1


if __name__ == "__main__":
    sys.exit(main())
