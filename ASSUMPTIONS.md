# Assumptions

Where the policy is silent or ambiguous, the triage system makes these assumptions. Each one is
enforced in code and covered by tests in `tests/`.

## Dates and "most recent"

- **Day counts** use the calendar date in UTC. A lab at `2026-03-01T23:30:00-05:00` counts as
  2026-03-02.
- **"Within N days"** means 0 to N days before the procedure. Exactly N days passes; N+1 fails.
- **A result dated after the procedure date** fails its window check. It isn't skipped in favor
  of an older result.
- **"Only the most recent result is considered"** is applied literally to CBC, CMP, blood
  pressure and temperature. We never fall back to an older result. A newest lab whose `status`
  isn't `final` fails with "CBC result not final" / "CMP result not final".
- **H&P:** the policy doesn't say "most recent" for documents, but we use the most recent H&P, the
  same as for tests. An older, stale H&P doesn't matter if a newer one is within the window.
- **Ties** (same timestamp) go to the item later in the list.
- **Undated items** can't be "most recent". Labs, vitals and H&Ps without a valid date are treated
  as not on file.

## Missing or invalid values

- **A value we can't read counts as missing:** a bad date, a risk outside LOW/MODERATE/HIGH, or a
  non-numeric blood pressure. This follows the policy's "missing/unknown → NEEDS_FOLLOW_UP". The
  evidence says what the value actually was.
- **Missing procedure date:** reported once. The H&P and lab date checks are skipped, because they
  can't be judged without it.
- **Missing procedure risk:** reported once. The lab checks are skipped, because the required tests
  depend on it.
- **Missing blood pressure or temperature** is missing required data: Rule 4 can't be checked
  without them.
- **A blood thinner with `active: null`** is reported as "Unknown anticoagulant active status".
  No plan is asked for until its status is known.
- **The procedure date is never taken from note text** (e.g. "Procedure date target: 2026-03-01").
  Structured fields are the source of truth.

## Vitals

- **Blood pressure:** systolic ≥ 180 **or** diastolic ≥ 110. If the latest reading has only one
  number and that number is over its limit, the patient is NOT_CLEARED. If the one number is
  normal, the reading is treated as missing, because the other number can't be ruled out.
- **Temperature:** > 100.4°F (100.4 exactly passes). `value_c` is converted to °F. A `value_f`
  below 80 is almost certainly Celsius typed into the wrong field, so it's treated as unknown
  rather than read as normal.
- **No age limit** on the latest reading. The policy doesn't set one.
- **Rule 4 only uses the `vitals` list.** Numbers written in notes are not used.

## Documents

- **Document types come from the title.** We handle the many spellings of "History and Physical"
  (H&P, H and P, H+P, H/P, Hx & Physical, Hist & Phys, with Scanned/Imported/[PDF]/(external)
  decorations).
  - A title with a typo (e.g. "History & Phsyical") counts as an H&P only if the note text also
    says H&P.
  - Vague titles ("Medical Clearance", "Pre-op Evaluation", "Pre-anesthesia Evaluation") and
    shorthand ("Hx & Px", "Hx/PE", "History & Exam", "PAT Note", "Pre-Surgical Evaluation") are
    not counted as an H&P unless the note is read and confirmed to be one.
  - Bare "HP" isn't treated as an H&P from the title, because it has other meanings (e.g.
    H. pylori).
  - An H&P we can't recognize gives "History and Physical document missing"
    (NEEDS_FOLLOW_UP), never a false READY.
- **An H&P whose text says it isn't finished** ("H&P pending", "to be completed", "incomplete",
  "draft") doesn't count as completed.
- **The most recent consent document decides.** A newer unsigned or withdrawn consent fails even
  if an older one was signed. "Unsigned", "not signed", "awaiting signature", "to be signed",
  "withdrawn", "revoked" and similar always win over the word "signed".

## Blood thinners (Rule 3)

- **Anticoagulants** are matched by generic or brand name, with small typos allowed (e.g.
  "apixiban"). The full list is in `triage/vocab/anticoagulants.py`.
- **Antiplatelets (aspirin, clopidogrel, ticagrelor, prasugrel) are not anticoagulants** and don't
  trigger Rule 3.
- **A plan must say, for each blood thinner, what happens before surgery with timing and what
  happens after surgery with timing.** Wording like "pending", "to be finalized", "follow up with
  cardiology", "no clear … guidance" or "not yet documented" means the plan isn't finished.
- **A blood thinner named in a note but not active in the medication list** is treated as being
  taken, and needs a plan, unless the note clearly says it was stopped.
- **One issue per drug,** even if the drug appears in the medication list more than once.

## Evidence

- **Every issue's `source` points at the exact item** (`documents[2]`, `labs[0]`,
  `procedure.procedure_date`), or at the whole list when something is missing (`documents`,
  `labs`, `vitals`).
- **For a missing item,** the details list what was on file, so a reviewer can see what was
  checked.

## Known differences from the expected outputs

These are listed with reasons in `evals/known_oracle_disagreements.json`. In short:
- **case_00002:** a valid, recent H&P has a typo in its title. The expected output misses it; we
  follow the policy.
- **case_00042:** our anticoag evidence points at the specific plan note. The expected output
  points at the whole document list.
