"""Exact geometry checks on quadtree candidates: ray casting, segment intersection and distances (UTM metres)."""
import math

Point = tuple[float, float]
Ring = list[Point]  # closed: the first point is repeated at the end
Polygon = list[Ring]  # outer ring first, then holes
Box = tuple[float, float, float, float]

EPS = 1e-9  # metres; points this close to an edge count as on it

INSIDE, BOUNDARY, OUTSIDE = "inside", "boundary", "outside"


def box_of(points) -> Box:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def boxes_touch(a: Box, b: Box) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def box_ring(box: Box) -> Ring:
    x0, y0, x1, y1 = box
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


def edges(ring: Ring):
    return zip(ring, ring[1:])


def cross(o: Point, a: Point, b: Point) -> float:
    """Twice the signed area of triangle o-a-b: > 0 if b is left of o->a, < 0 if right, 0 if in line."""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _within_segment_box(p: Point, a: Point, b: Point) -> bool:
    return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])


def segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    """True if segments a-b and c-d share any point (crossing, touching or overlapping in line)."""
    d1, d2 = cross(c, d, a), cross(c, d, b)
    d3, d4 = cross(a, b, c), cross(a, b, d)
    if ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4)):
        return True  # proper crossing: each segment's ends lie on opposite sides of the other
    return ((d1 == 0 and _within_segment_box(a, c, d)) or (d2 == 0 and _within_segment_box(b, c, d))
            or (d3 == 0 and _within_segment_box(c, a, b)) or (d4 == 0 and _within_segment_box(d, a, b)))


def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    """Distance from p to the nearest point of segment a-b (projection clamped to the segment)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def segment_distance(a: Point, b: Point, c: Point, d: Point) -> float:
    if segments_intersect(a, b, c, d):
        return 0.0
    return min(point_segment_distance(a, c, d), point_segment_distance(b, c, d),
               point_segment_distance(c, a, b), point_segment_distance(d, a, b))


def point_in_ring(p: Point, ring: Ring) -> bool:
    """Ray casting: count edges crossed by a ray from p towards +x; an odd count means inside."""
    x, y = p
    inside = False
    for (x1, y1), (x2, y2) in edges(ring):
        if (y1 > y) != (y2 > y):  # edge spans the ray's height; half-open so a shared vertex counts once
            x_cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_cross:
                inside = not inside
    return inside


def boundary_distance(p: Point, polygon: Polygon) -> float:
    return min(point_segment_distance(p, a, b) for ring in polygon for a, b in edges(ring))


def locate(p: Point, polygon: Polygon) -> str:
    """Whether p is inside, on the boundary of, or outside a polygon with holes."""
    if boundary_distance(p, polygon) <= EPS:
        return BOUNDARY
    if not point_in_ring(p, polygon[0]):
        return OUTSIDE
    return OUTSIDE if any(point_in_ring(p, hole) for hole in polygon[1:]) else INSIDE


def point_distance(p: Point, polygon: Polygon) -> float:
    """0 inside the polygon, else the distance to its nearest edge."""
    return 0.0 if locate(p, polygon) != OUTSIDE else boundary_distance(p, polygon)


def polygons_intersect(a: Polygon, b: Polygon) -> bool:
    """True if two polygons share any point; edge crossings catch the plus-sign case where no corner is inside."""
    if not boxes_touch(box_of(a[0]), box_of(b[0])):
        return False
    for ring_a in a:
        for p, q in edges(ring_a):
            for ring_b in b:
                if any(segments_intersect(p, q, r, s) for r, s in edges(ring_b)):
                    return True
    # no edges meet, so one is entirely inside the other or they are apart
    return locate(a[0][0], b) != OUTSIDE or locate(b[0][0], a) != OUTSIDE


def polygon_intersects_box(polygon: Polygon, box: Box) -> bool:
    return polygons_intersect(polygon, [box_ring(box)])


def line_distance(polygon: Polygon, line: list[Point]) -> float:
    """Shortest distance between a polygon and a polyline; 0 if they touch or the line runs inside."""
    if any(locate(p, polygon) != OUTSIDE for p in line):
        return 0.0
    best = math.inf
    for ring in polygon:
        for p, q in edges(ring):
            for r, s in zip(line, line[1:]):
                best = min(best, segment_distance(p, q, r, s))
                if best == 0.0:
                    return 0.0
    return best
