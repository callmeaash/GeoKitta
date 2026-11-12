"""Schema checks that need no database connection."""
from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint

from app.models import Base

TABLES = {
    "parcels", "parcel_quadkeys", "parcel_geometry_history", "parcel_lineage", "parcel_issues",
    "owners", "parcel_ownership", "transactions", "rokka",
    "officers", "audit_log",
    "places", "features", "setback_rules",
}


def checks(table_name: str) -> set[str]:
    table = Base.metadata.tables[table_name]
    return {c.name for c in table.constraints if isinstance(c, CheckConstraint)}


def test_has_exactly_the_14_tables():
    assert set(Base.metadata.tables) == TABLES


def test_no_gist_spatial_indexes():
    # The linear quadtree is the project's spatial index; geometry columns must not get GiST indexes.
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, Geometry):
                assert column.type.spatial_index is False, f"{table.name}.{column.name}"
        for index in table.indexes:
            assert index.dialect_options["postgresql"].get("using") != "gist", index.name


def test_geometry_types_and_srid():
    expected = {
        ("parcels", "boundary"): "POLYGON",
        ("parcel_geometry_history", "boundary"): "POLYGON",
        ("places", "location"): "POINT",
        ("features", "geom"): "LINESTRING",
    }
    for (table, column), geometry_type in expected.items():
        col_type = Base.metadata.tables[table].c[column].type
        assert col_type.geometry_type == geometry_type
        assert col_type.srid == 4326


def test_quadkey_uses_c_collation_and_is_indexed():
    table = Base.metadata.tables["parcel_quadkeys"]
    assert table.c.quadkey.type.collation == "C"
    assert any(list(ix.columns) == [table.c.quadkey] for ix in table.indexes)


def test_parcel_rules_are_enforced_in_the_database():
    assert {"ck_parcels_boundary_valid", "ck_parcels_district_code", "ck_parcels_map_sheet_code",
            "ck_parcels_registered_area"} <= checks("parcels")
    unique = {c.name for c in Base.metadata.tables["parcels"].constraints if c.__class__.__name__ == "UniqueConstraint"}
    assert "uq_parcels_kitta" in unique


def test_ownership_shares_are_exact_fractions():
    table = Base.metadata.tables["parcel_ownership"]
    assert {"share_num", "share_den"} <= set(table.c.keys())
    assert "ck_parcel_ownership_share" in checks("parcel_ownership")
