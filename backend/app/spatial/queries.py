"""Spatial lookups: identify a parcel at a point, select by rectangle, find parcels near a line (UTM metres)."""
import math
from typing import Protocol

from app.spatial.geometry import (BOUNDARY, INSIDE, Box, Point, Polygon, boundary_distance, line_distance, locate,
                                  polygon_intersects_box)


class Index(Protocol):
    stats: dict

    def candidates(self, box: Box) -> dict[int, Box]: ...

    def polygons(self, ids) -> dict[int, Polygon]: ...


def identify(index: Index, p: Point, tolerance: float = 1.5) -> int | None:
    """Parcel containing p; on a shared edge the one whose box centre is nearest; else the nearest edge in tolerance."""
    box = (p[0] - tolerance, p[1] - tolerance, p[0] + tolerance, p[1] + tolerance)
    boxes = index.candidates(box)
    ranked = []
    for pid, poly in index.polygons(boxes).items():
        where = locate(p, poly)
        if where == INSIDE:
            rank, dist = 0, 0.0
        elif where == BOUNDARY:
            rank, dist = 1, 0.0
        else:
            rank, dist = 2, boundary_distance(p, poly)
            if dist > tolerance:
                continue
        b = boxes[pid]
        centre = math.hypot(p[0] - (b[0] + b[2]) / 2, p[1] - (b[1] + b[3]) / 2)
        ranked.append((rank, dist, centre, pid))
    index.stats["checked"] = len(boxes)
    return min(ranked)[3] if ranked else None


def in_box(index: Index, box: Box) -> list[int]:
    """Parcels that touch a rectangle."""
    boxes = index.candidates(box)
    found = sorted(pid for pid, poly in index.polygons(boxes).items() if polygon_intersects_box(poly, box))
    index.stats["checked"] = len(boxes)
    return found


def near_line(index: Index, line: list[Point], distance: float) -> list[int]:
    """Parcels within `distance` metres of a polyline (road or river centre line, setback search)."""
    boxes, totals = {}, {"cells": 0, "rows_read": 0}
    for a, b in zip(line, line[1:]):  # one box per segment, so a long diagonal road does not pull in a whole block
        seg_box = (min(a[0], b[0]) - distance, min(a[1], b[1]) - distance,
                   max(a[0], b[0]) + distance, max(a[1], b[1]) + distance)
        boxes.update(index.candidates(seg_box))
        totals = {k: totals[k] + index.stats[k] for k in totals}
    found = sorted(pid for pid, poly in index.polygons(boxes).items() if line_distance(poly, line) <= distance)
    index.stats = {**totals, "candidates": len(boxes), "checked": len(boxes)}
    return found
