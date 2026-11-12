"""Text normalisation for name search, including common Nepali romanisation differences."""
import re
import unicodedata

# Spellings of the same sound in romanised Nepali names, folded to one form before comparing.
# Order matters: longer patterns first.
_FOLDS = [
    ("ksh", "x"), ("chh", "ch"), ("aa", "a"), ("ee", "i"), ("oo", "u"),
    ("v", "b"), ("w", "b"), ("z", "j"), ("ph", "f"),
]
_ENDINGS = [("ey", "e"), ("y", "i")]


def normalize(text: str) -> str:
    """Lowercase, strip accents and punctuation, collapse spaces."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


def fold(word: str) -> str:
    """One spelling per sound: Lakshmi and Laxmi, Vishnu and Bishnu, Pooja and Puja become equal."""
    for a, b in _FOLDS:
        word = word.replace(a, b)
    for a, b in _ENDINGS:
        if len(word) > 3 and word.endswith(a):
            word = word[: -len(a)] + b
            break
    return word


def words(text: str) -> list[str]:
    """Folded words of a name or query."""
    return [fold(w) for w in normalize(text).split()]


def max_edits(word: str) -> int:
    """Edits allowed for a word of this length: none for very short words, more for long ones."""
    n = len(word)
    if n <= 2:
        return 0
    if n <= 5:
        return 1
    if n <= 9:
        return 2
    return 3
