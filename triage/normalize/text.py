"""text cleanup shared by everything that reads titles or notes"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

# look-alike letters from other alphabets that nfkc leaves alone, e.g. cyrillic "ѕ" in "ѕigned"
_CONFUSABLES = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
        "ѕ": "s", "і": "i", "ј": "j", "ԁ": "d", "ɡ": "g", "ո": "n", "ν": "v",
        "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
        "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Χ": "X", "Υ": "Y",
        "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
        "Р": "P", "С": "C", "Т": "T", "Х": "X", "Ѕ": "S", "І": "I", "Ј": "J",
        "ο": "o", "α": "a", "ε": "e", "ι": "i", "κ": "k", "ρ": "p", "τ": "t",
    }
)
# control and invisible characters, e.g. zero-width spaces used to split "sig​ned"
_INVISIBLE = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f​-‏⁠﻿]")
_SPACES = re.compile(r"\s+")


def clean(value: object) -> str:
    # nfkc, look-alike letters mapped, invisible characters dropped, whitespace collapsed, lowercase
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKC", value).translate(_CONFUSABLES)
    text = _INVISIBLE.sub("", text)
    return _SPACES.sub(" ", text).strip().casefold()


def has_confusables(value: object) -> bool:
    return isinstance(value, str) and value.translate(_CONFUSABLES) != value


def find_first(patterns: Iterable[str], text: str) -> re.Match[str] | None:
    # earliest match across all patterns, so evidence quotes the first relevant spot
    best: re.Match[str] | None = None
    for pattern in patterns:
        match = re.search(pattern, text)
        if match and (best is None or match.start() < best.start()):
            best = match
    return best


def sentence_around(raw: str, needle: str, limit: int = 240) -> str:
    # the sentence of the original text containing needle, used as an evidence excerpt
    # searches case-insensitively in the original so the excerpt is an exact substring of it
    raw = raw.strip()
    if len(raw) <= limit:
        return raw
    position = raw.casefold().find(needle.casefold()) if needle else -1
    if position < 0:
        return _shorten(raw, limit)
    previous_stop = raw.rfind(". ", 0, position)
    start = previous_stop + 2 if previous_stop >= 0 else 0
    next_stop = raw.find(". ", position)
    end = next_stop + 1 if next_stop >= 0 else len(raw)
    return _shorten(raw[start:end], limit)


def _shorten(piece: str, limit: int) -> str:
    # cuts at the last whole word before limit, only when the piece is too long
    piece = piece.strip()
    if len(piece) <= limit:
        return piece
    cut = piece[:limit]
    return cut[: cut.rfind(" ")].strip() if " " in cut else cut
