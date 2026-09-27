"""wording that decides consent, unfinished notes and unfinished plans, all as regex on cleaned lowercase text"""

from __future__ import annotations

# not-signed wording always wins over signed wording, "unsigned" contains "signed"
CONSENT_NOT_SIGNED: tuple[str, ...] = (
    r"\bunsigned\b",
    r"\bnot\s+(?:yet\s+)?(?:been\s+)?signed\b",
    r"\bawaiting\s+(?:\w+\s+)?signature\b",
    r"\bsignature\s+(?:is\s+)?(?:pending|not\s+(?:yet\s+)?on\s+file|missing|required|needed|outstanding)\b",
    r"\bpending\s+(?:\w+\s+)?signature\b",
    r"\bto\s+be\s+signed\b",
    r"\brequested\s+signature\b",
    r"\b(?:withdrawn|withdrew|revoked|rescinded|declined|refused)\b",
)

CONSENT_SIGNED: tuple[str, ...] = (
    r"\bsigned\b",
    r"\bsignature\s+(?:is\s+)?on\s+file\b",
    r"\be-?signed\b",
    r"\belectronically\s+signed\b",
)

# an anticoag plan using any of these isn't finished
PLAN_PENDING: tuple[str, ...] = (
    r"\bpending\b",
    r"\bto\s+be\s+(?:finali[sz]ed|completed|determined|confirmed|decided|discussed)\b",
    r"\bnot\s+(?:yet\s+)?(?:documented|finali[sz]ed|completed|complete|decided|determined)\b",
    r"\bincomplete\b",
    r"\bin\s+progress\b",
    r"\bfollow\s*-?\s*up\s+with\b",
    r"\bawaiting\b",
    r"\btbd\b",
    r"\bno\s+clear\b",
)

# an h&p using any of these isn't completed, kept narrower than PLAN_PENDING because
# normal h&p wording like "no clear contraindication" or "follow up with pcp" is fine
HP_UNFINISHED: tuple[str, ...] = (
    r"\b(?:h&p|evaluation|exam|note)\s+(?:is\s+)?(?:pending|incomplete|in\s+progress)\b",
    r"\bto\s+be\s+completed\b",
    r"\bnot\s+(?:yet\s+)?completed\b",
    r"\bincomplete\b",
    r"\bdraft\b",
)
