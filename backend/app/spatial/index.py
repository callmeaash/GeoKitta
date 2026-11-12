"""Linear quadtree stored in parcel_quadkeys: write entries and fetch candidate parcels for a search box."""
from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from app.spatial import quadkey as qk
from app.spatial.geometry import Box, Polygon, box_of, boxes_touch
from app.spatial.projection import polygons_from_geojson

TABLE = "parcel_quadkeys"
COLUMNS = ("parcel_id", "quadkey", "min_x", "min_y", "max_x", "max_y")

# Ancestors of the covering quadrants (exact key) and the quadrants with their descendants (prefix range).
# Both are B-tree range conditions: an equality join on many keys lets PostgreSQL choose a hash join over the
# whole table, which would skip the index. i points back to the key, and from it to the boxes that asked for it.
_SEARCH_SQL = """
SELECT 0, r.i, q.parcel_id, q.min_x, q.min_y, q.max_x, q.max_y
FROM unnest(CAST(:exact AS text[])) WITH ORDINALITY AS r(key, i)
JOIN {table} q ON q.quadkey >= r.key AND q.quadkey <= r.key
UNION ALL
SELECT 1, r.i, q.parcel_id, q.min_x, q.min_y, q.max_x, q.max_y
FROM unnest(CAST(:lo AS text[]), CAST(:hi AS text[])) WITH ORDINALITY AS r(lo, hi, i)
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
        return self.candidates_many([box])

    def candidates_many(self, boxes: list[Box]) -> dict[int, Box]:
        """Parcels whose bounding box touches any of the search boxes, in one query."""
        exact: dict[str, list[int]] = {}  # key -> search boxes that need it; neighbouring boxes share keys
        ranges: dict[str, list[int]] = {}
        for i, box in enumerate(boxes):
            cover = qk.cover(box)
            for c in cover:
                ranges.setdefault(c, []).append(i)
            for a in {a for c in cover for a in qk.ancestors(c)}:
                exact.setdefault(a, []).append(i)
        asked = (list(exact.values()), list(ranges.values()))
        rows = self.db.execute(self.sql, {"exact": list(exact), "lo": list(ranges),
                                          "hi": [qk.key_range(c)[1] for c in ranges]})
        found, read = {}, 0
        for part, i, pid, *b in rows:
            read += 1
            if pid not in found and any(boxes_touch(tuple(b), boxes[j]) for j in asked[part][i - 1]):
                found[pid] = tuple(b)
        self.stats = {"cells": len(ranges), "rows_read": read, "candidates": len(found)}
        return found

    def polygons(self, ids) -> dict[int, Polygon]:
        return load_polygons(self.db, ids)
