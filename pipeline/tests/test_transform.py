import geopandas as gpd
from shapely.geometry import box

from pipeline import settings
from pipeline.extract import tag
from pipeline.transform import build_wards, is_devanagari, latin_name, river_width, ward_number


def test_ward_number_from_osm_name():
    assert ward_number("Kathmandu-17") == 17
    assert ward_number("Kathmandu - 4 ") == 4
    assert ward_number("काठमाडौँ महानगरपालिका") is None


def test_latin_name_prefers_english():
    assert latin_name("कालिमाटी", "Kalimati") == "Kalimati"
    assert latin_name("Thamel", None) == "Thamel"
    assert latin_name("ठमेल", None) is None
    assert is_devanagari("ठमेल") and not is_devanagari("Thamel")


def test_river_width_uses_named_estimates():
    assert river_width("Bagmati Nadi (बागमती नदी)", "river") == 40
    assert river_width(float("nan"), "stream") == settings.WATERWAY_WIDTH_M["stream"]


def test_other_tags_parsing():
    tags = '"name:en"=>"Kalimati","power"=>"line"'
    assert tag(tags, "name:en") == "Kalimati"
    assert tag(tags, "power") == "line"
    assert tag(tags, "amenity") is None
    assert tag(None, "name:en") is None


def test_missing_wards_24_and_25_are_filled_from_the_gap():
    # 32 wards in a 4 x 8 grid of 100 m squares (UTM); wards 24 and 25 are missing from "OSM"
    squares = {n + 1: box((n % 8) * 100, (n // 8) * 100, (n % 8 + 1) * 100, (n // 8 + 1) * 100) for n in range(32)}
    kmc = box(0, 0, 800, 400)
    rows = [{"admin_level": "9", "name": f"Kathmandu-{n}", "geometry": g}
            for n, g in squares.items() if n not in (24, 25)]
    admin = gpd.GeoDataFrame(rows, geometry="geometry", crs=settings.UTM).to_crs(settings.WGS84)
    wards, notes = build_wards(admin, kmc)
    assert sorted(wards["ward_no"]) == list(range(1, 33))
    assert set(wards.loc[wards["approximate"], "ward_no"]) == {24, 25}
    assert abs(wards.area.sum() - kmc.area) < 1
    assert notes
