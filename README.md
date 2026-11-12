# GeoKitta

Cadastral (land parcel) information system for a pilot area of Kathmandu Metropolitan City. BCA 6th-semester project.

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

## Test

```
cd backend
..\.venv\Scripts\python -m pytest

cd frontend
npm test
```
