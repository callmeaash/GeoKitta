"""Report what OpenStreetMap has for Kathmandu Metropolitan City (KMC), from the local Geofabrik extract."""
import json
import time
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pyogrio

ROOT = Path(__file__).resolve().parents[1]
PBF = ROOT / "data" / "cache" / "osm" / "nepal-latest.osm.pbf"
OUT = ROOT / "data" / "explore"
UTM = "EPSG:32645"
KMC_QUERY = "Kathmandu Metropolitan City, Nepal"
PLACE_TYPES = {"suburb", "quarter", "neighbourhood", "locality", "hamlet", "village", "isolated_dwelling"}


def timed(label, fn):
    start = time.perf_counter()
    result = fn()
    print(f"  ({label}: {time.perf_counter() - start:.1f} s)")
    return result


def kmc_boundary() -> gpd.GeoDataFrame:
    cached = OUT / "kmc_boundary.geojson"
    if cached.exists():
        return gpd.read_file(cached)
    gdf = ox.geocode_to_gdf(KMC_QUERY)[["display_name", "osm_type", "osm_id", "geometry"]]
    gdf.to_file(cached, driver="GeoJSON")
    return gdf


def read(layer, poly, columns):
    """Read one OSM layer inside KMC's bounding box, then keep features whose centre is inside KMC."""
    gdf = timed(layer, lambda: pyogrio.read_dataframe(PBF, layer=layer, bbox=poly.bounds, columns=columns))
    return gdf[gdf.geometry.representative_point().within(poly)]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {"source": f"Geofabrik extract {PBF.name}, {time.ctime(PBF.stat().st_mtime)}"}

    print("\n== KMC boundary")
    kmc = kmc_boundary()
    poly = kmc.geometry.iloc[0]
    area_km2 = kmc.to_crs(UTM).area.iloc[0] / 1e6
    summary["boundary"] = {"area_km2": round(float(area_km2), 2), "bounds_lonlat": [round(v, 5) for v in poly.bounds]}
    print(f"  {summary['boundary']}")

    print("\n== Polygons: admin boundaries, buildings, land use")
    mp = read("multipolygons", poly, ["osm_id", "osm_way_id", "name", "admin_level", "boundary", "building", "landuse"])

    admin = mp[mp["boundary"] == "administrative"]
    levels = admin.groupby("admin_level").size().to_dict()
    summary["admin_levels"] = {str(k): int(v) for k, v in levels.items()}
    print(f"  admin polygons by level: {summary['admin_levels']}")
    for level in sorted(levels, key=lambda v: int(v) if str(v).isdigit() else 99):
        print(f"  level {level} examples: {admin[admin.admin_level == level]['name'].dropna().head(6).tolist()}")
    admin[["osm_id", "admin_level", "name", "geometry"]].to_file(OUT / "kmc_admin.geojson", driver="GeoJSON")

    bld = mp[mp["building"].notna()]
    areas = bld.to_crs(UTM).area
    summary["buildings"] = {"count": len(bld), "median_footprint_m2": round(float(areas.median()), 1),
                            "total_footprint_km2": round(float(areas.sum()) / 1e6, 2),
                            "share_of_kmc_pct": round(float(areas.sum()) / 1e6 / area_km2 * 100, 1),
                            "by_type": bld.groupby("building").size().sort_values(ascending=False).head(10).to_dict()}
    print(f"  buildings: {summary['buildings']}")

    land = mp[mp["landuse"].notna()]
    by_use = land.to_crs(UTM).area.groupby(land["landuse"]).sum().sort_values(ascending=False) / 1e6
    summary["landuse_km2"] = {k: round(float(v), 2) for k, v in by_use.head(12).items()}
    print(f"  land use km²: {summary['landuse_km2']}")

    print("\n== Lines: roads and waterways")
    lines = read("lines", poly, ["osm_id", "name", "highway", "waterway"])
    roads = lines[lines["highway"].notna()]
    road_len = roads.to_crs(UTM).length
    by_type = road_len.groupby(roads["highway"]).sum().sort_values(ascending=False) / 1000
    summary["roads"] = {"segments": len(roads), "total_km": round(float(road_len.sum()) / 1000, 1),
                        "km_by_type": {k: round(float(v), 1) for k, v in by_type.head(12).items()}}
    print(f"  roads: {summary['roads']}")

    water = lines[lines["waterway"].isin(["river", "stream", "canal", "drain"])]
    water_len = water.to_crs(UTM).length
    named = (water_len.groupby(water["name"]).sum().sort_values(ascending=False) / 1000).head(12)
    summary["waterways"] = {"segments": len(water), "total_km": round(float(water_len.sum()) / 1000, 1),
                            "by_type": water.groupby("waterway").size().to_dict(),
                            "named_km": {k: round(float(v), 2) for k, v in named.items()}}
    print(f"  waterways: {summary['waterways']}")

    print("\n== Points: named places")
    pts = read("points", poly, ["osm_id", "name", "place"])
    places = pts[pts["place"].isin(PLACE_TYPES) & pts["name"].notna()]
    summary["places"] = {"count": len(places), "by_type": places.groupby("place").size().to_dict(),
                         "examples": places["name"].head(15).tolist()}
    summary["named_points"] = int(pts["name"].notna().sum())
    print(f"  places: {summary['places']}")
    print(f"  all named points (landmarks, shops, ...): {summary['named_points']}")

    (OUT / "kmc_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), "utf-8")
    print(f"\nSaved {OUT / 'kmc_summary.json'}")


if __name__ == "__main__":
    main()
