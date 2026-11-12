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
copy .env.example .env          # then set your PostgreSQL password and a JWT_SECRET in .env

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

The public map viewer opens at http://localhost:5173. Zoom in to see parcel outlines, or click anywhere to identify a parcel. The tools are Details, Select (rectangle or line), Buffer (point, line, or road/river with its setback rule), Measure and Layers. Links such as `#map=18/27.70660/85.31120&parcel=123` open a view directly. Base map tiles © OpenStreetMap contributors.

The search box finds places by name even when misspelled ("baluwatr" → Baluwatar), and parcels by PIN, kitta number or ward/kitta (`4/123`).

## Officer accounts

Officers sign in at http://localhost:5173/officer/login. Accounts are created from the command line, never through the web:

```
cd backend
..\.venv\Scripts\python -m app.cli create-officer sita.maharjan --name "Sita Maharjan" --admin
..\.venv\Scripts\python -m app.cli set-password sita.maharjan
..\.venv\Scripts\python -m app.cli disable-officer sita.maharjan
```

Passwords are stored as argon2 hashes. A signed-in officer gets an HttpOnly session cookie (8 hours). Signed in, the map shows each parcel's owners, shares and ownership history. The workspace has a dashboard, owner search (tolerant of spelling variants such as Shreshtha/Shrestha and Lakshmi/Laxmi), and owner registration with a duplicate check.

### Parcel workflows

Officers register parcels, update boundaries and split parcels (kitta kaat) from survey coordinates: typed, pasted, or uploaded as CSV (`point,easting,northing`) or GeoJSON. Boundaries are never drawn with the mouse. Every save is validated: a valid polygon, no overlap with neighbours (linear quadtree plus an exact test), area against the registered area, and a sliver check. Each save is recorded as a case with history, lineage, ownership and an audit log entry. The pipeline writes sample survey files to `data\generated\survey\` for all three workflows.

To validate every parcel and record problems for review (the pipeline also runs this):

```
cd backend
..\.venv\Scripts\python -m app.scan
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
