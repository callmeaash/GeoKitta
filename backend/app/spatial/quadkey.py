"""Linear quadtree addresses: quadkeys for points and boxes, quadrant bounds and range covers."""

ROOT_X = 328_400.0  # south-west corner of the root square, UTM 45N metres
ROOT_Y = 3_059_600.0
ROOT_SIZE = 12_800.0  # covers KMC (about 9.5 x 9.1 km) with a margin; a power-of-two multiple keeps cells exact
MAX_DEPTH = 18  # smallest quadrant is about 5 cm
COVER_EXTRA_LEVELS = 3  # how much finer than the search box the cover may go along its edges
COVER_MAX_DEPTH = 11  # 6.25 m cells; parcels of 25 m² or more are never stored deeper, so finer cover is wasted

Box = tuple[float, float, float, float]  # min_x, min_y, max_x, max_y in UTM metres

# digit for (east, north) halves: 0 = NW, 1 = NE, 2 = SW, 3 = SE
_DIGIT = {(0, 1): "0", (1, 1): "1", (0, 0): "2", (1, 0): "3"}
_HALVES = {d: half for half, d in _DIGIT.items()}


class OutsideRootError(ValueError):
    """The point or box is outside the root square, so it cannot be indexed."""


def check_inside(box: Box) -> None:
    x0, y0, x1, y1 = box
    if x0 > x1 or y0 > y1:
        raise ValueError(f"box corners are in the wrong order: {box}")
    if x0 < ROOT_X or y0 < ROOT_Y or x1 > ROOT_X + ROOT_SIZE or y1 > ROOT_Y + ROOT_SIZE:
        raise OutsideRootError(f"box {box} is outside the quadtree root")


def cell_size(depth: int) -> float:
    return ROOT_SIZE / (1 << depth)


def cell_of(x: float, y: float, depth: int) -> tuple[int, int]:
    """Column and row (counted from the south-west) of the quadrant at this depth that contains the point."""
    n = 1 << depth
    size = ROOT_SIZE / n
    return min(int((x - ROOT_X) // size), n - 1), min(int((y - ROOT_Y) // size), n - 1)


def to_key(col: int, row: int, depth: int) -> str:
    """Quadkey of a quadrant: one digit per level, read from the root down."""
    return "".join(_DIGIT[((col >> i) & 1, (row >> i) & 1)] for i in range(depth - 1, -1, -1))


def from_key(key: str) -> tuple[int, int, int]:
    """Column, row and depth of a quadkey."""
    col = row = 0
    for d in key:
        east, north = _HALVES[d]
        col, row = col * 2 + east, row * 2 + north
    return col, row, len(key)


def cell_box(key: str) -> Box:
    col, row, depth = from_key(key)
    size = cell_size(depth)
    x0, y0 = ROOT_X + col * size, ROOT_Y + row * size
    return x0, y0, x0 + size, y0 + size


def point_key(x: float, y: float, depth: int = MAX_DEPTH) -> str:
    check_inside((x, y, x, y))
    return to_key(*cell_of(x, y, depth), depth)


def level_for(box: Box) -> int:
    """Deepest level whose quadrants are at least as wide as the box's longer side."""
    side = max(box[2] - box[0], box[3] - box[1])
    depth, size = 0, ROOT_SIZE
    while depth < MAX_DEPTH and size / 2 >= side:
        size /= 2
        depth += 1
    return depth


def keys_for_box(box: Box) -> list[str]:
    """Quadrants a parcel is stored under: those at its own size level that its box touches (1 to 4)."""
    check_inside(box)
    depth = level_for(box)
    c0, r0 = cell_of(box[0], box[1], depth)
    c1, r1 = cell_of(box[2], box[3], depth)
    return [to_key(c, r, depth) for r in range(r1, r0 - 1, -1) for c in range(c0, c1 + 1)]


def ancestors(key: str) -> list[str]:
    """Proper ancestors of a quadrant, from the root ("") down to its parent."""
    return [key[:i] for i in range(len(key))]


def key_range(key: str) -> tuple[str, str]:
    """B-tree range [lo, hi) holding the quadrant and all its descendants ('4' sorts after '3' in collation C)."""
    return key, key + "4"


def cover(box: Box) -> list[str]:
    """Disjoint quadrants covering the box: whole quadrants inside it, plus edge quadrants down to a limited depth."""
    x0, y0, x1, y1 = box
    x0, y0 = max(x0, ROOT_X), max(y0, ROOT_Y)
    x1, y1 = min(x1, ROOT_X + ROOT_SIZE), min(y1, ROOT_Y + ROOT_SIZE)
    if x0 > x1 or y0 > y1:
        return []  # the box misses the root entirely
    stop = min(COVER_MAX_DEPTH, level_for((x0, y0, x1, y1)) + COVER_EXTRA_LEVELS)
    out: list[str] = []

    def visit(col: int, row: int, depth: int) -> None:
        c0, r0 = cell_of(x0, y0, depth)
        c1, r1 = cell_of(x1, y1, depth)
        if not (c0 <= col <= c1 and r0 <= row <= r1):
            return  # quadrant does not touch the box
        size = cell_size(depth)
        qx0, qy0 = ROOT_X + col * size, ROOT_Y + row * size
        if depth == stop or (x0 <= qx0 and y0 <= qy0 and qx0 + size <= x1 and qy0 + size <= y1):
            out.append(to_key(col, row, depth))
            return
        for east, north in ((0, 1), (1, 1), (0, 0), (1, 0)):  # NW, NE, SW, SE
            visit(col * 2 + east, row * 2 + north, depth + 1)

    visit(0, 0, 0)
    return out
