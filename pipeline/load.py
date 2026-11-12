import json
import logging

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from sqlalchemy import Connection, Engine, text

from pipeline import settings
from pipeline.generate import Generated, largest
from pipeline.transform import Prepared

log = logging.getLogger(__name__)

# Synthetic data the pipeline replaces with --reset (officers and setback_rules are kept)
DATA_TABLES = ["parcel_quadkeys", "parcel_issues", "parcel_geometry_history", "parcel_lineage", "rokka",
               "parcel_ownership", "transactions", "owners", "parcels", "places", "features", "audit_log"]
SERIAL_TABLES = ["features", "places", "parcels", "owners", "transactions", "parcel_ownership",
                 "parcel_geometry_history", "rokka", "audit_log"]


class LoadError(Exception):
    pass


def ewkt(geoms: gpd.GeoSeries) -> list[str]:
    """WGS84 EWKT with ~1 cm precision; any shape made invalid by rounding is repaired to its largest polygon."""
    values = shapely.set_precision(geoms.to_crs(settings.WGS84).values, 1e-7)
    out = []
    for g in values:
        if g.geom_type not in ("Polygon", "Point", "LineString") or not g.is_valid:
            g = largest(g) if g.geom_type != "LineString" else g
        out.append(f"SRID=4326;{g.wkt}")
    return out


def value(v):
    """pandas/numpy value -> plain Python for psycopg (None for missing)."""
    if v is None or v is pd.NA or v is pd.NaT:
        return None
    v = v.item() if isinstance(v, np.generic) else v
    if isinstance(v, float):
        if np.isnan(v):
            return None
        if v.is_integer():
            return int(v)  # int columns with missing values arrive as floats from pandas
    return v


def copy(conn: Connection, table: str, df: pd.DataFrame, columns: list[str], geom_col: str | None = None,
         geoms: list[str] | None = None) -> None:
    cursor = conn.connection.driver_connection.cursor()
    cols = columns + ([geom_col] if geom_col else [])
    with cursor.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as cp:
        for n, row in enumerate(df[columns].itertuples(index=False, name=None)):
            cp.write_row([value(v) for v in row] + ([geoms[n]] if geom_col else []))


def existing_parcels(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM parcels")).scalar_one()


def run_load(engine: Engine, prep: Prepared, gen: Generated, reset: bool, run_details: dict) -> dict[str, int]:
    """Replace the synthetic data in one transaction; nothing changes if any step fails."""
    with engine.begin() as conn:
        existing = conn.execute(text("SELECT count(*) FROM parcels")).scalar_one()
        if existing and not reset:
            raise LoadError(f"parcels already has {existing} rows; rerun with --reset to replace the synthetic data")
        if reset:
            conn.exec_driver_sql(f"TRUNCATE {', '.join(DATA_TABLES)} RESTART IDENTITY CASCADE")

        officer = conn.execute(text("""
            INSERT INTO officers (username, password_hash, full_name, office, is_admin, is_active)
            VALUES (:u, '!', 'Data import (synthetic)', 'GeoKitta pipeline', false, false)
            ON CONFLICT (username) DO UPDATE SET is_active = false
            RETURNING id"""), {"u": settings.PIPELINE_USERNAME}).scalar_one()

        f = prep.features
        copy(conn, "features", f, ["name", "feature_type", "width_m", "osm_id"], "geom", ewkt(f.geometry))
        pl = prep.places
        copy(conn, "places", pl, ["name", "name_ne", "place_type", "ward_no", "osm_id"], "location", ewkt(pl.geometry))

        p = gen.parcels.assign(district_code=settings.DISTRICT_CODE, municipality_code=settings.MUNICIPALITY_CODE,
                               geometry_source="synthetic")
        copy(conn, "parcels", p, ["id", "pin", "district_code", "municipality_code", "ward_no", "map_sheet_code",
                                  "parcel_no", "parcel_type", "land_use", "registered_area", "status",
                                  "geometry_source"], "boundary", ewkt(p.geometry))
        copy(conn, "owners", gen.owners, ["id", "lin", "owner_type", "full_name", "full_name_ne", "gender",
                                          "date_of_birth", "citizenship_no", "district_code", "address"])
        copy(conn, "transactions", gen.transactions.assign(created_by=officer),
             ["id", "case_id", "txn_type", "parcel_id", "status", "deed_ref", "deed_date", "office", "created_by"])
        copy(conn, "parcel_ownership", gen.ownership, ["parcel_id", "owner_id", "share_num", "share_den",
                                                       "valid_from", "valid_to", "acquired_txn_id", "ended_txn_id"])
        copy(conn, "parcel_lineage", gen.lineage, ["parent_id", "child_id", "transaction_id"])
        h = gen.history
        if len(h):
            copy(conn, "parcel_geometry_history", h, ["parcel_id", "area_m2", "valid_from", "valid_to",
                                                      "transaction_id"], "boundary", ewkt(h.geometry))
        if len(gen.rokka):
            copy(conn, "rokka", gen.rokka, ["parcel_id", "requested_by_type", "requested_by_name", "reason",
                                            "start_date", "fukuwa_date", "placed_txn_id", "released_txn_id"])

        for table in SERIAL_TABLES:
            conn.exec_driver_sql(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT max(id) FROM {table}), 1), (SELECT max(id) FROM {table}) IS NOT NULL)")

        counts = {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
                  for t in ["features", "places", "parcels", "owners", "parcel_ownership", "transactions",
                            "parcel_lineage", "parcel_geometry_history", "rokka"]}
        conn.execute(text("INSERT INTO audit_log (officer_id, action, details) "
                          "VALUES (:o, 'pipeline_import', CAST(:d AS jsonb))"),
                     {"o": officer, "d": json.dumps({**run_details, "counts": counts}, default=str)})
    return counts
