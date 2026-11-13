from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api import auth, issues, officer, parcels, public, records
from app.config import settings



@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        public.features()  # load roads, rivers and place names once at startup, not on the first click
        public.gazetteer()
        officer.owners_index()  # about 4 s for 176k owners
    except Exception:  # noqa: BLE001 - the API still starts without a database; requests will report it
        pass
    yield


app = FastAPI(
    lifespan=lifespan,
    title="GeoKitta API",
    description="Cadastral information system for Kathmandu. Demonstration with synthetic data.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)  # parcel outlines compress well

app.include_router(public.router)
app.include_router(auth.router)
app.include_router(officer.router)
app.include_router(parcels.router)
app.include_router(records.router)
app.include_router(issues.router)


@app.get("/api/health", tags=["system"])
def health() -> dict:
    """Check that the API is running."""
    return {"status": "ok", "app": settings.app_name}
