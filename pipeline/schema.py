from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError

# Tables and columns the pipeline writes to; the schema itself is owned by backend/ (Alembic)
REQUIRED_COLUMNS = {
    "features": {"id", "name", "feature_type", "width_m", "geom", "osm_id"},
    "places": {"id", "name", "name_ne", "place_type", "ward_no", "location", "osm_id"},
    "parcels": {"id", "pin", "district_code", "municipality_code", "ward_no", "map_sheet_code", "parcel_no",
                "parcel_type", "land_use", "registered_area", "status", "boundary", "geometry_source"},
    "owners": {"id", "lin", "owner_type", "full_name", "full_name_ne", "gender", "date_of_birth",
               "citizenship_no", "district_code", "address"},
    "parcel_ownership": {"parcel_id", "owner_id", "share_num", "share_den", "valid_from", "valid_to",
                         "acquired_txn_id", "ended_txn_id"},
    "transactions": {"id", "case_id", "txn_type", "parcel_id", "status", "deed_ref", "deed_date", "office",
                     "created_by"},
    "parcel_lineage": {"parent_id", "child_id", "transaction_id"},
    "parcel_geometry_history": {"parcel_id", "boundary", "area_m2", "valid_from", "valid_to", "transaction_id"},
    "rokka": {"parcel_id", "requested_by_type", "requested_by_name", "reason", "start_date", "fukuwa_date",
              "placed_txn_id", "released_txn_id"},
    "officers": {"id", "username", "password_hash", "full_name", "is_active"},
    "audit_log": {"officer_id", "action", "details"},
}
FIX_HINT = "create the tables with: cd backend && ..\\.venv\\Scripts\\python -m alembic upgrade head"


class SchemaError(Exception):
    pass


def check_schema(engine: Engine) -> None:
    """Raise SchemaError if the database is unreachable or lacks PostGIS or a needed column."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = ANY(:t)"), {"t": list(REQUIRED_COLUMNS)}).all()
            has_postgis = conn.execute(
                text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis')")).scalar()
    except OperationalError as exc:
        raise SchemaError(f"cannot connect to the database ({exc.orig}); check DATABASE_URL in .env") from exc
    actual: dict[str, set[str]] = {}
    for table, column in rows:
        actual.setdefault(table, set()).add(column)
    problems = [] if has_postgis else ["PostGIS is not installed in this database"]
    for table, columns in REQUIRED_COLUMNS.items():
        if table not in actual:
            problems.append(f"table {table} is missing")
        elif missing := sorted(columns - actual[table]):
            problems.append(f"table {table} is missing columns: {', '.join(missing)}")
    if problems:
        raise SchemaError("; ".join(problems) + f". {FIX_HINT}")
