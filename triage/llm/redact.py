"""removes patient and staff details from text before it goes into any prompt
identifiers are taken from the submission itself, plus common patterns (phones, emails, ssn, mrn, long numbers)
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

# credentials after a comma in author names, e.g. "Danielle Rivera, APRN"
_CREDENTIALS = {"md", "do", "rn", "np", "pa", "aprn", "msn", "dnp", "fnp", "bc", "c", "phd", "pharmd", "crna", "mba", "mph", "dr"}

_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"[\w.+-]+@[\w-]+\.[\w.]+", "[EMAIL]"),
    (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]"),
    (r"(?:\+?1[\s.-]?)?\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b", "[PHONE]"),
    (r"\bMRN\s*[-:#]?\s*\w+", "[MRN]"),
    (r"\b\d{7,}\b", "[NUMBER]"),
)


class Redactor:
    def __init__(self, data: dict[str, Any]) -> None:
        self.terms = _identifiers(data)
        # longest first, so "Sophia Simmons" is replaced before "Sophia"
        ordered = sorted(self.terms, key=len, reverse=True)
        self._terms = [
            (re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE), label) for term, label in ((t, self.terms[t]) for t in ordered)
        ]

    def __call__(self, text: str) -> str:
        for pattern, label in self._terms:
            text = pattern.sub(label, text)
        for pattern, label in _PATTERNS:
            text = re.sub(pattern, label, text, flags=re.IGNORECASE)
        return text


def _identifiers(data: dict[str, Any]) -> dict[str, str]:
    # identifier text -> placeholder
    terms: dict[str, str] = {}
    patient = data.get("patient") or {}
    name = patient.get("name") or {}
    given, family = name.get("given"), name.get("family")
    for part in (given, family):
        _add(terms, part, "[NAME]")
    if isinstance(given, str) and isinstance(family, str):
        _add(terms, f"{given} {family}", "[NAME]")
        _add(terms, f"{family}, {given}", "[NAME]")
    _add(terms, patient.get("mrn"), "[MRN]")
    if isinstance(patient.get("mrn"), str):
        _add(terms, re.sub(r"\D", "", patient["mrn"]), "[MRN]")
    _add(terms, patient.get("id"), "[ID]")
    for variant in _date_variants(patient.get("dob")):
        _add(terms, variant, "[DOB]")
    procedure = data.get("procedure") or {}
    _add(terms, procedure.get("case_id"), "[ID]")
    for doc in data.get("documents") or []:
        if isinstance(doc, dict):
            _add(terms, doc.get("doc_id"), "[ID]")
            for part in _author_names(doc.get("author")):
                _add(terms, part, "[STAFF]")
    return terms


def _add(terms: dict[str, str], value: object, label: str) -> None:
    # very short values would wipe out ordinary words, e.g. a one-letter initial
    if isinstance(value, str) and len(value.strip()) >= 2:
        terms.setdefault(value.strip(), label)


def _author_names(author: object) -> list[str]:
    if not isinstance(author, str):
        return []
    name = author.split(",")[0]
    parts = [p.strip(".") for p in name.split() if p.strip(".").casefold() not in _CREDENTIALS]
    return [name.strip(), *[p for p in parts if len(p) >= 2]]


def _date_variants(value: object) -> list[str]:
    # 1948-01-02, 01/02/1948, 1/2/1948, 01-02-1948
    if not isinstance(value, str):
        return []
    try:
        day = dt.date.fromisoformat(value.strip()[:10])
    except ValueError:
        return [value]
    return [
        day.isoformat(),
        f"{day.month:02d}/{day.day:02d}/{day.year}",
        f"{day.month}/{day.day}/{day.year}",
        f"{day.month:02d}-{day.day:02d}-{day.year}",
    ]
