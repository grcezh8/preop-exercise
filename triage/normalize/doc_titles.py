"""sorts a document title into a kind, cheapest check first
rules -> fuzzy match -> UNKNOWN (llm step a handles UNKNOWN and VAGUE_HP later)
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from triage.normalize.text import clean
from triage.schemas.normalized import DocKind, KindSource
from triage.vocab import doc_titles as vocab


def clean_title(title: object) -> str:
    # strips filing decorations and rewrites every h&p spelling to "h&p"
    text = clean(title)
    for pattern in vocab.DECORATIONS:
        text = re.sub(pattern, " ", text)
    for pattern in vocab.HP_VARIANTS:
        text = re.sub(pattern, "h&p", text)
    return re.sub(r"\s+", " ", text).strip()


def classify_document(title: object, text_clean: str) -> tuple[DocKind, KindSource]:
    text = clean_title(title)
    if not text:
        return "UNKNOWN", "none"
    # order matters: a "cardiology progress note - anticoag" is an anticoag note, not other
    if _any(vocab.CONSENT, text):
        return "CONSENT", "rules"
    if _any(vocab.ANTICOAG_NOTE, text):
        return "ANTICOAG_NOTE", "rules"
    if "h&p" in text:
        return "HP", "rules"
    if _any(vocab.VAGUE_HP, text):
        return "VAGUE_HP", "rules"
    if _any(vocab.OTHER, text):
        return "OTHER", "rules"
    if _fuzzy_contains(text, vocab.FUZZY_HP):
        # a typo'd title only counts when the note itself says h&p, otherwise the llm reads it
        return ("HP", "fuzzy") if _mentions_hp(text_clean) else ("VAGUE_HP", "fuzzy")
    return "UNKNOWN", "none"


def _mentions_hp(text_clean: str) -> bool:
    for pattern in vocab.HP_VARIANTS:
        text_clean = re.sub(pattern, "h&p", text_clean)
    return "h&p" in text_clean


def _any(patterns: tuple[str, ...], text: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _fuzzy_contains(text: str, targets: tuple[str, ...]) -> bool:
    # compares each target against every run of words of the same length, catches "history & phsyical"
    words = re.findall(r"[a-z]+", text.replace("&", " and "))
    for target in targets:
        size = len(target.split())
        for start in range(len(words) - size + 1):
            window = " ".join(words[start : start + size])
            if SequenceMatcher(None, window, target).ratio() >= vocab.FUZZY_MIN_RATIO:
                return True
    return False
