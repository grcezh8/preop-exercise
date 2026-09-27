"""builds a clean READY submission that tests change one thing at a time"""

from __future__ import annotations

import copy
from typing import Any

PROCEDURE_DATE = "2026-03-10"

_READY: dict[str, Any] = {
    "patient": {
        "id": "p-1",
        "mrn": "MRN-4455667",
        "name": {"given": "Rosalind", "family": "Okonkwo"},
        "dob": "1950-05-05",
        "sex": "F",
    },
    "procedure": {
        "case_id": "case_test",
        "procedure_type": "Elective hernia repair",
        "procedure_risk": "LOW",
        "procedure_date": PROCEDURE_DATE,
        "is_elective": True,
        "location": "Cadence Surgical Center - Main OR",
    },
    "vitals": [
        {"type": "blood_pressure", "systolic": 124, "diastolic": 78, "date": "2026-03-01T09:00:00Z", "source": "clinic"},
        {"type": "temperature", "value_f": 98.6, "date": "2026-03-01T09:05:00Z", "source": "clinic"},
    ],
    "labs": [
        {"id": "l-1", "code": "CBC", "display": "Complete Blood Count", "effective_at": "2026-03-01T08:00:00Z", "status": "final", "source": "lab"},
    ],
    "medications": [{"name": "lisinopril", "active": True}],
    "conditions": [],
    "documents": [
        {"doc_id": "d-1", "type": "History and Physical", "date": "2026-03-01", "author": "Ada Quill, MD", "text": "H&P completed; patient reviewed in pre-op clinic."},
        {"doc_id": "d-2", "type": "Surgical Consent", "date": "2026-03-02", "author": "Ben Arrow, DO", "text": "Consent obtained and signed by patient."},
    ],
    "metadata": {"submission_received_at": "2026-03-05T10:00:00Z", "source_system": "test"},
}


def ready() -> dict[str, Any]:
    return copy.deepcopy(_READY)


def days_before_procedure(days: int) -> str:
    # an iso date `days` before the test procedure date, negative means after
    import datetime as dt

    return (dt.date.fromisoformat(PROCEDURE_DATE) - dt.timedelta(days=days)).isoformat()
