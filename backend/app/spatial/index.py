"""Linear quadtree stored in parcel_quadkeys: write entries and fetch candidate parcels for a search box."""
from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from app.spatial import quadkey as qk
from app.spatial.geometry import Box, Polygon, box_of, boxes_touch
from app.spatial.projection import polygons_from_geojson

TABLE = "parcel_quadkeys"
COLUMNS = ("parcel_id", "quadkey", "min_x", "min_y", "max_x", "max_y")

# ancestors of the covering quadrants by equality, the quadrants themselves (and descendants) by prefix range
_SEARCH_SQL = """
SELECT parcel_id, min_x, min_y, max_x, max_y FROM {table} WHERE quadkey = ANY(CAST(:exact AS text[]))
UNION ALL
SELECT q.parcel_id, q.min_x, q.min_y, q.max_x, q.max_y
FROM unnest(CAST(:lo AS text[]), CAST(:hi AS text[])) AS r(lo, hi)
JOIN {table} q ON q.quadkey >= r.lo AND q.quadkey < r.hi
"""


def entries(parcel_id: int, polygon: Polygon) -> list[tuple]:
    """Index rows for one parcel: its box under each quadrant it is stored in."""
    box = box_of(polygon[0])
    return [(parcel_id, key, *box) for key in qk.keys_for_box(box)]


def index_parcel(db: Session | Connection, parcel_id: int, polygon: Polygon) -> None:
    """Insert or replace a parcel's entries; call inside the transaction that saves the parcel."""
    unindex_parcel(db, parcel_id)
    db.execute(text(f"INSERT INTO {TABLE} ({', '.join(COLUMNS)}) "
                    "VALUES (:parcel_id, :quadkey, :min_x, :min_y, :max_x, :max_y)"),
               [dict(zip(COLUMNS, row)) for row in entries(parcel_id, polygon)])


def unindex_parcel(db: Session | Connection, parcel_id: int) -> None:
    db.execute(text(f"DELETE FROM {TABLE} WHERE parcel_id = :id"), {"id": parcel_id})


def load_polygons(db: Session | Connection, ids) -> dict[int, Polygon]:
    """Parcel boundaries in UTM metres, by id."""
    ids = list(ids)
    if not ids:
        return {}
    rows = db.execute(text("SELECT id, ST_AsGeoJSON(boundary) FROM parcels WHERE id = ANY(:ids)"),
                      {"ids": ids}).all()
    return dict(zip((r[0] for r in rows), polygons_from_geojson([r[1] for r in rows])))


class QuadtreeIndex:
    """Candidate search through the linear quadtree; `stats` describes the last search."""

    name = "linear quadtree"

    def __init__(self, db: Session | Connection, table: str = TABLE):
        if not table.replace("_", "").isalnum():
            raise ValueError(f"bad table name {table!r}")
        self.db, self.sql = db, text(_SEARCH_SQL.format(table=table))
        self.stats: dict = {}

    def candidates(self, box: Box) -> dict[int, Box]:
        """Parcels whose bounding box touches the search box."""
        cells = qk.cover(box)
        exact = sorted({a for c in cells for a in qk.ancestors(c)})
        rows = self.db.execute(self.sql, {"exact": exact, "lo": cells, "hi": [qk.key_range(c)[1] for c in cells]})
        found, read = {}, 0
        for pid, *b in rows:
            read += 1
            if pid not in found and boxes_touch(tuple(b), box):
                found[pid] = tuple(b)
        self.stats = {"cells": len(cells), "rows_read": read, "candidates": len(found)}
        return found

    def polygons(self, ids) -> dict[int, Polygon]:
        return load_polygons(self.db, ids)
