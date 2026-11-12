"""Levenshtein edit distance by dynamic programming (insert, delete, replace each cost 1)."""


def levenshtein(a: str, b: str, limit: int | None = None) -> int:
    """Edits needed to turn a into b. With a limit, stops early and returns limit + 1 once it is exceeded."""
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a  # keep the shorter word in the row
    if limit is not None and len(a) - len(b) > limit:
        return limit + 1  # the length gap alone needs more edits
    previous = list(range(len(b) + 1))  # row for the empty prefix of a
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            if ca == cb:
                current.append(previous[j - 1])  # letters match: copy the diagonal
            else:
                current.append(1 + min(previous[j],  # delete from a
                                       current[j - 1],  # insert into a
                                       previous[j - 1]))  # replace
        if limit is not None and min(current) > limit:
            return limit + 1  # every path through this row is already too long
        previous = current
    return previous[-1]


def table(a: str, b: str) -> list[list[int]]:
    """The full DP table, for teaching and the report: cell [i][j] is the distance between a[:i] and b[:j]."""
    rows = [list(range(len(b) + 1))]
    for i, ca in enumerate(a, start=1):
        row = [i]
        for j, cb in enumerate(b, start=1):
            row.append(rows[i - 1][j - 1] if ca == cb else 1 + min(rows[i - 1][j], row[j - 1], rows[i - 1][j - 1]))
        rows.append(row)
    return rows
