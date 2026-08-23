# Validation

This folder is the core of the project: the layer that decides
whether scraped data can be trusted before anything downstream
uses it.

## Files

**schema.py**
Checks one player record at a time: does it have all the required
fields, are the values the right kind of data (text vs number),
are numbers within a plausible range for football (age, minutes,
goals), and do related fields make sense together (a player can't
have more starts than games played). Also checks the whole
dataset at once: is the total record count reasonable, has any
entire column gone empty, and are there repeated player/squad
combinations worth a second look.

**drift.py**
Handles the case where the source website itself has changed, not
just one bad record. Compares the fields we got against the
fields we expected. If a field is missing but something unexpected
showed up instead, suggests whether the unexpected field could be
a stand-in, either through a known domain alias (`appearances`
meaning `games`) or through plain name similarity as a fallback.
Name similarity alone is a weak signal, kept deliberately weak on
purpose, since two field names looking alike is not proof they
mean the same thing.

**recovery.py**
Decides what to do with a drift suggestion. If confidence is high
enough, tries renaming the field on a copy of the record, never
the original, then runs that copy through every check in
schema.py again. Only if it comes out clean is the repair called
a success. If confidence is too low, or the repair still fails
validation, it refuses and says why.

**ai_healer.py**
A fallback for the cases drift.py's deterministic matching can't
resolve, a field renamed to something with no lexical resemblance
to the original (`gp` instead of `games`). Only called once per
distinct drift pattern across a whole dataset, not once per
record, and only ever offered fields that haven't already been
hard-blocked by drift.py's blocklist, so it can propose a genuinely
uncertain mapping but can never override a known-unsafe one. Any
network failure degrades to no suggestion rather than crashing the
run. Off entirely unless `GEMINI_API_KEY` is set.

**status.py**
Turns everything above into one final label:

- PASS: nothing wrong
- RECOVER: something was missing, a repair was attempted, and it
  actually worked
- QUARANTINE: something required is missing and no safe repair
  was possible
- WARNING: an extra, unrecognized field showed up but nothing
  required is missing, so the record is still usable
- FAIL: validation errors with no drift involved

RECOVER only gets used if a repair was actually attempted and
actually succeeded, not just because a possible fix exists. An
extra field on its own is a WARNING, not a reason to quarantine a
record that's otherwise fine.

**report.py**
Takes the outcome of a run and turns it into one structured
report: which schema version produced it, how many records came
in, how many were trusted, recovered, or quarantined, and what
drift or duplicates were found. This is the one artifact
everything downstream (a CLI summary, an API response, a future
frontend) is meant to read, instead of reaching into the
validation logic directly.

## Why these are six separate files instead of one

Each file answers a different question, and mixing them would
blur responsibilities that need to stay separate for the
project's core argument to hold up:

- schema.py asks: is this record internally correct?
- drift.py asks: has the source changed shape, and is a proposed
  fix even safe to consider?
- recovery.py asks: can I safely apply this fix, and did it
  actually work once applied?
- ai_healer.py asks: for the fields nothing above could resolve,
  is there a plausible answer worth proposing, without ever being
  allowed to bypass drift.py's safety boundary?
- status.py asks: given everything above, what's the final
  verdict?
- report.py asks: how do I describe this run to something outside
  the validation layer?

recovery.py depends on schema.py, since it needs the same checks
to verify a repair. ai_healer.py is only ever called by pipeline.py
after recovery.py has already failed, and only receives candidates
drift.py has already filtered. report.py depends on status.py and
schema.py, since it needs the status labels and the schema version.
Nothing goes the other direction. schema.py doesn't know recovery.py
exists, and status.py doesn't know report.py exists. That one-way
dependency is deliberate: the lower-level checks stay independent
of the orchestration built on top of them.

Keeping these separate also means each one can be tested and
debugged on its own. A bug in the drift-matching logic doesn't
require touching the range-checking code to find or fix it.

## Known issues found and fixed

An earlier version of the pipeline called classify_status() before
attempt_repair() had run, so status was always calculated against
a missing repair result and defaulted to QUARANTINE regardless of
what the repair actually did. Found by comparing the repair result
and the status result side by side and noticing they contradicted
each other. Fixed by reordering the pipeline so repair always
completes before status is calculated.

A separate issue: any unrecognized extra field was originally
treated the same as a missing required field, meaning a source
that only added a new column (no data lost) would get the entire
record quarantined for no real reason. Fixed by splitting drift
handling in classify_status(): only a missing required field
triggers a repair-or-quarantine decision, an extra field alone
produces WARNING instead.

## Adapting this for a different data source

Everything specific to EFL Championship player stats lives in
schema.py as constants: REQUIRED_FIELDS, NUMERIC_FIELDS,
TEXT_FIELDS, RANGE_CHECKS, PLAYERS_PER_SQUAD_RANGE, SCHEMA_NAME, and
SCHEMA_VERSION. To point this pipeline at a different source, a
different soccerdata endpoint, a StatsBomb export, a different
competition entirely, only that file needs new values.
PLAYERS_PER_SQUAD_RANGE in particular is deliberately not a fixed
total record count, it's a plausible-squad-size band multiplied by
however many distinct squads are actually present in the data, so
moving to a competition with a different number of clubs doesn't
require editing a magic number by hand. drift.py's FIELD_ALIASES
also needs its own entries for whatever field-naming quirks the new
source has.

recovery.py, status.py, report.py, and pipeline.py don't contain
any football-specific knowledge. They operate on whatever
REQUIRED_FIELDS and RANGE_CHECKS say, so they don't need to change
when the data source changes. The decision engine is reusable, the
football knowledge is not, and that separation is the point.