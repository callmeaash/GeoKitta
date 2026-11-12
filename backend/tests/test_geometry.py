import pytest

from app.spatial.geometry import (BOUNDARY, INSIDE, OUTSIDE, box_ring, line_distance, locate, point_distance,
                                  point_in_ring, point_segment_distance, polygon_intersects_box, polygons_intersect,
                                  segment_distance, segments_intersect)

SQUARE = [box_ring((0, 0, 10, 10))]
# U shape: the notch (4..6, 4..10) is outside
U_SHAPE = [[(0, 0), (10, 0), (10, 10), (6, 10), (6, 4), (4, 4), (4, 10), (0, 10), (0, 0)]]
WITH_HOLE = [box_ring((0, 0, 10, 10)), box_ring((3, 3, 7, 7))]


@pytest.mark.parametrize("point, expected", [
    ((5, 5), INSIDE), ((15, 5), OUTSIDE), ((10, 5), BOUNDARY), ((0, 0), BOUNDARY), ((-1, -1), OUTSIDE),
])
def test_locate_in_square(point, expected):
    assert locate(point, SQUARE) == expected


def test_concave_polygon():
    assert locate((5, 8), U_SHAPE) == OUTSIDE  # in the notch
    assert locate((2, 8), U_SHAPE) == INSIDE
    assert locate((5, 2), U_SHAPE) == INSIDE
    assert locate((5, 4), U_SHAPE) == BOUNDARY


def test_ray_through_a_vertex_is_counted_once():
    diamond = [[(5, 0), (10, 5), (5, 10), (0, 5), (5, 0)]]
    assert point_in_ring((2, 5), diamond[0])  # ray passes exactly through vertex (10, 5)
    assert not point_in_ring((-2, 5), diamond[0])  # left of the shape: the ray crosses at two vertices
    assert locate((-2, 5), diamond) == OUTSIDE
    assert locate((5, 5), diamond) == INSIDE


def test_hole_is_outside():
    assert locate((5, 5), WITH_HOLE) == OUTSIDE
    assert locate((1, 1), WITH_HOLE) == INSIDE
    assert locate((3, 5), WITH_HOLE) == BOUNDARY


@pytest.mark.parametrize("a, b, c, d, expected", [
    ((0, 0), (10, 10), (0, 10), (10, 0), True),     # crossing
    ((0, 0), (10, 0), (5, 0), (5, 5), True),        # T: end touches the middle
    ((0, 0), (10, 0), (10, 0), (12, 3), True),      # shared end point
    ((0, 0), (10, 0), (5, 0), (15, 0), True),       # overlapping in line
    ((0, 0), (10, 0), (11, 0), (15, 0), False),     # in line, apart
    ((0, 0), (10, 0), (0, 1), (10, 1), False),      # parallel
    ((0, 0), (10, 10), (6, 5), (20, 5), False),     # would cross only if extended
])
def test_segments_intersect(a, b, c, d, expected):
    assert segments_intersect(a, b, c, d) is expected
    assert segments_intersect(c, d, a, b) is expected


def test_point_segment_distance_clamps_to_the_ends():
    assert point_segment_distance((5, 3), (0, 0), (10, 0)) == pytest.approx(3)
    assert point_segment_distance((13, 4), (0, 0), (10, 0)) == pytest.approx(5)
    assert point_segment_distance((2, 2), (1, 1), (1, 1)) == pytest.approx(2 ** 0.5)
    assert segment_distance((0, 0), (10, 0), (0, 2), (10, 2)) == pytest.approx(2)


def test_point_distance():
    assert point_distance((5, 5), SQUARE) == 0
    assert point_distance((13, 14), SQUARE) == pytest.approx(5)


def test_plus_sign_overlap_has_no_corner_inside_the_other():
    horizontal = [box_ring((0, 4, 10, 6))]
    vertical = [box_ring((4, 0, 6, 10))]
    assert not any(locate(p, vertical) == INSIDE for p in horizontal[0])
    assert polygons_intersect(horizontal, vertical)


def test_polygons_intersect_cases():
    assert polygons_intersect(SQUARE, [box_ring((2, 2, 4, 4))])  # one inside the other
    assert polygons_intersect([box_ring((2, 2, 4, 4))], SQUARE)
    assert polygons_intersect(SQUARE, [box_ring((10, 0, 20, 10))])  # shared edge
    assert not polygons_intersect(SQUARE, [box_ring((11, 0, 20, 10))])
    assert not polygons_intersect(WITH_HOLE, [box_ring((4, 4, 6, 6))])  # inside the hole
    assert not polygons_intersect(U_SHAPE, [box_ring((4.5, 6, 5.5, 9))])  # inside the notch's box only


def test_polygon_intersects_box():
    assert polygon_intersects_box(U_SHAPE, (5, 9, 20, 20))
    assert not polygon_intersects_box(U_SHAPE, (4.5, 5, 5.5, 20))


def test_line_distance():
    road = [(-5, 15), (5, 15), (15, 15)]
    assert line_distance(SQUARE, road) == pytest.approx(5)
    assert line_distance(SQUARE, [(-5, 5), (15, 5)]) == 0  # runs across without a vertex inside
    assert line_distance(SQUARE, [(2, 2), (3, 3)]) == 0  # entirely inside


def test_within_distance_agrees_with_line_distance():
    import random
    from app.spatial.geometry import within_distance
    rng = random.Random(5)
    shapes = [SQUARE, U_SHAPE, WITH_HOLE]
    for _ in range(400):
        poly = rng.choice(shapes)
        line = [(rng.uniform(-15, 25), rng.uniform(-15, 25)) for _ in range(rng.randint(1, 4))]
        d = rng.uniform(0, 6)
        assert within_distance(poly, line, d) == (line_distance(poly, line) <= d), (line, d)


def test_area_and_chunks():
    from app.spatial.geometry import chunk_line, polygon_area
    assert polygon_area(SQUARE) == pytest.approx(100)
    assert polygon_area(WITH_HOLE) == pytest.approx(84)
    assert polygon_area(U_SHAPE) == pytest.approx(88)  # 100 minus the 2 x 6 notch
    line = [(0, 0), (60, 0), (120, 0), (180, 0), (200, 0)]
    chunks = chunk_line(line, 100)
    assert chunks[0][-1] == chunks[1][0]  # pieces join up
    assert [p for c in chunks for p in c[1:]] == line[1:]
