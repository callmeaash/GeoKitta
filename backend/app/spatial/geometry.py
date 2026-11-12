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
    """Shortest distance between a polygon and a polyline (or a single point); 0 if they touch or it runs inside."""
    if any(locate(p, polygon) != OUTSIDE for p in line):
        return 0.0
    if len(line) == 1:
        return boundary_distance(line[0], polygon)
    best = math.inf
    for ring in polygon:
        for p, q in edges(ring):
            for r, s in zip(line, line[1:]):
                best = min(best, segment_distance(p, q, r, s))
                if best == 0.0:
                    return 0.0
    return best


def ring_area(ring: Ring) -> float:
    """Shoelace formula: absolute area enclosed by a closed ring."""
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in edges(ring))) / 2


def polygon_area(polygon: Polygon) -> float:
    return ring_area(polygon[0]) - sum(ring_area(h) for h in polygon[1:])


def chunk_line(line: list[Point], max_length: float = 100.0) -> list[list[Point]]:
    """Split a polyline into runs of about max_length metres, so a long river is searched piece by piece."""
    if len(line) == 1:
        return [line]
    chunks, current, length = [], [line[0]], 0.0
    for a, b in zip(line, line[1:]):
        current.append(b)
        length += math.hypot(b[0] - a[0], b[1] - a[1])
        if length >= max_length:
            chunks.append(current)
            current, length = [b], 0.0
    if len(current) > 1:
        chunks.append(current)
    return chunks


def expand(box: Box, d: float) -> Box:
    return box[0] - d, box[1] - d, box[2] + d, box[3] + d


def within_distance(polygon: Polygon, line: list[Point], d: float) -> bool:
    """True if the polyline (or point) comes within d of the polygon; stops at the first close edge pair."""
    pbox = box_of(polygon[0])
    if len(line) == 1:
        p = line[0]
        return boxes_touch(expand((p[0], p[1], p[0], p[1]), d), pbox) and point_distance(p, polygon) <= d
    for a, b in zip(line, line[1:]):
        if not boxes_touch(expand(box_of((a, b)), d), pbox):
            continue  # this segment is too far from the parcel's box
        for ring in polygon:
            if any(segment_distance(p, q, a, b) <= d for p, q in edges(ring)):
                return True
    # no boundary edge is within d, so the line is either wholly inside the polygon or farther than d
    return locate(line[0], polygon) == INSIDE


# ---------- Validation checks (registration, boundary update, split, city-wide scan) ----------

TOUCH_EPS = 0.01  # metres; closer than this counts as touching a boundary, not crossing it


def ring_problem(ring: Ring) -> str | None:
    """Why a closed ring is not a valid polygon boundary (exact tests, like OGC validity), or None."""
    if len(ring) < 4 or ring[0] != ring[-1]:
        return "the ring needs at least 3 corners and must be closed"
    if any(a == b for a, b in edges(ring)):
        return "two consecutive corners are the same point"
    pts = ring[:-1]
    if len(set(pts)) < len(pts):
        return "a corner is repeated"
    segs = list(edges(ring))
    n = len(segs)
    for i in range(n):  # at each corner v the boundary must not turn straight back along itself
        before, v, after = segs[i - 1][0], segs[i][0], segs[i][1]
        same_way = (before[0] - v[0]) * (after[0] - v[0]) + (before[1] - v[1]) * (after[1] - v[1]) > 0
        if cross(v, before, after) == 0 and same_way:
            return f"the boundary folds back on itself at corner {i + 1}"
    for i in range(n):  # edges that are not neighbours must not touch at all
        for j in range(i + 2, n):
            if not (i == 0 and j == n - 1) and segments_intersect(*segs[i], *segs[j]):
                return f"edges {i + 1} and {j + 1} cross each other"
    if ring_area(ring) < 1e-6:
        return "the ring encloses no area"
    return None


def perimeter(polygon: Polygon) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for ring in polygon for a, b in edges(ring))


def strictly_inside(p: Point, polygon: Polygon, eps: float = TOUCH_EPS) -> bool:
    """Inside the polygon and farther than eps from its boundary."""
    if not point_in_ring(p, polygon[0]) or any(point_in_ring(p, h) for h in polygon[1:]):
        return False
    return boundary_distance(p, polygon) > eps


def _crosses_properly(p: Point, q: Point, r: Point, s: Point, eps: float) -> bool:
    """Segments cross at a point inside both, away from every end (not just touching at a corner)."""
    d1, d2, d3, d4 = cross(r, s, p), cross(r, s, q), cross(p, q, r), cross(p, q, s)
    if not ((d1 > 0 > d2 or d1 < 0 < d2) and (d3 > 0 > d4 or d3 < 0 < d4)):
        return False
    t = d1 / (d1 - d2)
    x, y = p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])
    return all(math.hypot(x - e[0], y - e[1]) > eps for e in (p, q, r, s)) and \
        min(point_segment_distance(e, *seg) for e, seg in ((p, (r, s)), (q, (r, s)), (r, (p, q)), (s, (p, q)))) > eps


def interiors_overlap(a: Polygon, b: Polygon, eps: float = TOUCH_EPS) -> bool:
    """True if two parcels share area; neighbours that only share a boundary line are not overlapping."""
    ba, bb = box_of(a[0]), box_of(b[0])
    common = (max(ba[0], bb[0]) - eps, max(ba[1], bb[1]) - eps, min(ba[2], bb[2]) + eps, min(ba[3], bb[3]) + eps)
    if common[2] - common[0] <= 3 * eps or common[3] - common[1] <= 3 * eps:
        return False  # boxes only touch
    near = [p for ring in a for p in ring[:-1] if boxes_touch((p[0], p[1], p[0], p[1]), common)]
    if any(strictly_inside(p, b, eps) for p in near):
        return True  # a corner of a lies inside b
    near_b = [p for ring in b for p in ring[:-1] if boxes_touch((p[0], p[1], p[0], p[1]), common)]
    if any(strictly_inside(p, a, eps) for p in near_b):
        return True
    ea = [e for ring in a for e in edges(ring) if boxes_touch(box_of(e), common)]
    eb = [e for ring in b for e in edges(ring) if boxes_touch(box_of(e), common)]
    if any(_crosses_properly(p, q, r, s, eps) for p, q in ea for r, s in eb):
        return True  # edges cross with no corner inside: the plus-sign case
    # boundaries may coincide while both shapes lie on the same side (e.g. a copy): test just inside each edge of a
    ring = a[0]
    turn = 1 if sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in edges(ring)) > 0 else -1  # +1 counter-clockwise
    for p, q in ea:
        length = math.hypot(q[0] - p[0], q[1] - p[1])
        if length < 10 * eps:
            continue
        nx, ny = -(q[1] - p[1]) / length * turn, (q[0] - p[0]) / length * turn  # unit normal into a
        mid = ((p[0] + q[0]) / 2 + nx * 5 * eps, (p[1] + q[1]) / 2 + ny * 5 * eps)
        if strictly_inside(mid, a, eps) and strictly_inside(mid, b, eps):
            return True
    return False


def within_polygon(inner: Polygon, outer: Polygon, eps: float = TOUCH_EPS) -> bool:
    """True if inner lies inside outer (touching its boundary is allowed), e.g. a child inside its parent."""
    pts = [p for ring in inner for p in ring[:-1]]
    pts += [((p[0] + q[0]) / 2, (p[1] + q[1]) / 2) for ring in inner for p, q in edges(ring)]  # for concave parents
    if any(locate(p, outer) == OUTSIDE and boundary_distance(p, outer) > eps for p in pts):
        return False
    return not any(_crosses_properly(p, q, r, s, eps) for ring in inner for p, q in edges(ring)
                   for oring in outer for r, s in edges(oring))
