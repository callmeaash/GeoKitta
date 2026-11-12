import argparse
import csv
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine

from pipeline import settings
from pipeline.extract import extract, latest_snapshot, load_snapshot
from pipeline.generate import generate
from pipeline.load import LoadError, existing_parcels, run_load
from pipeline.schema import SchemaError, check_schema
from pipeline.transform import transform
from pipeline.validate import validate

log = logging.getLogger("pipeline")


def parse_args(argv):
    parser = argparse.ArgumentParser(prog="python -m pipeline",
                                     description="Load OSM data and synthetic parcels for KMC into the database.")
    parser.add_argument("--wards", help="comma-separated ward numbers, e.g. 4,5 (default: all of KMC)")
    parser.add_argument("--snapshot", help="snapshot folder to use (default: the latest in data/raw)")
    parser.add_argument("--extract", action="store_true", help="re-clip the Nepal extract even if a snapshot exists")
    parser.add_argument("--seed", type=int, default=settings.DEFAULT_SEED)
    parser.add_argument("--reset", action="store_true", help="replace existing synthetic data")
    parser.add_argument("--dry-run", action="store_true", help="generate and validate without writing to the database")
    args = parser.parse_args(argv)
    try:
        args.wards = sorted({int(w) for w in args.wards.split(",")}) if args.wards else None
    except ValueError:
        parser.error("--wards must be numbers, e.g. 4,5")
    return args


def write_outputs(gen, prep, out: Path) -> None:
    """Answer key for planted defects, sample survey files and a run summary."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "defects.json").write_text(json.dumps(gen.defects, indent=2, ensure_ascii=False), "utf-8")
    survey = out / "survey"
    survey.mkdir(exist_ok=True)
    for old in survey.glob("*.csv"):  # files from an earlier run would not match this data
        old.unlink()
    for name, coords in gen.survey.items():
        with open(survey / name, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["point", "easting", "northing"])
            w.writerows((n, f"{x:.2f}", f"{y:.2f}") for n, (x, y) in enumerate(coords, start=1))
    summary = {"stats": gen.stats, "notes": prep.notes, "crs_of_survey_files": settings.UTM}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), "utf-8")


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("pyogrio").setLevel(logging.WARNING)
    t0 = time.perf_counter()

    engine = None
    if not args.dry_run:
        try:
            engine = create_engine(settings.database_url())
            check_schema(engine)
        except (RuntimeError, SchemaError) as exc:
            log.error("%s", exc)
            return 1
        if not args.reset and (n := existing_parcels(engine)):
            log.error("parcels already has %d rows; rerun with --reset to replace the synthetic data", n)
            return 1

    snapshot = Path(args.snapshot) if args.snapshot else latest_snapshot()
    if args.extract or snapshot is None:
        log.info("clipping %s to KMC (takes a few minutes)", settings.PBF.name)
        snapshot = extract()
    log.info("snapshot %s", snapshot)
    prep = transform(load_snapshot(snapshot), args.wards)
    for note in prep.notes:
        log.info("note: %s", note)
    log.info("area %.2f km²: %d buildings, %d roads, %d waterways, %d features, %d places",
             prep.area.area / 1e6, len(prep.buildings), len(prep.roads), len(prep.waterways),
             len(prep.features), len(prep.places))

    gen = generate(prep, args.seed)
    log.info("generated: %s", gen.stats)

    report = validate(gen)
    for w in report.warnings:
        log.warning(w)
    out = settings.GENERATED_DIR
    write_outputs(gen, prep, out)
    log.info("wrote defects.json, survey/ and summary.json to %s", out)
    if not report.ok:
        for e in report.errors:
            log.error(e)
        log.error("validation failed, nothing was loaded")
        return 1
    if args.dry_run:
        log.info("dry run: validation passed, database not changed (%.0f s)", time.perf_counter() - t0)
        return 0

    details = {"snapshot": str(snapshot), "wards": args.wards or "all", "seed": args.seed,
               "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        counts = run_load(engine, prep, gen, args.reset, details)
    except LoadError as exc:
        log.error("%s", exc)
        return 1
    log.info("loaded: %s (%.0f s)", counts, time.perf_counter() - t0)

    # the backend owns the spatial index; rebuild it so lookups see the new parcels
    log.info("building the linear quadtree")
    backend = settings.PROJECT_DIR / "backend"
    if subprocess.run([sys.executable, "-m", "app.spatial.reindex"], cwd=backend).returncode != 0:
        log.error("quadtree build failed; run it again with: cd backend; python -m app.spatial.reindex")
        return 1
    log.info("done (%.0f s)", time.perf_counter() - t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
