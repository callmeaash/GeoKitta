from datetime import date

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from pipeline import settings
from pipeline.generate import Generated
from pipeline.validate import validate


def make(geoms, shares, defects=None) -> Generated:
    n = len(geoms)
    parcels = gpd.GeoDataFrame({
        "id": range(1, n + 1), "pin": [f"KTM-01-001-{k:04d}" for k in range(1, n + 1)], "ward_no": 1,
        "map_sheet_code": "272010010", "parcel_no": range(1, n + 1), "registered_area": [g.area for g in geoms],
        "status": "active"}, geometry=geoms, crs=settings.UTM)
    ownership = pd.DataFrame([{"parcel_id": pid, "owner_id": oid, "share_num": num, "share_den": den,
                               "valid_from": date(2000, 1, 1), "valid_to": None}
                              for pid, oid, num, den in shares])
    return Generated(parcels=parcels, owners=pd.DataFrame({"lin": ["27-000001-M", "27-000002-F"]}),
                     ownership=ownership, transactions=pd.DataFrame({"case_id": []}), lineage=pd.DataFrame(),
                     history=gpd.GeoDataFrame(geometry=[]), rokka=pd.DataFrame(), defects=defects or [], survey={},
                     stats={})


def test_clean_data_passes():
    gen = make([box(0, 0, 10, 10), box(10, 0, 20, 10)], [(1, 1, 1, 2), (1, 2, 1, 2), (2, 1, 1, 1)])
    report = validate(gen)
    assert report.ok, report.errors


def test_shares_must_add_up_to_one():
    gen = make([box(0, 0, 10, 10)], [(1, 1, 1, 2), (1, 2, 1, 3)])
    assert any("do not add up to 1" in e for e in validate(gen).errors)


def test_unplanted_overlap_is_an_error_and_planted_one_is_not():
    geoms = [box(0, 0, 10, 10), box(9, 0, 19, 10)]  # 10 m² overlap
    shares = [(1, 1, 1, 1), (2, 2, 1, 1)]
    assert any("overlapping" in e for e in validate(make(geoms, shares)).errors)
    planted = [{"type": "overlap", "pins": ["KTM-01-001-0001", "KTM-01-001-0002"]}]
    assert not any("overlapping" in e for e in validate(make(geoms, shares, planted)).errors)


def test_active_parcel_without_owner_is_an_error():
    gen = make([box(0, 0, 10, 10), box(10, 0, 20, 10)], [(1, 1, 1, 1)])
    assert any("no current owner" in e for e in validate(gen).errors)
