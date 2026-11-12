"""Fuzzy name index: a BK-tree over distinct name words, and for each word the records that contain it."""
from bisect import bisect_left
from dataclasses import dataclass, field

from app.search.bktree import BKTree
from app.search.levenshtein import levenshtein
from app.search.text import max_edits, normalize, words

PREFIX_COST = 0.5  # a word typed so far that starts a longer name word ranks just after an exact match


@dataclass
class Match:
    id: int
    name: str
    score: float  # summed edits over the query words (folded spelling)
    distance: int  # plain Levenshtein between the typed text and the name, for display
    matched: list[str] = field(default_factory=list)  # the name words that matched


class NameIndex:
    def __init__(self, entries: list[tuple[int, str]] = ()):
        self.names: dict[int, str] = {}
        self.postings: dict[str, set[int]] = {}  # folded word -> record ids
        self.tree = BKTree()
        self._sorted_words: list[str] = []
        self.stats: dict = {}
        for rid, name in entries:
            self.add(rid, name, sort=False)
        self._sorted_words = sorted(self.postings)

    def __len__(self) -> int:
        return len(self.names)

    def add(self, rid: int, name: str, sort: bool = True) -> None:
        self.names[rid] = name
        for w in set(words(name)):
            if w not in self.postings:
                self.postings[w] = set()
                self.tree.add(w)
                if sort:
                    self._sorted_words.insert(bisect_left(self._sorted_words, w), w)
            self.postings[w].add(rid)

    def remove(self, rid: int) -> None:
        name = self.names.pop(rid, None)
        for w in set(words(name or "")):
            self.postings.get(w, set()).discard(rid)  # the word stays in the tree; its posting list may be empty

    def _word_matches(self, word: str, prefix: bool) -> dict[str, float]:
        """Vocabulary words close to one query word: within its edit allowance, or starting with it."""
        found = {w: float(d) for w, d in self.tree.search(word, max_edits(word))}
        self.stats["comparisons"] = self.stats.get("comparisons", 0) + self.tree.comparisons
        if prefix and len(word) >= 2:
            i = bisect_left(self._sorted_words, word)
            while i < len(self._sorted_words) and self._sorted_words[i].startswith(word):
                w = self._sorted_words[i]
                found[w] = min(found.get(w, PREFIX_COST), PREFIX_COST)
                i += 1
        return found

    def search(self, query: str, limit: int = 10, prefix: bool = True) -> list[Match]:
        """Records matching every query word; fewest edits first. The last word may be unfinished (prefix)."""
        self.stats = {"vocabulary": len(self.postings), "comparisons": 0}
        qwords = words(query)
        if not qwords:
            return []
        best: dict[int, float] | None = None
        matched: dict[int, list[str]] = {}
        for n, qw in enumerate(qwords):
            close = self._word_matches(qw, prefix and n == len(qwords) - 1)
            scores: dict[int, float] = {}
            for w, cost in close.items():
                for rid in self.postings.get(w, ()):
                    if best is not None and rid not in best:
                        continue  # must also match the earlier words
                    if cost < scores.get(rid, 99):
                        scores[rid] = cost
                        matched.setdefault(rid, []).append(w)
            best = scores if best is None else {rid: best[rid] + s for rid, s in scores.items()}
            if not best:
                return []
        typed = normalize(query)
        ranked = sorted(best.items(), key=lambda x: (x[1], len(self.names[x[0]]), self.names[x[0]]))[:limit]
        self.stats["records_scored"] = len(best)
        return [Match(rid, self.names[rid], score, levenshtein(typed, normalize(self.names[rid])),
                      sorted(set(matched.get(rid, [])))) for rid, score in ranked]
