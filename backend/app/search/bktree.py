"""BK-tree: finds all words within k edits of a query without comparing it to every word."""
from app.search.levenshtein import levenshtein


class BKTree:
    """Children hang on edges labelled with their distance to the parent; only edges d-k..d+k can hold matches."""

    def __init__(self, words=()):
        self.root: tuple[str, dict] | None = None  # (word, {distance: child})
        self.size = 0
        self.comparisons = 0  # distance computations in the last search, for the evaluation
        for w in words:
            self.add(w)

    def add(self, word: str) -> None:
        if self.root is None:
            self.root = (word, {})
            self.size = 1
            return
        node = self.root
        while True:
            d = levenshtein(word, node[0])
            if d == 0:
                return  # already in the tree
            child = node[1].get(d)
            if child is None:
                node[1][d] = (word, {})
                self.size += 1
                return
            node = child

    def search(self, word: str, k: int) -> list[tuple[str, int]]:
        """Words within k edits of word, nearest first."""
        self.comparisons = 0
        if self.root is None:
            return []
        found, stack = [], [self.root]
        while stack:
            node_word, children = stack.pop()
            d = levenshtein(word, node_word)
            self.comparisons += 1
            if d <= k:
                found.append((node_word, d))
            for edge, child in children.items():
                if d - k <= edge <= d + k:
                    stack.append(child)
        return sorted(found, key=lambda x: (x[1], x[0]))

    def __len__(self) -> int:
        return self.size
