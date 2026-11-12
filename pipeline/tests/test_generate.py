import geopandas as gpd
import shapely
from shapely.geometry import Polygon, box

from pipeline import settings
from pipeline.generate import bisect, footprint_cells, parcels_from_blocks, split_to_size


def test_bisect_halves_keep_the_area():
    poly = box(0, 0, 100, 40)
    pieces = bisect(poly)
    assert len(pieces) == 2
    assert abs(sum(p.area for p in pieces) - poly.area) < 1e-6
    assert all(p.area < poly.area * 0.6 for p in pieces)


def test_split_to_size_respects_the_limit():
    poly = Polygon([(0, 0), (300, 0), (280, 120), (10, 100)])
    pieces = split_to_size(poly, 2000)
    assert all(p.area <= 2000 for p in pieces)
    assert abs(sum(p.area for p in pieces) - poly.area) < 0.1  # 1 mm overlay grid loses a few cm² over many cuts


def test_one_parcel_per_building_without_overlaps():
    block = box(0, 0, 60, 30)
    footprints = [box(5, 5, 12, 12), box(25, 8, 33, 15), box(45, 18, 52, 25)]
    buildings = gpd.GeoDataFrame({"building": ["yes", "house", "yes"], "amenity": [None, None, None]},
                                 geometry=footprints, crs=settings.UTM)
    rows = parcels_from_blocks([block], buildings)
    parcels = [r["geometry"] for r in rows]
    assert len(parcels) == 3
    assert all(r["building"] is not None for r in rows)
    assert abs(sum(p.area for p in parcels) - block.area) < 0.01
    for i, a in enumerate(parcels):
        assert a.covers(footprints[i].representative_point())
        for b in parcels[i + 1:]:
            assert shapely.intersection(a, b).area < 1e-6


def test_block_without_buildings_becomes_open_plots():
    block = box(0, 0, 100, 60)  # 6000 m² of open land
    rows = parcels_from_blocks([block], gpd.GeoDataFrame({"building": [], "amenity": []}, geometry=[],
                                                         crs=settings.UTM))
    assert len(rows) >= 2
    assert all(r["building"] is None for r in rows)
    assert all(r["geometry"].area <= settings.OPEN_PLOT_TARGET_M2 * 1.5 for r in rows)


def test_footprint_cells_do_not_cut_a_long_building():
    block = box(0, 0, 60, 30)
    long, small = box(2, 2, 40, 10), box(42, 2, 48, 8)  # centre-point Voronoi would cut the long one near x = 33
    cells = footprint_cells(block, [long, small], [long.centroid, small.centroid])
    assert shapely.intersection(cells[0], long).area > 0.99 * long.area
    assert shapely.intersection(cells[1], small).area > 0.99 * small.area
    assert abs(sum(c.area for c in cells) - block.area) < 0.01
    assert shapely.intersection(cells[0], cells[1]).area < 1e-6
