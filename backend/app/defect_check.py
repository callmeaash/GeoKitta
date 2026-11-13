"""Runs the city-wide scan and compares it with the pipeline's planted defects: python -m app.defect_check."""
import json
import sys
import time

from sqlalchemy import text

from app.config import ROOT
from app.db import engine
from app.scan import find_issues

MANIFEST = ROOT / "data" / "generated" / "defects.json"
OUT = ROOT / "data" / "evaluation" / "validation.json"
GEOMETRY_TYPES = {"overlap": "overlap", "overlap_cross": "overlap", "sliver": "sliver",
                  "area_mismatch": "area_mismatch"}


def compare(planted: list[dict], issues: list[dict], pin_of: dict[int, str]) -> dict:
    """Which planted defects the scan found, and what else it found."""
    found_keys = set()
    for i in issues:
        pins = frozenset(p for p in (pin_of.get(i["parcel_id"]), pin_of.get(i.get("other"))) if p)
        found_keys.add((i["issue_type"], pins))
    by_type: dict[str, dict] = {}
    matched = set()
    for d in planted:
        kind = GEOMETRY_TYPES[d["type"]]
        key = (kind, frozenset(d["pins"]))
        hit = key in found_keys
        row = by_type.setdefault(d["type"], {"planted": 0, "found": 0, "missed": []})
        row["planted"] += 1
        row["found"] += hit
        if hit:
            matched.add(key)
        else:
            row["missed"].append(d["pins"])
    # a shifted parcel also overlaps the other neighbours listed in the manifest: side effects, not new findings
    side = {("overlap", frozenset((p, n))) for d in planted for p in d["pins"] for n in d.get("also_overlaps", [])}
    extra: dict[str, int] = {}
    for key in found_keys - matched - side:
        extra[key[0]] = extra.get(key[0], 0) + 1
    return {"planted": by_type, "side_effects_of_planted": len((found_keys - matched) & side),
            "other_findings": extra}


def main() -> int:
    planted = [d for d in json.loads(MANIFEST.read_text("utf-8")) if d["type"] in GEOMETRY_TYPES]
    t0 = time.perf_counter()
    with engine.connect() as conn:
        issues, stats = find_issues(conn)
        pin_of = dict(conn.execute(text("SELECT id, pin FROM parcels")).all())
    result = compare(planted, issues, pin_of)
    result["scan"] = {**stats, "issues": len(issues), "seconds": round(time.perf_counter() - t0)}
    for kind, row in result["planted"].items():
        missed = f"  missed {row['missed']}" if row["missed"] else ""
        print(f"{kind:>14}: found {row['found']}/{row['planted']}{missed}")
    print(f"overlaps with other neighbours of a shifted parcel: {result['side_effects_of_planted']}")
    print(f"other findings (not planted): {result['other_findings'] or 'none'}")
    print(f"scanned {stats['parcels']:,} parcels, {stats['pairs_compared']:,} pairs in {result['scan']['seconds']} s")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), "utf-8")
    print(f"wrote {OUT}")
    return 0 if all(not r["missed"] for r in result["planted"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
