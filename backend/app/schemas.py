"""API request and response models. Public models never carry owner details."""
from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

LonLat = tuple[float, float]


class LookupStats(BaseModel):
    """How the linear quadtree answered a query (shown in the demo and the report)."""

    cells: int = 0
    rows_read: int = 0
    candidates: int = 0
    checked: int = 0
    ms: float = 0.0


class ParcelSummary(BaseModel):
    id: int
    pin: str
    kitta: int
    ward: int
    map_sheet: str
    land_use: str
    parcel_type: str
    area_m2: float = Field(description="registered area")


class Setback(BaseModel):
    feature_id: int
    name: str | None
    feature_type: str
    distance_m: float = Field(description="from the centre line, bank or line, as the rule measures it")
    rule_id: int
    rule_distance_m: float
    measured_from: str
    source: str
    note: str | None


class ParcelDetails(ParcelSummary):
    municipality: str = "Kathmandu Metropolitan City"
    status: str
    geometry_source: str
    accuracy_m: float | None
    boundary_area_m2: float = Field(description="area enclosed by the stored boundary (shoelace formula, UTM)")
    setbacks: list[Setback]
    centre: LonLat
    geometry: dict


class IdentifyResult(BaseModel):
    parcel: ParcelSummary | None
    stats: LookupStats


class ParcelList(BaseModel):
    parcels: list[ParcelSummary]
    count: int
    total_area_m2: float
    truncated: bool = False
    zone: dict | None = None
    stats: LookupStats


class SelectRequest(BaseModel):
    box: tuple[float, float, float, float] | None = Field(None, description="west, south, east, north")
    line: list[LonLat] | None = Field(None, min_length=2, max_length=500)

    @model_validator(mode="after")
    def one_shape(self):
        if (self.box is None) == (self.line is None):
            raise ValueError("give either box or line")
        return self


class OutlinesRequest(BaseModel):
    ids: list[int] = Field(max_length=5000)


class BufferRequest(BaseModel):
    point: LonLat | None = None
    line: list[LonLat] | None = Field(None, min_length=2, max_length=500)
    feature_id: int | None = None
    whole_feature: bool = Field(True, description="include every way of the same named road or river")
    distance_m: float = Field(15, gt=0, le=500)
    rule_id: int | None = Field(None, description="use this setback rule's distance instead of distance_m")

    @model_validator(mode="after")
    def one_source(self):
        if sum(x is not None for x in (self.point, self.line, self.feature_id)) != 1:
            raise ValueError("give exactly one of point, line or feature_id")
        return self


class FeatureOut(BaseModel):
    id: int
    name: str | None
    feature_type: str
    width_m: float | None
    ways: int
    distance_m: float
    geometry: dict


class RuleOut(BaseModel):
    id: int
    feature_type: str
    distance_m: float
    measured_from: str
    source: str
    note: str | None


class PlaceHit(BaseModel):
    id: int
    name: str
    name_ne: str | None
    kind: str
    ward: int | None
    lng: float
    lat: float
    distance: int = Field(description="Levenshtein edits between the query and the name")
    edits: float = Field(description="edits over the matched words after folding spelling variants")


class SearchStats(BaseModel):
    vocabulary: int
    comparisons: int = Field(description="Levenshtein computations the BK-tree needed")
    ms: float


class SearchResult(BaseModel):
    places: list[PlaceHit]
    parcels: list[ParcelSummary]
    suggestion: str | None
    stats: SearchStats


# ---------- Officers (behind login) ----------

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class OfficerOut(BaseModel):
    id: int
    username: str
    full_name: str
    office: str | None
    is_admin: bool


class OwnerHit(BaseModel):
    id: int
    lin: str
    full_name: str
    full_name_ne: str | None
    owner_type: str
    gender: str | None
    date_of_birth: date | None
    district_code: int | None
    parcels: int = Field(description="parcels currently held")
    distance: int = Field(0, description="Levenshtein edits between the searched and the stored name")
    edits: float = Field(0, description="edits after folding spelling variants")


class SimilarOwner(OwnerHit):
    same_dob: bool
    same_district: bool
    likely_duplicate: bool


class Holding(BaseModel):
    parcel: ParcelSummary
    share: str = Field(description="exact fraction, e.g. 1/2")
    valid_from: date
    valid_to: date | None
    case_id: str | None = Field(None, description="case that started the holding")
    txn_type: str | None = None


class OwnerDetails(OwnerHit):
    citizenship_no: str | None
    address: str | None
    phone: str | None
    current: list[Holding]
    past: list[Holding]


class OwnerCreate(BaseModel):
    owner_type: str = Field(pattern="^(individual|organisation|government|communal)$")
    full_name: str = Field(min_length=3, max_length=150)
    full_name_ne: str | None = Field(None, max_length=150)
    gender: str | None = Field(None, pattern="^(male|female|other)$")
    date_of_birth: date | None = None
    citizenship_no: str | None = Field(None, pattern=r"^[0-9][0-9/-]{2,29}$")
    district_code: int = Field(27, ge=1, le=77)
    address: str | None = Field(None, max_length=200)
    phone: str | None = Field(None, pattern=r"^\+?[0-9]{7,15}$")
    confirm_new: bool = Field(False, description="save even though a likely duplicate exists")

    @model_validator(mode="after")
    def individual_details(self):
        self.full_name = " ".join(self.full_name.split())
        if self.owner_type == "individual":
            if self.gender is None or self.date_of_birth is None:
                raise ValueError("an individual needs a gender and a date of birth")
            if not date(1900, 1, 1) <= self.date_of_birth <= date.today():
                raise ValueError("date of birth must be between 1900 and today")
        else:
            self.gender = self.date_of_birth = None
        return self


class SimilarRequest(BaseModel):
    owner_type: str = "individual"
    full_name: str = Field(min_length=2, max_length=150)
    date_of_birth: date | None = None
    district_code: int | None = None


class OwnerOfParcel(BaseModel):
    owner_id: int
    lin: str
    full_name: str
    owner_type: str
    share: str
    valid_from: date
    valid_to: date | None
    case_id: str | None
    txn_type: str | None
    deed_ref: str | None


class RokkaOut(BaseModel):
    id: int
    requested_by_type: str
    requested_by_name: str
    reason: str | None
    start_date: date


class ParcelOwnershipOut(BaseModel):
    parcel_id: int
    current: list[OwnerOfParcel]
    history: list[OwnerOfParcel]
    rokka: list[RokkaOut]


class TxnRow(BaseModel):
    case_id: str
    txn_type: str
    status: str
    deed_date: date | None
    parcel_id: int | None
    pin: str | None
    kitta: int | None
    ward: int | None
    officer: str


class AuditRow(BaseModel):
    action: str
    officer: str
    created_at: datetime
    parcel_id: int | None
    details: dict


class Dashboard(BaseModel):
    active_parcels: int
    owners: int
    open_issues: int
    active_rokka: int
    transactions_30_days: int
    recent_transactions: list[TxnRow]
    recent_activity: list[AuditRow]
