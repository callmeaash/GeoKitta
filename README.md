# GeoKitta

Cadastral (land parcel) information system covering all 32 wards of Kathmandu Metropolitan City. BCA 6th-semester project.

The public can search parcels, view them on a map and check road and river setbacks. Land officers register parcels from survey coordinates, update boundaries, split parcels (kitta kaat), record ownership transfers and review geometry issues. The spatial index is a hand-written **linear quadtree** stored in PostgreSQL; name search uses a hand-written **Levenshtein** fuzzy match.

> All parcel, owner and transaction data is synthetic. This is an academic demonstration, not an official land record system.

## Stack

| Part | Technology |
|---|---|
| Backend | Python, FastAPI, SQLAlchemy, GeoAlchemy2, Alembic |
| Database | PostgreSQL 18 + PostGIS 3.6 |
| Frontend | Vue 3 (JavaScript), Vite, Leaflet |
| Data | OpenStreetMap via OSMnx, synthetic parcels generated with Shapely |
| Tests | pytest, Vitest |

## Folders

```
backend/    FastAPI app (app/) and tests (tests/)
pipeline/   OSM download and synthetic data generator (python -m pipeline)
frontend/   Vue app; brand files in public/brand/
scripts/    exploration scripts
data/       downloaded and generated data (not committed)
```

## Setup

Requirements: Python 3.13, Node.js 24, PostgreSQL 18 with PostGIS.

```
# 1. Environment
copy .env.example .env          # then set your PostgreSQL password in .env

# 2. Backend
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r backend\requirements.txt

# 3. Frontend
cd frontend
npm install
```

## Run

```
# Backend (http://127.0.0.1:8000, API docs at /docs)
cd backend
..\.venv\Scripts\python -m uvicorn app.main:app --reload

# Frontend (http://localhost:5173), in a second terminal
cd frontend
npm run dev
```

## Data

The database schema is created by the backend's migrations; the pipeline fills it with OpenStreetMap data for Kathmandu Metropolitan City and synthetic parcels, owners and history.

```
# 1. Create the tables (once)
cd backend
..\.venv\Scripts\python -m alembic upgrade head
cd ..

# 2. OpenStreetMap data: download the Geofabrik Nepal extract (~400 MB) once
#    https://download.geofabrik.de/asia/nepal-latest.osm.pbf  ->  data\cache\osm\nepal-latest.osm.pbf
.venv\Scripts\python -m pip install -r pipeline\requirements.txt

# 3. Generate and load (all of KMC, about 15 minutes); --wards 4,5 for a quick partial run
.venv\Scripts\python -m pipeline --reset
.venv\Scripts\python -m pipeline --wards 1 --dry-run   # generate and validate only
```

The first run clips the extract to KMC and saves a snapshot in `data\raw\`; later runs reuse it. After loading, the pipeline builds the linear quadtree (`parcel_quadkeys`). The answer key for the planted data defects and sample survey coordinate files are written to `data\generated\`. OpenStreetMap data © OpenStreetMap contributors, ODbL.

## Linear quadtree

The spatial index lives in `backend/app/spatial/`. Each parcel is stored under the 1-4 quadrants at its own size level, so a click reads about a dozen index rows instead of every parcel.

```
cd backend
..\.venv\Scripts\python -m app.spatial.reindex    # rebuild the index for all active parcels
..\.venv\Scripts\python -m app.spatial.evaluate   # quadtree vs brute-force loop at 200 / 10,000 / 50,000 / all parcels
```

## Test

```
.venv\Scripts\python -m pytest          # pipeline tests (from the project root)

cd backend
..\.venv\Scripts\python -m pytest

cd frontend
npm test
```
