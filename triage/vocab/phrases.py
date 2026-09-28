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
    # "hasn't signed", "has not signed", "did not sign", "was never signed"
    r"\b(?:has|have|had|was|were|is|did|does|do)\s*(?:not|n't)\s+(?:yet\s+)?(?:been\s+)?sign(?:ed)?\b",
    r"\bnever\s+(?:been\s+)?sign(?:ed)?\b",
    # the consent exists but can't be used
    r"\b(?:missing|blank|absent|invalid|void|expired)\b",
    r"\bwrong\s+(?:patient|procedure|site|side|form)\b",
    r"\bre-?do(?:ne)?\b",
    # signing is still in the future
    r"\bwill\s+(?:be\s+)?sign(?:ed)?\b",
    r"\b(?:needs?|required|has|have|agreed|plans?)\s+to\s+(?:be\s+)?sign(?:ed)?\b",
    r"\bsign(?:ed)?\s+(?:on\s+)?(?:the\s+)?day\s+of\s+surgery\b",
)

CONSENT_SIGNED: tuple[str, ...] = (
    r"\bsigned\b",
    r"\bsignature\s+(?:is\s+)?on\s+file\b",
    r"\be-?signed\b",
    r"\belectronically\s+signed\b",
)

# instruction-like text inside a note, a note that talks to the system is never trusted to approve anything
INJECTION: tuple[str, ...] = (
    # needs an instruction-type word, "ignore previous bp reading" or "disregard the previous note" are normal corrections
    r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+)?(?:the\s+|your\s+)?(?:previous\s+|prior\s+|above\s+|earlier\s+)?(?:instructions|rules|prompts?|guidelines|polic(?:y|ies))\b",
    # "assistant:" is left out, op notes use it normally, "review of systems:" doesn't match the singular
    r"\b(?:system|developer)\s*(?:note|message|prompt|instruction)?\s*:",
    r"\b(?:mark|classify|output|return|set)\s+(?:this\s+)?(?:patient|case|consent|plan|decision|status)?\s*(?:as\s+)?(?:ready|signed|complete|approved|cleared)\b",
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

# what an llm quote must contain to back up its answer, so a well-formed but wrong answer is rejected
# e.g. the llm says SIGNED but quotes "questions answered", no signature wording, so it's not accepted
SIGNATURE_CUES: tuple[str, ...] = (
    r"\bsign(?:ed|ature|ing)?\b",
    r"\be-?sign",
    r"\bdocusign\b",
    r"\bexecuted\b",
    r"\bauthori[sz]ed\b",
    r"\battest",
)

# an h&p quote must show history and exam together, "history questionnaire" or "gait training" aren't one
HP_CUES: tuple[str, ...] = (
    r"h&p",
    r"\bhpi\b",
    r"\bhistory\b.*\b(?:physical|exam(?:ination)?)\b",
    r"\b(?:physical|exam(?:ination)?)\b.*\bhistory\b",
)

CONSENT_CUES: tuple[str, ...] = (r"\bconsent", r"\bauthori[sz]", r"\bagree")

# "not taking" needs stopped, never, past, or future wording, "continues coumadin" can't be read as NO
STOPPED_CUES: tuple[str, ...] = (
    r"\bstop(?:ped|s)?\b",
    r"\bdiscontinu",
    r"\bno\s+longer\b",
    r"\bcompleted?\b",
    r"\bnot\s+(?:currently\s+)?(?:taking|on)\b",
    r"\bnever\b",
    r"\ballerg",
    r"\bconsider",
    r"\bplan(?:ned|s|ning)?\s+to\s+start\b",
    r"\bhistory\s+of\b",
    r"\b(?:previous(?:ly)?|former(?:ly)?|prior)\b",
    r"\bin\s+(?:19|20)\d{2}\b",
)

# a before-surgery quote must say what happens to the drug, an after-surgery quote must say when it comes back
BEFORE_ACTION_CUES: tuple[str, ...] = (
    r"\bhold\b", r"\bheld\b", r"\bstop", r"\bdiscontinu", r"\blast\s+dose\b", r"\bcontinu", r"\bbridg",
    r"\bomit", r"\bwithhold", r"\bskip",
)
AFTER_ACTION_CUES: tuple[str, ...] = (
    r"\bresum", r"\brestart", r"\bre-?start", r"\breinitiat", r"\bcontinu", r"\brecommenc", r"\bstart",
)
# both quotes must carry an actual time, "hold before surgery and resume afterwards" has none
# a bare number isn't a time, "coumadin 5 mg daily" is a dose
TIMING_CUES: tuple[str, ...] = (
    r"\b\d+(?:\s*(?:-|to)\s*\d+)?\s*(?:hours?|hrs?|h|days?|d|weeks?|wks?)\b",
    r"\b(?:one|two|three|four|five|six|seven|twelve|twenty-four|forty-eight|seventy-two)\s+(?:hours?|days?|weeks?)\b",
    r"\b(?:morning|evening|night)\b",
    r"\b(?:post-?op(?:erative)?\s+day|pod)\s*#?\s*\d",
    r"\bday\s+(?:of|before|after|prior)\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",
)

# the before quote must be about before surgery and the after quote about after, "continues coumadin daily" is neither
BEFORE_CONTEXT_CUES: tuple[str, ...] = (
    r"\bbefore\b", r"\bprior\b", r"\bpre-?op", r"\bpreoperative", r"\blast\s+dose\b", r"\bahead\s+of\b",
)
AFTER_CONTEXT_CUES: tuple[str, ...] = (
    r"\bafter\b", r"\bpost-?op", r"\bpostoperative", r"\bfollowing\b", r"\bpod\b",
)
