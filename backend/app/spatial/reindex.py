"""Rebuild the linear quadtree for every active parcel: python -m app.spatial.reindex (from backend/)."""
import sys
import time
from collections import Counter

from sqlalchemy import Connection, text

from app.db import engine
from app.spatial.index import COLUMNS, TABLE, entries
from app.spatial.projection import polygons_from_geojson


def rebuild(conn: Connection) -> dict:
    """Replace all quadtree entries; runs in the caller's transaction."""
    rows = conn.execute(text("SELECT id, ST_AsGeoJSON(boundary) FROM parcels WHERE status = 'active' ORDER BY id"))
    rows = rows.all()
    polygons = polygons_from_geojson([r[1] for r in rows])
    conn.execute(text(f"TRUNCATE {TABLE}"))
    depths: Counter = Counter()
    count = 0
    with conn.connection.driver_connection.cursor() as cur:
        with cur.copy(f"COPY {TABLE} ({', '.join(COLUMNS)}) FROM STDIN") as copy:
            for (pid, _), polygon in zip(rows, polygons):
                for entry in entries(pid, polygon):
                    copy.write_row(entry)
                    depths[len(entry[1])] += 1
                    count += 1
    return {"parcels": len(rows), "entries": count, "entries_by_depth": dict(sorted(depths.items()))}


def main() -> int:
    t0 = time.perf_counter()
    with engine.begin() as conn:
        result = rebuild(conn)
    with engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT").exec_driver_sql(f"ANALYZE {TABLE}")
    print(f"indexed {result['parcels']} parcels as {result['entries']} quadtree entries "
          f"({result['entries'] / max(result['parcels'], 1):.2f} per parcel) in {time.perf_counter() - t0:.1f} s")
    print("entries by quadkey length:", result["entries_by_depth"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
