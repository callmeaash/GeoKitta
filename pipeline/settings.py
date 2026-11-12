import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
RAW_DIR = DATA_DIR / "raw"
GENERATED_DIR = DATA_DIR / "generated"
PBF = CACHE_DIR / "osm" / "nepal-latest.osm.pbf"  # Geofabrik extract, downloaded once

load_dotenv(PROJECT_DIR / ".env")

WGS84 = "EPSG:4326"
UTM = "EPSG:32645"  # UTM zone 45N, metres

# Area: Kathmandu Metropolitan City, by OSM relation id (place names can match the wrong object)
KMC_RELATION = 12394677
KMC_MIN_AREA_KM2 = 40
WARD_COUNT = 32
GAP_WARDS = (24, 25)  # missing from OSM; filled from the gap between the other wards (approximate split)

# Synthetic identity codes (fictional, used consistently across the data)
DISTRICT_CODE = 27
MUNICIPALITY_CODE = 2701
SHEET_SCALE_DIGIT = 2  # map sheet geocode = district(2) + scale(1) + ward(2) + sheet(3) + part(1)
SHEET_SIZE_M = 500

DEFAULT_SEED = 20261112
PIPELINE_USERNAME = "pipeline"

# Roads that form city blocks, with half the corridor width in metres
ROAD_HALF_WIDTH_M = {
    "trunk": 8, "primary": 7, "secondary": 6, "tertiary": 5, "unclassified": 4,
    "residential": 3, "living_street": 2.5, "trunk_link": 4, "primary_link": 4,
    "secondary_link": 4, "tertiary_link": 3,
}
HIGHWAY_TYPES = {"trunk", "primary", "trunk_link", "primary_link"}  # stored as feature_type 'highway'

# Estimated widths in metres (OSM rivers are centre lines); setbacks are measured from the bank
WATERWAY_WIDTH_M = {"river": 15, "stream": 5, "canal": 4, "drain": 2}
NAMED_RIVER_WIDTH_M = {"bagmati": 40, "bishnumati": 25, "manohara": 25}

# Parcel generation
MIN_PARCEL_M2 = 25
MAX_PARCEL_M2 = 6000          # bigger cells are split
OPEN_PLOT_TARGET_M2 = 1200    # target size when splitting land with no buildings
SPLIT_SHARE = 0.01            # share of parcels created by a past split (kitta kaat)
BOUNDARY_UPDATE_SHARE = 0.01  # share of parcels with an older boundary in history
TRANSFER_SHARE = 0.25         # share of parcels with a past ownership transfer
ROKKA_SHARE = 0.01
JOINT_SHARE = 0.20            # parcels with two owners (1/2 each)
TRIPLE_SHARE = 0.03           # parcels with three owners (1/3 each)
NEAR_DUPLICATE_OWNERS = 200   # planted spelling variants for the duplicate-owner warning

# Planted defects (answer key in data/generated/defects.json)
DEFECT_OVERLAPS = 12
DEFECT_SLIVERS = 10
DEFECT_AREA_MISMATCH = 25


def database_url() -> str:
    """Database URL the pipeline writes to."""
    url = os.getenv("PIPELINE_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env and fill it in.")
    return url
