import re
from dataclasses import dataclass

import geopandas as gpd
import pandas as pd
import shapely
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from pipeline import settings

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
DEVANAGARI_DIGITS = str.maketrans("0123456789", "०१२३४५६७८९")


@dataclass
class Prepared:
    area: BaseGeometry          # selected wards (or all of KMC), UTM
    wards: gpd.GeoDataFrame     # ward_no, approximate, geometry (UTM)
    roads: gpd.GeoDataFrame     # block-forming roads (UTM) with half_width
    waterways: gpd.GeoDataFrame  # rivers and streams (UTM) with width_m
    buildings: gpd.GeoDataFrame  # footprints (UTM)
    features: gpd.GeoDataFrame  # rows for the features table (WGS84)
    places: gpd.GeoDataFrame    # rows for the places table (WGS84)
    notes: list[str]


def polygonal(geom) -> BaseGeometry:
    """Only the polygon parts of a geometry (overlays can leave stray lines or points)."""
    parts = [g for g in shapely.get_parts(shapely.make_valid(geom)) if g.geom_type in ("Polygon", "MultiPolygon")]
    return shapely.union_all(parts) if parts else shapely.Polygon()


def is_devanagari(text) -> bool:
    return isinstance(text, str) and bool(DEVANAGARI.search(text))


def latin_name(name, name_en) -> str | None:
    """English name if present, otherwise the name when it is already in Latin script."""
    if isinstance(name_en, str) and name_en.strip():
        return name_en.strip()
    if isinstance(name, str) and name.strip() and not is_devanagari(name):
        return name.strip()
    return None


def ward_number(name) -> int | None:
    m = re.search(r"(\d+)\s*$", name or "")
    return int(m.group(1)) if m else None


def build_wards(admin: gpd.GeoDataFrame, kmc: BaseGeometry) -> tuple[gpd.GeoDataFrame, list[str]]:
    """Ward polygons (UTM) clipped to KMC; missing wards 24 and 25 are split from the remaining gap."""
    notes = []
    wards = admin[admin["admin_level"].astype(str) == "9"].copy()
    wards["ward_no"] = wards["name"].map(ward_number)
    wards = wards[wards["ward_no"].between(1, settings.WARD_COUNT)].to_crs(settings.UTM)
    wards = wards.dissolve("ward_no").reset_index()[["ward_no", "geometry"]]
    wards["geometry"] = [polygonal(g.intersection(kmc)) for g in wards.geometry]
    wards["approximate"] = False

    missing = sorted(set(range(1, settings.WARD_COUNT + 1)) - set(wards["ward_no"]))
    if missing:
        gap = kmc.difference(wards.union_all())
        parts = [g for g in getattr(gap, "geoms", [gap]) if g.area > 1000]
        if missing == list(settings.GAP_WARDS) and parts:
            gap_main = gpd.GeoSeries(parts).union_all()
            minx, miny, maxx, maxy = gap_main.bounds
            cy = gap_main.centroid.y
            north = polygonal(gap_main.intersection(box(minx, cy, maxx, maxy)))
            south = polygonal(gap_main.intersection(box(minx, miny, maxx, cy)))
            extra = gpd.GeoDataFrame({"ward_no": list(settings.GAP_WARDS), "approximate": True},
                                     geometry=[north, south], crs=settings.UTM)
            wards = pd.concat([wards, extra], ignore_index=True)
            notes.append(f"wards {settings.GAP_WARDS} are not in OSM; split the {gap_main.area / 1e6:.2f} km² gap "
                         "north/south (approximate)")
        else:
            notes.append(f"wards missing from OSM and not filled: {missing}")
    return gpd.GeoDataFrame(wards, geometry="geometry", crs=settings.UTM), notes


def assign_ward(geoms: gpd.GeoSeries, wards: gpd.GeoDataFrame) -> pd.Series:
    """Ward number for each geometry, by its representative point (nearest ward if outside all)."""
    pts = gpd.GeoDataFrame(geometry=geoms.representative_point().values, crs=geoms.crs, index=geoms.index)
    joined = gpd.sjoin_nearest(pts, wards[["ward_no", "geometry"]], how="left")
    return joined.groupby(level=0)["ward_no"].first().reindex(geoms.index)


def explode_lines(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.explode(index_parts=False)
    return gdf[gdf.geom_type == "LineString"]


def river_width(name, waterway: str) -> float:
    lower = name.lower() if isinstance(name, str) else ""
    for key, width in settings.NAMED_RIVER_WIDTH_M.items():
        if key in lower:
            return width
    return settings.WATERWAY_WIDTH_M.get(waterway, 5)


def transform(snap: dict[str, gpd.GeoDataFrame], wards_filter: list[int] | None = None) -> Prepared:
    kmc = snap["boundary"].to_crs(settings.UTM).geometry.iloc[0]
    wards, notes = build_wards(snap["admin"], kmc)
    if wards_filter:
        unknown = sorted(set(wards_filter) - set(wards["ward_no"]))
        if unknown:
            raise ValueError(f"unknown ward numbers: {unknown}")
        area = polygonal(wards[wards["ward_no"].isin(wards_filter)].union_all())
    else:
        area = polygonal(kmc)
    near_area = area.buffer(100)

    roads = explode_lines(snap["roads"].to_crs(settings.UTM))
    roads = roads[roads["highway"].isin(settings.ROAD_HALF_WIDTH_M) & roads.intersects(near_area)].copy()
    roads["half_width"] = roads["highway"].map(settings.ROAD_HALF_WIDTH_M)

    waterways = explode_lines(snap["waterways"].to_crs(settings.UTM))
    waterways = waterways[waterways.intersects(near_area)].copy()
    waterways["width_m"] = [river_width(n, w) for n, w in zip(waterways["name"], waterways["waterway"])]

    buildings = snap["buildings"].to_crs(settings.UTM)
    buildings = buildings[buildings.geometry.notna()]
    buildings = buildings[buildings.geometry.make_valid().geom_type.isin(["Polygon", "MultiPolygon"])]
    buildings = buildings[buildings.representative_point().within(area)].copy()

    # ---------- features table ----------
    road_rows = roads.assign(
        name=[latin_name(n, e) or n for n, e in zip(roads["name"], roads["name_en"])],
        feature_type=["highway" if h in settings.HIGHWAY_TYPES else "road" for h in roads["highway"]],
        width_m=roads["half_width"] * 2)
    water_rows = waterways.assign(
        name=[latin_name(n, e) or n for n, e in zip(waterways["name"], waterways["name_en"])],
        feature_type=["river" if w == "river" else "stream" for w in waterways["waterway"]])
    power = explode_lines(snap["power"].to_crs(settings.UTM))
    power_rows = power[power.intersects(near_area)].assign(feature_type="power_line", width_m=None)
    cols = ["name", "feature_type", "width_m", "osm_id", "geometry"]
    features = pd.concat([road_rows[cols], water_rows[cols], power_rows.reindex(columns=cols)], ignore_index=True)
    features = gpd.GeoDataFrame(features, geometry="geometry", crs=settings.UTM).to_crs(settings.WGS84)

    # ---------- places table ----------
    def place_rows(gdf: gpd.GeoDataFrame, place_type: str) -> gpd.GeoDataFrame:
        gdf = gdf.to_crs(settings.UTM)
        pts = gdf.geometry.representative_point()
        gdf = gdf.assign(geometry=pts.values)[pts.within(area).values]
        return gpd.GeoDataFrame({
            "name": [latin_name(n, e) for n, e in zip(gdf["name"], gdf["name_en"])],
            "name_ne": [n if is_devanagari(n) else None for n in gdf["name"]],
            "place_type": place_type, "osm_id": gdf["osm_id"].values}, geometry=gdf.geometry.values, crs=settings.UTM)

    river_points = []
    for name, group in water_rows[water_rows["feature_type"] == "river"].groupby("name"):
        longest = group.loc[group.length.idxmax()].geometry
        river_points.append({"name": name, "name_ne": None, "place_type": "river", "osm_id": None,
                             "geometry": longest.interpolate(0.5, normalized=True)})
    ward_points = [{"name": f"Ward {w}", "name_ne": f"वडा नं. {str(w).translate(DEVANAGARI_DIGITS)}",
                    "place_type": "ward", "osm_id": None, "geometry": g.representative_point()}
                   for w, g in zip(wards["ward_no"], wards.geometry) if g.representative_point().within(area)]
    places = pd.concat([
        place_rows(snap["places"], "tole"), place_rows(snap["landmarks"], "landmark"),
        place_rows(snap["parks"], "park"),
        gpd.GeoDataFrame(river_points, geometry="geometry", crs=settings.UTM) if river_points else None,
        gpd.GeoDataFrame(ward_points, geometry="geometry", crs=settings.UTM),
    ], ignore_index=True)
    places = gpd.GeoDataFrame(places, geometry="geometry", crs=settings.UTM)
    places = places[places["name"].notna()].drop_duplicates(["name", "place_type"])
    places["ward_no"] = assign_ward(places.geometry, wards).astype("Int64")
    places = places.to_crs(settings.WGS84)

    return Prepared(area=area, wards=wards, roads=roads, waterways=waterways, buildings=buildings,
                    features=features, places=places, notes=notes)
