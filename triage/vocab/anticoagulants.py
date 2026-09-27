"""anticoagulants we recognize, generic name -> every name it can appear under
antiplatelets (aspirin, clopidogrel, ticagrelor, prasugrel) are left out on purpose, they don't trigger rule 3
"""

from __future__ import annotations

ANTICOAGULANTS: dict[str, tuple[str, ...]] = {
    "apixaban": ("apixaban", "eliquis"),
    "rivaroxaban": ("rivaroxaban", "xarelto"),
    "edoxaban": ("edoxaban", "savaysa", "lixiana"),
    "dabigatran": ("dabigatran", "pradaxa"),
    "warfarin": ("warfarin", "coumadin", "jantoven"),
    "enoxaparin": ("enoxaparin", "lovenox"),
    "dalteparin": ("dalteparin", "fragmin"),
    "tinzaparin": ("tinzaparin", "innohep"),
    "heparin": ("heparin",),
    "fondaparinux": ("fondaparinux", "arixtra"),
    "acenocoumarol": ("acenocoumarol", "sintrom"),
    "phenprocoumon": ("phenprocoumon", "marcumar"),
    "argatroban": ("argatroban",),
    "bivalirudin": ("bivalirudin", "angiomax"),
}

# every recognized name -> its generic name
NAME_TO_GENERIC: dict[str, str] = {
    name: generic for generic, names in ANTICOAGULANTS.items() for name in names
}

# words that mean "blood thinner" without naming a drug, used to find the note an anticoag issue points at
GENERIC_TERMS: tuple[str, ...] = ("anticoag", "blood thinner", "doac", "noac")
