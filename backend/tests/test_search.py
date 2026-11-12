import importlib.util
import json
import random
import string

import pytest

from app.config import ROOT
from app.search.bktree import BKTree
from app.search.index import NameIndex
from app.search.levenshtein import levenshtein, table
from app.search.text import fold, max_edits, normalize, words


@pytest.mark.parametrize("a, b, d", [
    ("shrestha", "shreshtha", 1), ("ram", "raam", 1), ("baluwatar", "baluwatr", 1), ("laxmi", "lakshmi", 3),
    ("ram", "shyam", 3), ("kitten", "sitting", 3), ("same", "same", 0), ("", "", 0), ("", "abc", 3), ("abc", "", 3),
])
def test_known_distances(a, b, d):
    assert levenshtein(a, b) == d
    assert levenshtein(b, a) == d


def test_table_matches_and_shows_the_worked_example():
    t = table("ram", "raam")
    assert t[-1][-1] == 1
    assert t[0] == [0, 1, 2, 3, 4] and [row[0] for row in t] == [0, 1, 2, 3]


def test_random_words_are_a_metric_and_the_limit_is_safe():
    rng = random.Random(1)
    rand = lambda: "".join(rng.choice("abcde") for _ in range(rng.randint(0, 9)))  # noqa: E731
    for _ in range(400):
        a, b, c = rand(), rand(), rand()
        d = levenshtein(a, b)
        assert d == table(a, b)[-1][-1]
        assert levenshtein(a, c) <= d + levenshtein(b, c)  # triangle inequality, which the BK-tree relies on
        for limit in range(4):
            assert levenshtein(a, b, limit) == (d if d <= limit else limit + 1)


def test_bktree_finds_exactly_what_a_full_scan_finds():
    rng = random.Random(2)
    vocab = sorted({"".join(rng.choice(string.ascii_lowercase[:8]) for _ in range(rng.randint(3, 9)))
                    for _ in range(600)})
    tree = BKTree(vocab)
    assert len(tree) == len(vocab)
    for _ in range(100):
        q = "".join(rng.choice(string.ascii_lowercase[:8]) for _ in range(rng.randint(3, 9)))
        k = rng.randint(0, 3)
        expected = sorted(((w, levenshtein(q, w)) for w in vocab if levenshtein(q, w) <= k), key=lambda x: (x[1], x[0]))
        assert tree.search(q, k) == expected
        assert tree.comparisons <= len(vocab)


def test_normalize_and_fold():
    assert normalize("  Ratna-Park,  KATHMANDU ") == "ratna park kathmandu"
    assert fold("lakshmi") == fold("laxmi")
    assert fold("vishnu") == fold("bishnu")
    assert fold("pooja") == fold("puja")
    assert fold("deepak") == fold("dipak")
    assert fold("rajbhandary") == fold("rajbhandari")
    assert fold("neupaney") == fold("neupane")
    assert words("Ram Bahadur") == ["ram", "bahadur"]
    assert [max_edits(w) for w in ("ab", "ram", "baluwatar", "bishnumatiriver")] == [0, 1, 2, 3]


NAMES = [(1, "Ram Bahadur Shrestha"), (2, "Sita Kumari Maharjan"), (3, "Laxmi Prasad Poudel"),
         (4, "Ram Shrestha"), (5, "Hari Bahadur Thapa"), (6, "Baluwatar"), (7, "Thamel Marg")]


def test_name_index_needs_every_word_and_ranks_by_edits():
    idx = NameIndex(NAMES)
    hits = idx.search("ram shreshtha")
    assert [h.id for h in hits] == [4, 1]  # both match; the shorter name first on equal edits
    assert hits[0].score == 1 and hits[0].distance == 1
    assert idx.search("ram thapa") == []  # no name has both words


def test_name_index_prefix_and_spelling_variants():
    idx = NameIndex(NAMES)
    assert [h.id for h in idx.search("baluw")] == [6]  # unfinished word
    assert idx.search("baluw", prefix=False) == []
    assert [h.id for h in idx.search("Lakshmi Paudel")] == [3]
    idx.add(8, "Vishnu Neupaney")
    assert [h.id for h in idx.search("bishnu neupane")] == [8]
    idx.remove(8)
    assert idx.search("bishnu neupane") == []


def _variants() -> dict[str, str]:
    """The spelling variants the pipeline plants (pipeline/names.py), loaded by path."""
    spec = importlib.util.spec_from_file_location("names", ROOT / "pipeline" / "names.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.VARIANTS


def test_every_planted_variant_finds_its_original():
    VARIANTS = _variants()
    idx = NameIndex([(i, f"Test {orig}") for i, orig in enumerate(VARIANTS)])
    for i, (orig, variant) in enumerate(VARIANTS.items()):
        assert i in [h.id for h in idx.search(f"test {variant}", prefix=False)], (orig, variant)


def test_planted_duplicate_owners_are_found_among_all_owners():
    """Acceptance test: each planted near-duplicate finds its original among the real owner records."""
    key = ROOT / "data" / "generated" / "defects.json"
    if not key.exists():
        pytest.skip("no answer key; run the pipeline")
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    from app.db import engine
    try:
        with engine.connect() as c:
            rows = c.execute(text("SELECT id, full_name, lin FROM owners")).all()
    except OperationalError:
        pytest.skip("database not reachable")
    pairs = [d for d in json.loads(key.read_text("utf-8")) if d["type"] == "duplicate_owner"]
    by_lin = {r[2]: r[0] for r in rows}
    if not pairs or not all(p["original_lin"] in by_lin for p in pairs):
        pytest.skip("answer key does not match the loaded data")
    idx = NameIndex([(r[0], r[1]) for r in rows])
    for p in pairs:
        hits = idx.search(p["duplicate"], limit=200, prefix=False)
        assert by_lin[p["original_lin"]] in [h.id for h in hits], p
