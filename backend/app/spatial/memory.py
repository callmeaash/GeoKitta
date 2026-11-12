"""The same linear quadtree held in a sorted Python list, for small static data such as roads and rivers."""
from bisect import bisect_left, bisect_right

from app.spatial import quadkey as qk
from app.spatial.geometry import Box, boxes_touch


def _clip(box: Box) -> Box:
    """Keep a box inside the root square so it can be given quadkeys."""
    x1, y1 = qk.ROOT_X + qk.ROOT_SIZE, qk.ROOT_Y + qk.ROOT_SIZE
    return (min(max(box[0], qk.ROOT_X), x1), min(max(box[1], qk.ROOT_Y), y1),
            min(max(box[2], qk.ROOT_X), x1), min(max(box[3], qk.ROOT_Y), y1))


class MemoryQuadtree:
    """Entries sorted by quadkey; binary search (bisect) plays the role of the database B-tree."""

    def __init__(self, items: list[tuple[int, Box]]):
        rows = sorted((key, item) for item, box in items for key in qk.keys_for_box(_clip(box)))
        self._keys = [k for k, _ in rows]
        self._items = [i for _, i in rows]
        self._boxes = dict(items)

    def __len__(self) -> int:
        return len(self._boxes)

    def search(self, box: Box) -> list[int]:
        """Items whose box touches the search box."""
        cells = qk.cover(box)
        found: set[int] = set()
        for key in {a for c in cells for a in qk.ancestors(c)}:  # stored in a larger quadrant: exact key
            found.update(self._items[bisect_left(self._keys, key):bisect_right(self._keys, key)])
        for c in cells:  # stored in the quadrant or below it: key range [c, c + '4')
            lo, hi = qk.key_range(c)
            found.update(self._items[bisect_left(self._keys, lo):bisect_left(self._keys, hi)])
        return sorted(i for i in found if boxes_touch(self._boxes[i], box))
