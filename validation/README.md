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
have more starts than games played). Also checks the whole dataset
at once: is the total record count reasonable, has any entire
column gone empty.

**drift.py**
Handles the case where the source website itself has changed, not
just one bad record. Compares the fields we got against the fields
we expected, and if something's missing but something unexpected
showed up instead, suggests how similar the names are (does
"appearances" look like it could be "games"). This only measures
name similarity, not football meaning, on purpose. It's a starting
signal, not a claim of certainty.

**recovery.py**
Decides what to do with a drift suggestion. If the name-similarity
confidence is high enough, it tries renaming the field on a copy of
the record, never the original, then runs that copy through every
check in schema.py again. Only if it comes out clean is the repair
called a success. If confidence is too low, or the repair still
fails validation, it refuses and says why.

**status.py**
Turns everything above into one final label: PASS, RECOVER,
QUARANTINE, or FAIL. RECOVER only gets used if a repair was
actually attempted and actually succeeded, not just because a
possible fix exists.

## Why these are four separate files instead of one

Each file answers a different question, and mixing them would blur
responsibilities that need to stay separate for the project's core
argument to hold up:

- schema.py asks: is this record internally correct?
- drift.py asks: has the source changed shape?
- recovery.py asks: can I safely fix this, and did the fix actually
  work?
- status.py asks: given everything above, what's the final verdict?

Recovery depends on schema (it needs the same checks to verify a
repair), so recovery.py imports from schema.py. Nothing goes the
other direction. That one-way dependency is deliberate: the basic
correctness checks in schema.py don't need to know that repair
logic exists, but repair logic can't claim success without
rechecking against them.

Keeping these separate also means each one can be tested and
debugged on its own. A bug in the drift-matching logic doesn't
require touching the range-checking code to find or fix it.

## Known issue found and fixed

An earlier version of the test pipeline called classify_status()
before attempt_repair() had run, so status was always calculated
against a missing repair result and defaulted to QUARANTINE
regardless of what the repair actually did. This was caught by
comparing the repair result and the status result side by side and
noticing they contradicted each other. Fixed by reordering the
pipeline so repair always completes before status is calculated.