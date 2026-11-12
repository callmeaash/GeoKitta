"""API request and response models. Public models never carry owner details."""
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
