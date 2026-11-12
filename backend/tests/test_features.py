import random

from app.spatial import quadkey as qk
from app.spatial.features import Feature, FeatureIndex, Rule, base_name
from app.spatial.geometry import boxes_touch
from app.spatial.memory import MemoryQuadtree

X, Y = qk.ROOT_X + 5000, qk.ROOT_Y + 5000


def test_memory_quadtree_matches_brute_force():
    rng = random.Random(11)
    items = []
    for i in range(800):
        x, y = X + rng.uniform(0, 2000), Y + rng.uniform(0, 2000)
        items.append((i, (x, y, x + rng.uniform(0, 150), y + rng.uniform(0, 40))))
    tree = MemoryQuadtree(items)
    for _ in range(200):
        x, y = X + rng.uniform(-100, 2100), Y + rng.uniform(-100, 2100)
        box = (x, y, x + rng.uniform(0, 300), y + rng.uniform(0, 300))
        assert tree.search(box) == sorted(i for i, b in items if boxes_touch(b, box))


def test_base_name_matches_osm_variants():
    assert base_name("Bagmati River") == base_name("Bagmati") == "bagmati"
    assert base_name("Tukucha Khola") == "tukucha"
    assert base_name("River") == "river"
    assert base_name(None) is None


def _river_index():
    river = [(X, Y + y) for y in range(0, 1001, 50)]  # a 1 km north-south river, 20 m wide
    return FeatureIndex([Feature(1, "Test River", "river", 20.0, river[:11]),
                         Feature(2, "Test", "river", 20.0, river[10:]),
                         Feature(3, None, "road", 8.0, [(X - 500, Y), (X - 500, Y + 1000)])])


def test_group_joins_ways_of_one_river_only():
    fi = _river_index()
    assert {f.id for f in fi.group(fi.features[1])} == {1, 2}
    assert [f.id for f in fi.group(fi.features[3])] == [3]


def test_setback_measured_from_the_bank():
    fi = _river_index()
    rule = Rule(9, "river", 15.0, "bank", "municipal", None)
    near_bank = [[(X + 20, Y + 400), (X + 30, Y + 400), (X + 30, Y + 410), (X + 20, Y + 410), (X + 20, Y + 400)]]
    far = [[(X + 40, Y + 400), (X + 50, Y + 400), (X + 50, Y + 410), (X + 40, Y + 410), (X + 40, Y + 400)]]
    hits = fi.setbacks(near_bank, [rule])
    assert len(hits) == 1 and hits[0]["distance_m"] == 10.0  # 20 m from the centre line, 10 m from the bank
    assert fi.setbacks(far, [rule]) == []  # 30 m from the bank


def test_nearest_feature_respects_types_and_distance():
    fi = _river_index()
    assert fi.nearest((X + 5, Y + 300), {"river"}, 50)[0].id == 1
    assert fi.nearest((X - 480, Y + 300), {"river"}, 50) is None
    assert fi.nearest((X - 480, Y + 300), {"road"}, 50)[0].id == 3
