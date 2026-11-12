"""Render parcels from the database over OSM buildings and roads, for a visual check of the pipeline output."""
import argparse
import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box
from sqlalchemy import create_engine

from pipeline import settings
from pipeline.extract import latest_snapshot

AREAS = {  # name: (lon, lat)
    "thamel": (85.3105, 27.7153),
    "asan": (85.3112, 27.7066),
    "thapathali": (85.3205, 27.6925),
}
OUT = settings.DATA_DIR / "explore" / "render"


def svg_path(geom, x0, y1) -> str:
    """SVG path data for a (multi)polygon or (multi)line in UTM metres, y flipped."""
    parts = getattr(geom, "geoms", [geom])
    d = []
    for g in parts:
        rings = [g.exterior, *g.interiors] if g.geom_type == "Polygon" else [g]
        for r in rings:
            pts = " ".join(f"{x - x0:.1f},{y1 - y:.1f}" for x, y in r.coords)
            d.append(f"M{pts}{'Z' if g.geom_type == 'Polygon' else ''}")
    return " ".join(d)


def render(name: str, lon: float, lat: float, half: float, engine, snap_path: Path, defect_pins: set) -> Path:
    centre = gpd.GeoSeries.from_xy([lon], [lat], crs=settings.WGS84).to_crs(settings.UTM).iloc[0]
    view = box(centre.x - half, centre.y - half, centre.x + half, centre.y + half)
    bbox_wgs = gpd.GeoSeries([view], crs=settings.UTM).to_crs(settings.WGS84).total_bounds
    env = "ST_MakeEnvelope(%f, %f, %f, %f, 4326)" % tuple(bbox_wgs)
    parcels = gpd.read_postgis(f"SELECT pin, status, land_use, boundary FROM parcels WHERE boundary && {env}",
                               engine, geom_col="boundary").to_crs(settings.UTM)
    features = gpd.read_postgis(f"SELECT feature_type, geom FROM features WHERE geom && {env}", engine,
                                geom_col="geom").to_crs(settings.UTM)
    buildings = gpd.read_file(snap_path / "kmc.gpkg", layer="buildings", bbox=tuple(bbox_wgs)).to_crs(settings.UTM)
    x0, y1, size = view.bounds[0], view.bounds[3], 2 * half

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="900" height="900">',
           f'<rect width="{size}" height="{size}" fill="#F4F4F2"/>']
    for _, f in features.iterrows():
        colour = "#A5CFF5" if f.feature_type in ("river", "stream") else "#FFFFFF"
        width = 10 if f.feature_type in ("river", "stream") else 5
        out.append(f'<path d="{svg_path(f.geom, x0, y1)}" fill="none" stroke="{colour}" stroke-width="{width}"/>')
    for g in buildings.geometry:
        out.append(f'<path d="{svg_path(g, x0, y1)}" fill="#CBD5E1" stroke="none"/>')
    for _, p in parcels[parcels.status == "active"].iterrows():
        stroke, w = ("#DC2626", 1.2) if p.pin in defect_pins else ("#1E3A8A", 0.5)
        out.append(f'<path d="{svg_path(p.boundary, x0, y1)}" fill="none" stroke="{stroke}" stroke-width="{w}"/>')
    out.append(f'<text x="8" y="22" font-family="Arial" font-size="16" fill="#0F172A">{name}: '
               f'{len(parcels)} parcels, {len(buildings)} buildings, {size:.0f} m wide</text></svg>')
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.svg"
    path.write_text("\n".join(out), encoding="utf-8")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--half", type=float, default=200, help="half the view width in metres")
    args = ap.parse_args()
    engine = create_engine(settings.database_url())
    defects = json.loads((settings.GENERATED_DIR / "defects.json").read_text("utf-8"))
    pins = {p for d in defects for p in d.get("pins", [])}
    for name, (lon, lat) in AREAS.items():
        print(render(name, lon, lat, args.half, engine, latest_snapshot(), pins))


if __name__ == "__main__":
    main()
