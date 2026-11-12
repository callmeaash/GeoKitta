"""Spatial lookups: identify a parcel at a point, select by rectangle, find parcels near points and lines (UTM)."""
import math
from typing import Protocol

from app.spatial.geometry import (BOUNDARY, INSIDE, Box, Point, Polygon, box_of, boundary_distance, boxes_touch,
                                  chunk_line, expand, locate, polygon_intersects_box, within_distance)


class Index(Protocol):
    stats: dict

    def candidates(self, box: Box) -> dict[int, Box]: ...

    def candidates_many(self, boxes: list[Box]) -> dict[int, Box]: ...

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


def near(index: Index, lines: list[tuple[list[Point], float]], chunk_m: float = 100.0) -> list[int]:
    """Parcels within each line's distance; a point is a one-point line. Long lines are searched piece by piece."""
    pieces = []
    for line, distance in lines:
        for part in chunk_line(line, chunk_m):
            pieces.append((part, distance, expand(box_of(part), distance)))
    if not pieces:
        return []
    boxes = index.candidates_many([p[2] for p in pieces])
    found = []
    for pid, poly in index.polygons(boxes).items():
        pbox = boxes[pid]
        if any(boxes_touch(box, pbox) and within_distance(poly, part, d) for part, d, box in pieces):
            found.append(pid)
    index.stats["checked"] = len(boxes)
    return sorted(found)


def near_line(index: Index, line: list[Point], distance: float) -> list[int]:
    """Parcels within `distance` metres of a polyline (road or river centre line, setback search)."""
    return near(index, [(line, distance)])
