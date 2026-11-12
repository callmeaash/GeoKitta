from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from pipeline import settings
from pipeline.load import ewkt, value


def test_value_converts_pandas_and_numpy_types():
    assert value(np.int64(5)) == 5 and isinstance(value(np.int64(5)), int)
    assert value(3.0) == 3 and isinstance(value(3.0), int)  # int column with missing values
    assert value(254.37) == 254.37
    assert value(float("nan")) is None
    assert value(pd.NA) is None and value(None) is None
    assert value(date(2026, 1, 12)) == date(2026, 1, 12)


def test_ewkt_is_wgs84_with_srid():
    gs = gpd.GeoSeries([box(334600, 3067500, 334620, 3067520)], crs=settings.UTM)
    text = ewkt(gs)[0]
    assert text.startswith("SRID=4326;POLYGON ((85.")
