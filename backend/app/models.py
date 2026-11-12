"""Database schema: 14 tables. No GiST indexes; parcel_quadkeys is the spatial index."""
from datetime import date, datetime
from decimal import Decimal

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SRID = 4326  # WGS 84 latitude/longitude

# Predictable constraint and index names, so Alembic migrations are stable
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# ---------- Allowed values ----------
OWNER_TYPES = ("individual", "organisation", "government", "communal")
GENDERS = ("male", "female", "other")
PARCEL_TYPES = ("private", "public", "government", "guthi")
LAND_USES = ("residential", "commercial", "agricultural", "institutional", "other")
PARCEL_STATUSES = ("active", "retired")
GEOMETRY_SOURCES = ("field_survey", "digitized", "synthetic")
TXN_TYPES = (
    "registration", "boundary_update", "split", "merge",
    "rajinama", "hal_ko_bakaspatra", "danpatra", "chhod_patra",
    "ansha_banda", "namasari", "samsodhan", "rokka", "fukuwa",
)
TXN_STATUSES = ("draft", "approved", "rejected")
REQUESTER_TYPES = ("bank", "court", "ciaa", "government", "other")
ISSUE_TYPES = ("overlap", "gap", "sliver", "invalid", "area_mismatch")
SEVERITIES = ("error", "warning")
REVIEW_STATUSES = ("open", "resolved", "dispute")
PLACE_TYPES = ("tole", "landmark", "park", "river", "road", "ward")
FEATURE_TYPES = ("highway", "road", "river", "stream", "power_line")
MEASURED_FROM = ("centre_line", "bank", "line")
RULE_SOURCES = ("municipal", "national")


def one_of(column: str, values: tuple[str, ...], name: str | None = None) -> CheckConstraint:
    """CHECK that a text column holds one of the allowed values."""
    allowed = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name or column)


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def updated_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# =========================================================
# Officers & audit
# =========================================================
class Officer(Base):
    """Officer accounts; admins have is_admin = true."""

    __tablename__ = "officers"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(Text, comment="argon2 hash; never the password itself")
    full_name: Mapped[str] = mapped_column(String(100))
    office: Mapped[str | None] = mapped_column(String(100))
    is_admin: Mapped[bool] = mapped_column(server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = created_at()
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("username ~ '^[a-z][a-z0-9_.]{2,49}$'", name="username_format"),
    )


class AuditLog(Base):
    """Who changed what and when."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    officer_id: Mapped[int] = mapped_column(ForeignKey("officers.id"))
    action: Mapped[str] = mapped_column(
        String(40), comment="e.g. parcel_registered, boundary_updated, ownership_transferred"
    )
    parcel_id: Mapped[int | None] = mapped_column(ForeignKey("parcels.id"), index=True)
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"))
    details: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        Index("ix_audit_log_created_at", "created_at"),
    )


# =========================================================
# Parcels & spatial index
# =========================================================
class Parcel(Base):
    """A kitta (land parcel)."""

    __tablename__ = "parcels"

    id: Mapped[int] = mapped_column(primary_key=True)
    pin: Mapped[str] = mapped_column(String(30), unique=True, comment="Parcel Identification Number")
    district_code: Mapped[int] = mapped_column(SmallInteger)
    municipality_code: Mapped[int] = mapped_column(Integer)
    ward_no: Mapped[int] = mapped_column(SmallInteger)
    map_sheet_code: Mapped[str] = mapped_column(String(9), comment="9-digit map sheet geocode (GRIDS1-style)")
    parcel_no: Mapped[int] = mapped_column(Integer, comment="kitta number")
    parcel_type: Mapped[str] = mapped_column(String(20))
    land_use: Mapped[str] = mapped_column(String(20))
    registered_area: Mapped[Decimal] = mapped_column(Numeric(12, 2), comment="m², as recorded")
    status: Mapped[str] = mapped_column(String(10), server_default=text("'active'"))
    boundary = mapped_column(
        Geometry("POLYGON", srid=SRID, spatial_index=False), nullable=False,
        comment="single polygon, EPSG:4326; must be valid",
    )
    geometry_source: Mapped[str] = mapped_column(String(20), server_default=text("'field_survey'"))
    accuracy_m: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    __table_args__ = (
        UniqueConstraint("municipality_code", "ward_no", "map_sheet_code", "parcel_no", name="uq_parcels_kitta"),
        CheckConstraint("district_code BETWEEN 1 AND 77", name="district_code"),
        CheckConstraint("ward_no BETWEEN 1 AND 40", name="ward_no"),
        CheckConstraint("map_sheet_code ~ '^[0-9]{9}$'", name="map_sheet_code"),
        CheckConstraint("parcel_no > 0", name="parcel_no"),
        CheckConstraint("registered_area > 0", name="registered_area"),
        CheckConstraint("accuracy_m IS NULL OR accuracy_m > 0", name="accuracy_m"),
        CheckConstraint("ST_IsValid(boundary)", name="boundary_valid"),
        one_of("parcel_type", PARCEL_TYPES),
        one_of("land_use", LAND_USES),
        one_of("status", PARCEL_STATUSES),
        one_of("geometry_source", GEOMETRY_SOURCES),
    )


class ParcelQuadkey(Base):
    """Linear quadtree entry: 1-4 rows per parcel. Box in UTM 45N metres; collation "C" for prefix ranges."""

    __tablename__ = "parcel_quadkeys"

    parcel_id: Mapped[int] = mapped_column(ForeignKey("parcels.id", ondelete="CASCADE"), primary_key=True)
    quadkey: Mapped[str] = mapped_column(
        String(24, collation="C"), primary_key=True, index=True, comment="quadrant digits 0-3 from the root"
    )
    min_x: Mapped[float] = mapped_column(Double, comment="UTM 45N metres")
    min_y: Mapped[float] = mapped_column(Double)
    max_x: Mapped[float] = mapped_column(Double)
    max_y: Mapped[float] = mapped_column(Double)

    __table_args__ = (
        CheckConstraint("quadkey ~ '^[0-3]*$'", name="quadkey_digits"),
        CheckConstraint("min_x <= max_x AND min_y <= max_y", name="bbox_order"),
    )


class ParcelGeometryHistory(Base):
    """Previous boundaries, kept when a boundary is updated."""

    __tablename__ = "parcel_geometry_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    parcel_id: Mapped[int] = mapped_column(ForeignKey("parcels.id"), index=True)
    boundary = mapped_column(Geometry("POLYGON", srid=SRID, spatial_index=False), nullable=False)
    area_m2: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"))

    __table_args__ = (
        CheckConstraint("valid_to >= valid_from", name="valid_period"),
        CheckConstraint("area_m2 > 0", name="area_m2"),
    )


class ParcelLineage(Base):
    """Parent → child links created by splits (kitta kaat) and merges."""

    __tablename__ = "parcel_lineage"

    parent_id: Mapped[int] = mapped_column(ForeignKey("parcels.id"), primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("parcels.id"), primary_key=True, index=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"))

    __table_args__ = (
        CheckConstraint("parent_id <> child_id", name="not_self"),
    )


class ParcelIssue(Base):
    """Validation problems found on save."""

    __tablename__ = "parcel_issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    parcel_id: Mapped[int] = mapped_column(ForeignKey("parcels.id"), index=True)
    other_parcel_id: Mapped[int | None] = mapped_column(
        ForeignKey("parcels.id"), comment="the other parcel, for overlaps"
    )
    issue_type: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(10))
    details: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    review_status: Mapped[str] = mapped_column(String(10), server_default=text("'open'"))
    review_note: Mapped[str | None] = mapped_column(Text)
    found_at: Mapped[datetime] = created_at()
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("officers.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("other_parcel_id IS NULL OR other_parcel_id <> parcel_id", name="other_parcel"),
        one_of("issue_type", ISSUE_TYPES),
        one_of("severity", SEVERITIES),
        one_of("review_status", REVIEW_STATUSES),
    )


# =========================================================
# Ownership & transactions
# =========================================================
class Owner(Base):
    """One row per owner (LIN)."""

    __tablename__ = "owners"

    id: Mapped[int] = mapped_column(primary_key=True)
    lin: Mapped[str] = mapped_column(String(20), unique=True, comment="Landowner Identification Number")
    owner_type: Mapped[str] = mapped_column(String(20))
    full_name: Mapped[str] = mapped_column(String(150))
    full_name_ne: Mapped[str | None] = mapped_column(String(150), comment="name in Devanagari")
    gender: Mapped[str | None] = mapped_column(String(10))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    citizenship_no: Mapped[str | None] = mapped_column(String(30))
    district_code: Mapped[int | None] = mapped_column(SmallInteger)
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = created_at()

    __table_args__ = (
        CheckConstraint("district_code BETWEEN 1 AND 77", name="district_code"),
        CheckConstraint("owner_type <> 'individual' OR date_of_birth IS NOT NULL", name="individual_dob"),
        one_of("owner_type", OWNER_TYPES),
        one_of("gender", GENDERS),
    )


class ParcelOwnership(Base):
    """Owner, exact share and period for a parcel."""

    __tablename__ = "parcel_ownership"

    id: Mapped[int] = mapped_column(primary_key=True)
    parcel_id: Mapped[int] = mapped_column(ForeignKey("parcels.id"))
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"), index=True)
    share_num: Mapped[int] = mapped_column(Integer)
    share_den: Mapped[int] = mapped_column(Integer)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, comment="NULL = current owner")
    acquired_txn_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"))
    ended_txn_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"))

    __table_args__ = (
        CheckConstraint("share_num > 0 AND share_den > 0 AND share_num <= share_den", name="share"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="valid_period"),
        Index("ix_parcel_ownership_parcel_id", "parcel_id"),
        # The same owner cannot hold two current shares of one parcel
        Index("uq_parcel_ownership_current", "parcel_id", "owner_id", unique=True,
              postgresql_where=text("valid_to IS NULL")),
    )


class Transaction(Base):
    """A case: registration, boundary update, split or deed."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(String(20), unique=True, comment="CaseID, unique across the system")
    txn_type: Mapped[str] = mapped_column(String(30))
    parcel_id: Mapped[int | None] = mapped_column(ForeignKey("parcels.id"), index=True,
                                                  comment="parcel concerned; the parent for a split")
    status: Mapped[str] = mapped_column(String(10), server_default=text("'draft'"))
    deed_ref: Mapped[str | None] = mapped_column(String(40))
    deed_date: Mapped[date | None] = mapped_column(Date)
    office: Mapped[str | None] = mapped_column(String(100))
    remarks: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("officers.id"))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()

    __table_args__ = (
        CheckConstraint("case_id ~ '^[0-9]{6,20}$'", name="case_id_format"),
        one_of("txn_type", TXN_TYPES),
        one_of("status", TXN_STATUSES),
    )


class Rokka(Base):
    """A hold on a parcel and its release (fukuwa)."""

    __tablename__ = "rokka"

    id: Mapped[int] = mapped_column(primary_key=True)
    parcel_id: Mapped[int] = mapped_column(ForeignKey("parcels.id"), index=True)
    requested_by_type: Mapped[str] = mapped_column(String(20))
    requested_by_name: Mapped[str] = mapped_column(String(150))
    reason: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date] = mapped_column(Date)
    fukuwa_date: Mapped[date | None] = mapped_column(Date, comment="NULL = still active")
    placed_txn_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"))
    released_txn_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"))

    __table_args__ = (
        CheckConstraint("fukuwa_date IS NULL OR fukuwa_date >= start_date", name="valid_period"),
        one_of("requested_by_type", REQUESTER_TYPES),
    )


# =========================================================
# Map reference data
# =========================================================
class Place(Base):
    """Named places for place search."""

    __tablename__ = "places"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    name_ne: Mapped[str | None] = mapped_column(String(150), comment="name in Devanagari")
    place_type: Mapped[str] = mapped_column(String(20))
    ward_no: Mapped[int | None] = mapped_column(SmallInteger)
    location = mapped_column(Geometry("POINT", srid=SRID, spatial_index=False), nullable=False)
    osm_id: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        one_of("place_type", PLACE_TYPES),
    )


class Feature(Base):
    """Roads, rivers and power lines for buffer and setback search."""

    __tablename__ = "features"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(150))
    feature_type: Mapped[str] = mapped_column(String(20))
    width_m: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), comment="needed for setbacks measured from the bank")
    geom = mapped_column(Geometry("LINESTRING", srid=SRID, spatial_index=False), nullable=False)
    osm_id: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        CheckConstraint("width_m IS NULL OR width_m > 0", name="width_m"),
        one_of("feature_type", FEATURE_TYPES),
    )


class SetbackRule(Base):
    """Setback distance per feature type."""

    __tablename__ = "setback_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_type: Mapped[str] = mapped_column(String(20))
    distance_m: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    measured_from: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("feature_type", "source", name="uq_setback_rules_feature_source"),
        CheckConstraint("distance_m > 0", name="distance_m"),
        one_of("feature_type", FEATURE_TYPES),
        one_of("measured_from", MEASURED_FROM),
        one_of("source", RULE_SOURCES),
    )
