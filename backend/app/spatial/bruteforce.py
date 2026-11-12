"""Brute-force comparator: checks every parcel's box in a loop. Used only by tests and the evaluation."""
from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from app.spatial.geometry import Box, Polygon, box_of, boxes_touch
from app.spatial.projection import polygons_from_geojson


class BruteForceIndex:
    """Same interface as QuadtreeIndex, with every parcel held in memory."""

    name = "brute force"

    def __init__(self, polygons: dict[int, Polygon]):
        self._polygons = polygons
        self._boxes = [(pid, box_of(p[0])) for pid, p in polygons.items()]
        self.stats: dict = {}

    @classmethod
    def load(cls, db: Session | Connection, ids=None) -> "BruteForceIndex":
        """All active parcels, or only the given ids."""
        if ids is None:
            rows = db.execute(text("SELECT id, ST_AsGeoJSON(boundary) FROM parcels WHERE status = 'active'")).all()
        else:
            rows = db.execute(text("SELECT id, ST_AsGeoJSON(boundary) FROM parcels WHERE id = ANY(:ids)"),
                              {"ids": list(ids)}).all()
        return cls(dict(zip((r[0] for r in rows), polygons_from_geojson([r[1] for r in rows]))))

    def __len__(self) -> int:
        return len(self._boxes)

    def candidates(self, box: Box) -> dict[int, Box]:
        found = {pid: b for pid, b in self._boxes if boxes_touch(b, box)}
        self.stats = {"cells": 0, "rows_read": len(self._boxes), "candidates": len(found)}
        return found

    def polygons(self, ids) -> dict[int, Polygon]:
        return {pid: self._polygons[pid] for pid in ids}
