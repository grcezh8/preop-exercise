"""wording used to sort document titles into types, all applied to cleaned lowercase titles"""

from __future__ import annotations

# filing decorations that say nothing about what the document is, stripped first
DECORATIONS: tuple[str, ...] = (
    r"\[pdf\]",
    r"\((?:scanned|external|pdf|signed)\)",
    r"^\s*(?:scanned|imported)\s*:?\s*",
    r"^\s*pre-?op\s*-\s*",
    r"\s-\s*signed\s*$",
)

# spellings of "history and physical", each rewritten to "h&p"
HP_VARIANTS: tuple[str, ...] = (
    r"\bh\s*(?:&|\+|/|and)\s*p\b",
    r"\b(?:history|hist|hx)\.?\s*(?:&|and|/)\s*(?:physical|phys)\.?(?:\s+(?:examination|exam))?\b",
)

CONSENT = (r"\bconsent\b",)

ANTICOAG_NOTE = (
    r"\banticoag",
    r"\bmedication\s+(?:plan|review|management)\b",
    r"\bbridging\b",
)

# titles that could be an h&p but don't say so, they need their text read (llm step a)
VAGUE_HP = (
    r"\bclearance\b",
    r"\bpre-?op(?:erative)?\s+(?:evaluation|assessment)\b",
    r"\bpre-?anesthesia\s+evaluation\b",
    r"\bpre-?surgical\s+(?:evaluation|assessment)\b",
    # shorthand like "hx & px", "hx/pe", "history & exam", "hpi and exam"
    r"\b(?:hx|history|hpi)\s*(?:&|and|/|\+)\s*(?:px|pe|exam|examination)\b",
    # pre-admission testing visits often hold the h&p
    r"\bpre-?admission\s+testing\b",
    r"\bpat\s+(?:note|evaluation|visit|assessment)\b",
)

# titles known not to be any document the policy needs
OTHER = (
    r"\bnursing\b",
    r"\banesthesia\s+pre-?assessment\b",
    r"\bfollow-?\s*up\b",
    r"\bprogress\s+note\b",
    r"\bdischarge\b",
    r"\boperative\s+report\b",
    r"\bphysical\s+therapy\b",
    r"\bradiology\b",
    r"\bimaging\b",
    r"\blab(?:oratory)?\s+report\b",
)

# fuzzy targets, compared against runs of words of the same length to catch typos
# single words like "consent" aren't fuzzy matched, "content" scores as close as the typo "consnet"
FUZZY_HP = ("history and physical",)
FUZZY_MIN_RATIO = 0.85
