import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pyogrio
from shapely.geometry.base import BaseGeometry

from pipeline import settings

log = logging.getLogger(__name__)

SNAPSHOT_FILE = "kmc.gpkg"
META_FILE = "meta.json"
LAYERS = ("boundary", "admin", "buildings", "roads", "waterways", "power", "places", "landmarks", "parks")
PLACE_TYPES = {"suburb", "quarter", "neighbourhood", "locality", "hamlet", "village"}
LANDMARK_AMENITIES = {"hospital", "school", "college", "university", "place_of_worship", "police", "townhall",
                      "bus_station", "marketplace", "library", "fire_station"}


def tag(other_tags, key: str) -> str | None:
    """Read one key from GDAL's other_tags text ("k"=>"v","k2"=>"v2")."""
    if not isinstance(other_tags, str):
        return None
    m = re.search(rf'"{re.escape(key)}"=>"((?:[^"\\]|\\.)*)"', other_tags)
    return m.group(1) if m else None


def kmc_boundary() -> gpd.GeoDataFrame:
    """KMC boundary polygon from Nominatim by relation id (cached by OSMnx)."""
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(settings.CACHE_DIR / "osmnx")
    gdf = ox.geocode_to_gdf(f"R{settings.KMC_RELATION}", by_osmid=True)[["geometry"]]
    km2 = gdf.to_crs(settings.UTM).area.sum() / 1e6
    if km2 < settings.KMC_MIN_AREA_KM2:
        raise ValueError(f"KMC boundary is only {km2:.1f} km², expected at least {settings.KMC_MIN_AREA_KM2}")
    return gdf


def _read(layer: str, poly: BaseGeometry, columns: list[str]) -> gpd.GeoDataFrame:
    log.info("reading %s from %s", layer, settings.PBF.name)
    return pyogrio.read_dataframe(settings.PBF, layer=layer, bbox=poly.bounds, columns=columns)


def _inside(gdf: gpd.GeoDataFrame, poly: BaseGeometry) -> gpd.GeoDataFrame:
    return gdf[gdf.geometry.representative_point().within(poly)]


def extract(out_root: Path = settings.RAW_DIR) -> Path:
    """Clip the Nepal extract to KMC and save the layers to a dated snapshot folder."""
    if not settings.PBF.exists():
        raise FileNotFoundError(f"{settings.PBF} not found; download https://download.geofabrik.de/asia/"
                                "nepal-latest.osm.pbf into data/cache/osm/")
    boundary = kmc_boundary()
    poly = boundary.geometry.iloc[0]

    mp = _read("multipolygons", poly, ["osm_id", "osm_way_id", "name", "admin_level", "boundary", "building",
                                       "amenity", "leisure", "other_tags"])
    mp = mp[mp.geometry.notna()]
    admin = mp[(mp["boundary"] == "administrative") & mp.geometry.intersects(poly)][["osm_id", "admin_level", "name",
                                                                                     "geometry"]]
    buildings = _inside(mp[mp["building"].notna()], poly)
    buildings = buildings.assign(osm_id=buildings["osm_way_id"].fillna(buildings["osm_id"]))
    buildings = buildings[["osm_id", "building", "amenity", "geometry"]]
    parks = _inside(mp[(mp["leisure"] == "park") & mp["name"].notna()], poly)
    parks = parks.assign(name_en=parks["other_tags"].map(lambda t: tag(t, "name:en")))
    parks = parks[["osm_id", "name", "name_en", "geometry"]]

    lines = _read("lines", poly, ["osm_id", "name", "highway", "waterway", "other_tags"])
    lines = lines[lines.geometry.notna() & lines.geometry.intersects(poly)]
    lines = lines.assign(name_en=lines["other_tags"].map(lambda t: tag(t, "name:en")),
                         power=lines["other_tags"].map(lambda t: tag(t, "power")))
    roads = lines[lines["highway"].notna()][["osm_id", "name", "name_en", "highway", "geometry"]]
    waterways = lines[lines["waterway"].isin(["river", "stream", "canal", "drain"])][
        ["osm_id", "name", "name_en", "waterway", "geometry"]]
    power = lines[lines["power"].isin(["line", "minor_line"])][["osm_id", "name", "power", "geometry"]]

    pts = _inside(_read("points", poly, ["osm_id", "name", "place", "other_tags"]), poly)
    pts = pts[pts["name"].notna()]
    pts = pts.assign(name_en=pts["other_tags"].map(lambda t: tag(t, "name:en")),
                     amenity=pts["other_tags"].map(lambda t: tag(t, "amenity")))
    places = pts[pts["place"].isin(PLACE_TYPES)][["osm_id", "name", "name_en", "place", "geometry"]]
    landmarks = pts[pts["amenity"].isin(LANDMARK_AMENITIES) & pts["name_en"].notna()][
        ["osm_id", "name", "name_en", "amenity", "geometry"]]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = out_root / f"kmc-{stamp}"
    path.mkdir(parents=True, exist_ok=True)
    gpkg = path / SNAPSHOT_FILE
    gpkg.unlink(missing_ok=True)
    frames = dict(boundary=boundary, admin=admin, buildings=buildings, roads=roads, waterways=waterways,
                  power=power, places=places, landmarks=landmarks, parks=parks)
    for name, gdf in frames.items():
        gpd.GeoDataFrame(gdf, geometry="geometry", crs=settings.WGS84).to_file(gpkg, layer=name, driver="GPKG")
    meta = {"source": settings.PBF.name,
            "source_modified": datetime.fromtimestamp(settings.PBF.stat().st_mtime, timezone.utc).isoformat(),
            "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "counts": {k: len(v) for k, v in frames.items()}}
    (path / META_FILE).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return path


def load_snapshot(path: Path) -> dict[str, gpd.GeoDataFrame]:
    """Read every layer of a saved snapshot."""
    gpkg = Path(path) / SNAPSHOT_FILE
    if not gpkg.exists():
        raise FileNotFoundError(f"snapshot {gpkg} not found")
    return {name: gpd.read_file(gpkg, layer=name) for name in LAYERS}


def latest_snapshot(root: Path = settings.RAW_DIR) -> Path | None:
    found = sorted(p for p in root.glob("kmc-*") if (p / SNAPSHOT_FILE).exists())
    return found[-1] if found else None
