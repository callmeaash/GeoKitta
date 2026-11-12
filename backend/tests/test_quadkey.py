import random

import pytest

from app.spatial import quadkey as qk
from app.spatial.quadkey import ROOT_SIZE, ROOT_X, ROOT_Y

HALF = ROOT_SIZE / 2


def test_first_level_digits_follow_nw_ne_sw_se():
    assert qk.point_key(ROOT_X + 1, ROOT_Y + ROOT_SIZE - 1, 1) == "0"  # north-west
    assert qk.point_key(ROOT_X + ROOT_SIZE - 1, ROOT_Y + ROOT_SIZE - 1, 1) == "1"  # north-east
    assert qk.point_key(ROOT_X + 1, ROOT_Y + 1, 1) == "2"  # south-west
    assert qk.point_key(ROOT_X + ROOT_SIZE - 1, ROOT_Y + 1, 1) == "3"  # south-east


def test_child_key_starts_with_parent_key():
    x, y = ROOT_X + 4321.5, ROOT_Y + 8765.25
    keys = [qk.point_key(x, y, d) for d in range(qk.MAX_DEPTH + 1)]
    assert keys[0] == ""
    assert all(keys[d + 1].startswith(keys[d]) for d in range(qk.MAX_DEPTH))
    assert qk.ancestors(keys[5]) == keys[:5]


def test_points_on_dividing_lines_go_east_and_north():
    assert qk.point_key(ROOT_X + HALF, ROOT_Y + HALF, 1) == "1"
    assert qk.point_key(ROOT_X + ROOT_SIZE, ROOT_Y + ROOT_SIZE, 3) == "111"  # far corner stays in the root
    assert qk.point_key(ROOT_X, ROOT_Y, 3) == "222"


def test_key_round_trip_and_cell_box():
    for key in ["", "0", "3", "1203", "3210012301"]:
        col, row, depth = qk.from_key(key)
        assert qk.to_key(col, row, depth) == key
        x0, y0, x1, y1 = qk.cell_box(key)
        assert x1 - x0 == pytest.approx(ROOT_SIZE / 2 ** len(key))
        assert qk.point_key((x0 + x1) / 2, (y0 + y1) / 2, len(key)) == key


def test_outside_root_is_rejected():
    with pytest.raises(qk.OutsideRootError):
        qk.point_key(ROOT_X - 1, ROOT_Y + 1)
    with pytest.raises(qk.OutsideRootError):
        qk.keys_for_box((ROOT_X + 10, ROOT_Y + 10, ROOT_X + ROOT_SIZE + 5, ROOT_Y + 20))


def test_level_for_matches_box_size():
    assert qk.level_for((0, 0, 0, 0)) == qk.MAX_DEPTH
    assert qk.level_for((0, 0, ROOT_SIZE, 1)) == 0
    assert qk.level_for((0, 0, 20, 10)) == 9  # 25 m cells are the smallest that fit 20 m
    assert qk.level_for((0, 0, 25, 25)) == 9


def test_parcel_inside_one_cell_gets_one_key():
    x0, y0 = ROOT_X + 25 * 100 + 2, ROOT_Y + 25 * 40 + 2  # inside one 25 m cell
    keys = qk.keys_for_box((x0, y0, x0 + 20, y0 + 15))
    assert len(keys) == 1 and len(keys[0]) == 9


def test_parcel_on_the_root_centre_gets_four_small_keys_not_the_root():
    box = (ROOT_X + HALF - 8, ROOT_Y + HALF - 6, ROOT_X + HALF + 8, ROOT_Y + HALF + 6)
    keys = qk.keys_for_box(box)
    assert len(keys) == 4
    assert {k[0] for k in keys} == {"0", "1", "2", "3"}
    assert all(len(k) == qk.level_for(box) for k in keys)


def test_stored_keys_cover_the_box():
    rng = random.Random(7)
    for _ in range(500):
        x, y = ROOT_X + rng.uniform(0, ROOT_SIZE - 300), ROOT_Y + rng.uniform(0, ROOT_SIZE - 300)
        box = (x, y, x + rng.uniform(0, 250), y + rng.uniform(0, 250))
        keys = qk.keys_for_box(box)
        assert 1 <= len(keys) <= 4
        for _ in range(5):  # every point of the box is in one of the stored quadrants
            px, py = rng.uniform(box[0], box[2]), rng.uniform(box[1], box[3])
            assert qk.point_key(px, py, len(keys[0])) in keys


def test_key_range_holds_exactly_the_descendants():
    lo, hi = qk.key_range("12")
    inside = ["12", "120", "1233", "123333333"]
    outside = ["1", "11", "13", "2", "", "1133"]
    assert all(lo <= k < hi for k in inside)  # Python compares code points, like collation "C"
    assert not any(lo <= k < hi for k in outside)


def _covered(cells, x, y):
    return any(qk.point_key(x, y, len(c)) == c for c in cells)


@pytest.mark.parametrize("size", [3.0, 40.0, 300.0, 1500.0])
def test_cover_is_complete_disjoint_and_touches_the_box(size):
    rng = random.Random(int(size))
    for _ in range(30):
        x, y = ROOT_X + rng.uniform(0, ROOT_SIZE - size), ROOT_Y + rng.uniform(0, ROOT_SIZE - size)
        box = (x, y, x + size, y + size * rng.uniform(0.3, 1))
        cells = qk.cover(box)
        assert cells
        for a in cells:  # disjoint: no covering quadrant contains another
            assert not any(b != a and b.startswith(a) for b in cells)
            cx0, cy0, cx1, cy1 = qk.cell_box(a)  # no quadrant outside the box
            assert cx0 <= box[2] and box[0] <= cx1 and cy0 <= box[3] and box[1] <= cy1
        for _ in range(40):
            assert _covered(cells, rng.uniform(box[0], box[2]), rng.uniform(box[1], box[3]))
        assert _covered(cells, box[0], box[1]) and _covered(cells, box[2], box[3])


def test_cover_uses_whole_quadrants_inside_large_boxes():
    cells = qk.cover((ROOT_X + 100, ROOT_Y + 100, ROOT_X + 3300, ROOT_Y + 3300))
    assert min(len(c) for c in cells) < max(len(c) for c in cells)  # big inner quadrants, small edge ones
    assert max(len(c) for c in cells) <= qk.COVER_MAX_DEPTH


def test_cover_of_box_partly_outside_is_clipped_and_outside_is_empty():
    assert qk.cover((ROOT_X - 50, ROOT_Y - 50, ROOT_X + 10, ROOT_Y + 10))
    assert qk.cover((ROOT_X - 50, ROOT_Y - 50, ROOT_X - 10, ROOT_Y - 10)) == []
