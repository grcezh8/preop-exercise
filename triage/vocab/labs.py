"""lab codes and display names we recognize for the tests the policy requires"""

from __future__ import annotations

# lab code (uppercased, spaces removed) -> required test
LAB_CODES: dict[str, str] = {
    "CBC": "CBC",
    "LAB-CBC": "CBC",
    "CBCWDIFF": "CBC",
    "CBC-DIFF": "CBC",
    "CBCD": "CBC",
    "CMP": "CMP",
    "LAB-CMP": "CMP",
    "CMP14": "CMP",
}

# used only when the code isn't recognized, matched against the lowercased display name
LAB_DISPLAY_PHRASES: dict[str, str] = {
    "complete blood count": "CBC",
    "comprehensive metabolic panel": "CMP",
}
