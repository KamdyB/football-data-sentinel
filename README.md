## Validation

The scraper's raw output isn't trusted by default. Every record
passes through `validation/schema.py` before being treated as
usable data.

Checks currently implemented:
- **Schema presence** — all required fields exist on the record
- **Type validation** — text fields are strings; numeric fields
  convert cleanly to a number (scraped values arrive as strings,
  so this checks convertibility, not raw Python type)
- **Range validation** — numeric fields fall within plausible
  bounds (e.g. age 15-45, minutes 0-4140 for a season)
- **Cross-field validation** — logically impossible combinations
  are flagged (e.g. starts exceeding games played)
- **Row filtering** — FBref's combined stats table includes blank
  divider rows between squads; these are filtered before
  validation runs, not treated as malformed player data
- **Dataset-level checks** — total record count is checked against
  an expected range, and each required field is checked to confirm
  it isn't empty across the entire dataset (catches a whole column
  silently disappearing, not just one bad record)

Current status: 573 raw rows scraped from the EFL Championship
2025-26 stats page, 551 valid player records after filtering,
all validation checks passing. Each check has been verified
against deliberately malformed test data to confirm it actually
detects the problem it's meant to catch, not just against clean
input.

## Recovery and Status

When drift is detected, Sentinel does not repair automatically.
It proposes a field mapping using string similarity, then only
applies the repair if confidence clears a threshold (0.85) and
the repaired record passes the full validation pipeline.

Status meanings:
- PASS: clean record, no issues
- RECOVER: a repair was attempted, succeeded, and was revalidated
- QUARANTINE: drift was detected but no safe repair was possible,
  either because confidence was too low or the repair itself
  still failed validation
- FAIL: validation errors with no drift involved

Known bug found and fixed during development: an earlier version
computed status before the repair had run, so status always
defaulted to QUARANTINE regardless of the repair's real outcome.
Fixed by reordering the pipeline so repair completes before
classification runs. This is logged here deliberately, since
catching contradictory system state was part of proving the
Sentinel's decisions are trustworthy, not just present.