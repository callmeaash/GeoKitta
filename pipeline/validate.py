from dataclasses import dataclass, field
from fractions import Fraction

import shapely
from shapely.strtree import STRtree

from pipeline import settings
from pipeline.generate import Generated

OVERLAP_TOLERANCE_M2 = 0.1  # shared edges can differ by floating-point noise; planted overlaps are several m²


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def unexpected_overlaps(gen: Generated) -> list[tuple[str, str]]:
    """Pairs of active parcels whose interiors overlap, excluding the planted defects."""
    p = gen.parcels[gen.parcels["status"] == "active"]
    geoms, pins = p.geometry.values, p["pin"].values
    planted = [set(d["pins"]) | set(d.get("also_overlaps", [])) for d in gen.defects
               if d["type"] in ("overlap", "overlap_cross")]
    left, right = STRtree(geoms).query(geoms, predicate="overlaps")
    found = []
    for i, j in zip(left, right):
        if i < j and not any({pins[i], pins[j]} <= s for s in planted):
            if shapely.intersection(geoms[i], geoms[j]).area > OVERLAP_TOLERANCE_M2:
                found.append((pins[i], pins[j]))
    return found


def validate(gen: Generated) -> Report:
    r = Report()
    p = gen.parcels

    if (p.geom_type != "Polygon").any():
        r.errors.append(f"{int((p.geom_type != 'Polygon').sum())} parcels are not single polygons")
    if (~p.is_valid).any():
        r.errors.append(f"{int((~p.is_valid).sum())} parcels have invalid geometry")
    if p["pin"].duplicated().any():
        r.errors.append(f"{int(p['pin'].duplicated().sum())} duplicate PINs")
    if p.duplicated(["ward_no", "map_sheet_code", "parcel_no"]).any():
        r.errors.append("duplicate kitta numbers within a map sheet")
    if not p["ward_no"].between(1, settings.WARD_COUNT).all():
        r.errors.append("ward numbers outside 1-32")
    if not p["map_sheet_code"].str.fullmatch(r"\d{9}").all():
        r.errors.append("map sheet codes must be 9 digits")
    if (p["registered_area"] <= 0).any():
        r.errors.append("registered areas must be positive")

    own = gen.ownership
    current = own[own["valid_to"].isna()]
    totals = current.groupby("parcel_id").apply(
        lambda g: sum(Fraction(int(n), int(d)) for n, d in zip(g["share_num"], g["share_den"])), include_groups=False)
    if (totals != 1).any():
        r.errors.append(f"{int((totals != 1).sum())} parcels have current shares that do not add up to 1")
    active_ids = set(p.loc[p["status"] == "active", "id"])
    no_owner = active_ids - set(current["parcel_id"])
    if no_owner:
        r.errors.append(f"{len(no_owner)} active parcels have no current owner")
    if set(current["parcel_id"]) - active_ids:
        r.errors.append("retired parcels still have current owners")
    if current.duplicated(["parcel_id", "owner_id"]).any():
        r.errors.append("an owner holds two current shares of the same parcel")
    closed = own[own["valid_to"].notna()]
    if (closed["valid_to"] < closed["valid_from"]).any():
        r.errors.append("ownership periods end before they start")

    if gen.owners["lin"].duplicated().any():
        r.errors.append("duplicate LINs")
    if gen.transactions["case_id"].duplicated().any():
        r.errors.append("duplicate case IDs")

    overlaps = unexpected_overlaps(gen)
    if len(overlaps) > 0.001 * len(p):
        r.errors.append(f"{len(overlaps)} unexpected overlapping parcel pairs, e.g. {overlaps[:3]}")
    elif overlaps:
        r.warnings.append(f"{len(overlaps)} unexpected overlapping parcel pairs, e.g. {overlaps[:3]}")

    kinds = {d["type"] for d in gen.defects}
    for needed in ("overlap", "overlap_cross", "sliver", "area_mismatch", "duplicate_owner"):
        if needed not in kinds:
            r.warnings.append(f"no planted '{needed}' defect (the area may be too small)")
    return r
