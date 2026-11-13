"""Fuzzy search quality on the generated data: python -m app.search.evaluate (from backend/)."""
import json
import random
import statistics
import string
import sys
import time

from sqlalchemy import text

from app.api.officer import owners_index, similar_owners
from app.config import ROOT
from app.db import SessionLocal
from app.schemas import SimilarRequest
from app.search.gazetteer import Gazetteer
from app.search.levenshtein import levenshtein
from app.search.text import words

MANIFEST = ROOT / "data" / "generated" / "defects.json"
OUT = ROOT / "data" / "evaluation" / "search.json"
KNOWN = [("shrestha", "shreshtha", 1), ("ram", "raam", 1), ("baluwatar", "baluwatr", 1), ("laxmi", "lakshmi", 3),
         ("ram", "shyam", 3), ("kitten", "sitting", 3), ("same", "same", 0), ("", "", 0), ("", "abc", 3)]
NEGATIVE_SAMPLE = 500  # distinct owners checked for false duplicate warnings
PLACE_SAMPLE = 300


def typo(word: str, rng: random.Random) -> str:
    """One random edit (replace, insert or delete a letter) away from word."""
    i = rng.randrange(1, len(word))  # keep the first letter, as people usually do
    kind = rng.choice("rid")
    letter = rng.choice([c for c in string.ascii_lowercase if c != word[i]])
    if kind == "r":
        return word[:i] + letter + word[i + 1:]
    if kind == "i":
        return word[:i] + letter + word[i:]
    return word[:i] + word[i + 1:]


def owner_search(db, pairs, ids_by_lin) -> dict:
    """Each planted near-duplicate name is searched; where does the original owner rank?"""
    idx = owners_index()
    found, best, same_name, times = 0, 0, [], []
    for p in pairs:
        t0 = time.perf_counter()
        hits = idx.search(p["duplicate"], limit=200, prefix=False)
        times.append((time.perf_counter() - t0) * 1000)
        hits = [h for h in hits if h.id != ids_by_lin[p["duplicate_lin"]]]  # the duplicate's own record
        target = next((h for h in hits if h.id == ids_by_lin[p["original_lin"]]), None)
        found += target is not None
        best += target is not None and target.score == min(h.score for h in hits)
        same_name.append(sum(h.name == p["original"] for h in hits))
    # many owners share a name (few distinct name words), so the original is one of several equally close records
    return {"owners": len(idx), "distinct_words": len(idx.postings), "queries": len(pairs), "found": found,
            "among_closest": best, "owners_with_original_name_median": statistics.median(same_name),
            "median_ms": round(statistics.median(times), 2)}


def duplicate_warning(db, pairs, ids_by_lin, rng) -> dict:
    """Planted duplicates must be flagged against their original; distinct owners must not be flagged."""
    rows = {r[0]: r for r in db.execute(text(
        "SELECT id, full_name, owner_type, date_of_birth, district_code, lin FROM owners"))}
    flagged = 0
    for p in pairs:
        me = rows[ids_by_lin[p["duplicate_lin"]]]
        similar = similar_owners(db, SimilarRequest(owner_type=me[2], full_name=me[1], date_of_birth=me[3],
                                                    district_code=me[4]), limit=50)
        flagged += any(s.likely_duplicate and s.lin == p["original_lin"] for s in similar)
    planted = {p["duplicate_lin"] for p in pairs} | {p["original_lin"] for p in pairs}
    pool = [r for r in rows.values() if r[2] == "individual" and r[5] not in planted]
    false_flags = 0
    for me in rng.sample(pool, NEGATIVE_SAMPLE):
        similar = similar_owners(db, SimilarRequest(owner_type=me[2], full_name=me[1], date_of_birth=me[3],
                                                    district_code=me[4]), limit=50)
        false_flags += any(s.likely_duplicate and s.id != me[0] for s in similar)
    return {"planted": len(pairs), "flagged": flagged, "distinct_checked": NEGATIVE_SAMPLE,
            "distinct_flagged": false_flags}


def place_search(db, rng) -> dict:
    """Misspelled place names must find the place; random strings must find nothing."""
    gaz = Gazetteer.load(db)
    candidates = [p for p in gaz.places.values() if any(len(w) >= 5 for w in words(p.name))]
    sample = rng.sample(candidates, min(PLACE_SAMPLE, len(candidates)))
    found, top1, compared, vocab, times = 0, 0, [], len(gaz.index.postings), []
    for p in sample:
        ws = words(p.name)
        k = max(range(len(ws)), key=lambda j: len(ws[j]))
        ws[k] = typo(ws[k], rng)
        t0 = time.perf_counter()
        results = gaz.search(" ".join(ws))
        times.append((time.perf_counter() - t0) * 1000)
        compared.append(gaz.index.stats["comparisons"] / vocab)
        names = [r[0].name.lower() for r in results]
        found += p.name.lower() in names
        top1 += bool(names) and names[0] == p.name.lower()
    noise_hits = 0
    for _ in range(PLACE_SAMPLE):
        junk = "".join(rng.choice("qxzjvkw") for _ in range(rng.randint(6, 10)))
        noise_hits += bool(gaz.search(junk))
    return {"places": len(gaz.places), "distinct_words": vocab, "misspelled_queries": len(sample),
            "found_top_6": found, "top_1": top1, "random_queries": PLACE_SAMPLE, "random_with_results": noise_hits,
            "bktree_compared_pct_median": round(100 * statistics.median(compared), 1),
            "median_ms": round(statistics.median(times), 2)}


def main() -> int:
    rng = random.Random(2026)
    report = {"levenshtein": [{"a": a, "b": b, "expected": d, "got": levenshtein(a, b)} for a, b, d in KNOWN]}
    pairs = [d for d in json.loads(MANIFEST.read_text("utf-8")) if d["type"] == "duplicate_owner"]
    with SessionLocal() as db:
        ids_by_lin = dict(db.execute(text("SELECT lin, id FROM owners")).all())
        report["owner_search"] = owner_search(db, pairs, ids_by_lin)
        print("owner search:", report["owner_search"], flush=True)
        report["duplicate_warning"] = duplicate_warning(db, pairs, ids_by_lin, rng)
        print("duplicate warning:", report["duplicate_warning"], flush=True)
        report["place_search"] = place_search(db, rng)
        print("place search:", report["place_search"], flush=True)
    ok = all(r["expected"] == r["got"] for r in report["levenshtein"])
    print(f"levenshtein known pairs: {'all correct' if ok else 'MISMATCH'}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str), "utf-8")
    print(f"wrote {OUT}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
