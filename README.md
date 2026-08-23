# Football Data Sentinel

Football Data Sentinel is a validation and self-recovery layer for scraped
football data. It sits between the raw scraper output and downstream
analysis, with the goal of preventing malformed or structurally changed
source data from silently entering the analytics pipeline.

The current implementation is built around the EFL Championship 2025-26
player statistics dataset scraped from FBref via Bright Data Scraper
Studio. The validation and recovery components are designed to be reusable
across future football datasets and scraper runs.

## Pipeline

The current pipeline is:

    raw JSON
        ↓
    player-row filtering
        ↓
    record validation
        ↓
    dataset validation
        ↓
    schema drift detection
        ↓
    deterministic field mapping
        ↓
    AI-assisted mapping fallback (optional)
        ↓
    recovery + revalidation
        ↓
    status classification
        ↓
    run report

Every run produces a timestamped JSON report under `data/runs/`.

## Validation

The scraper's raw output isn't trusted by default. Every record passes
through `validation/schema.py` before being treated as usable data.

Checks currently implemented:

Schema presence confirms all required fields exist on the record. Type
validation checks that text fields are strings and numeric fields convert
cleanly to a number, since scraped values arrive as strings, this checks
convertibility rather than raw Python type. Range validation confirms
numeric fields fall within plausible bounds, for example age 15 to 45 or
minutes 0 to 4140 for a 46-game Championship season. Cross-field
validation flags logically impossible combinations, such as starts
exceeding games played. Row filtering removes the blank divider rows
FBref's combined stats table includes between squads, so they're never
treated as malformed player data. Dataset-level checks confirm the total
record count is plausible for however many distinct squads are actually
present, and that each required field isn't empty across the entire
dataset, which catches a whole column silently disappearing rather than
just one bad record.

Each check has been verified against deliberately malformed test data to
confirm it actually detects the problem it's meant to catch, not just
against clean input. See `tests/test_failures.py`, `tests/test_engine.py`,
and `tests/test_schema.py`.

## Drift Detection

Sentinel compares the fields present in an incoming record against the
expected schema defined in `validation/schema.py`.

Drift identifies missing fields, ones required by the schema but absent
from the record, and unexpected fields, ones present in the record but not
part of the expected schema.

For example, replacing `games` with `appearances` produces:

    missing: ["games"]
    unexpected: ["appearances"]

`validation/drift.py` scores every missing/unexpected field pair and
greedily assigns the best safe match to each missing field, not just the
narrow case of exactly one missing and one unexpected field. Some field
pairs are hard-blocked regardless of how similar the names look, xG and
xAG are expected-value metrics, not renamed versions of goals and assists,
so they can never be auto-mapped onto them. A rename there would insert a
wrong number, not fix a missing one.

## Recovery, AI-Assisted Fallback, and Status

When drift is detected, Sentinel does not repair automatically. It
proposes field mappings using string similarity and known domain aliases
(`appearances` recognized as `games`, for example), then only applies a
repair if confidence clears a threshold of 0.85 and the repaired record
passes the full validation pipeline.

If a missing field's deterministic mapping fails and `GEMINI_API_KEY` is
set, Sentinel falls back to an AI-assisted pass before giving up on that
field. This only runs once per distinct drift pattern across the whole
dataset, not once per record, since schema drift is structural: every
record sharing the same missing and unexpected fields has the same
underlying cause. The AI is never offered a field pair that's already
hard-blocked, so it can't override that safety boundary regardless of
what it would otherwise conclude. Any mapping it proposes still goes
through the same revalidation as a deterministic one, and is tagged
`ai_suggested` in the run report rather than blended in as equivalent
to a hand-verified alias. If the AI call fails for any reason, network
drop, rate limit, or anything else, that field is left unresolved and
the record is quarantined rather than the run crashing.

Status meanings:

PASS is a clean dataset with no issues requiring recovery. RECOVER means
drift was detected, a safe repair was applied, and the repaired record
passed validation. QUARANTINE means drift was detected but no safe repair
was possible, either because confidence was too low, the field pair was
blocked, or the repair itself still failed validation. FAIL means
validation errors with no recoverable drift involved. WARNING is a
non-fatal condition requiring attention.

Recovery is deliberately conservative. An uncertain mapping is rejected
rather than guessed, whether that mapping came from string similarity or
from the AI fallback.

A recovery attempt is not considered successful merely because a field
was renamed. `validation/recovery.py` re-runs the complete record
validation suite against the repaired record before returning
`success: true`.

## Run Reports

Each pipeline execution produces a timestamped JSON report under
`data/runs/`, plus a `data/runs/latest.json` pointer to the most recent
one. History lives in the timestamped files, `latest.json` is a
convenience reference, not the audit trail.

A clean run currently produces output of this form:

    {
      "status": "pass",
      "records": {
        "raw": 822,
        "player_rows": 791,
        "recovered": 0,
        "quarantined": 0,
        "final_trusted": 791
      },
      "validation": {
        "errors": []
      },
      "drift": {
        "detected": false,
        "missing": [],
        "unexpected": []
      }
    }

The report records the decision made by Sentinel for that run rather than
silently overwriting the source data.

## Failure Cases Verified

The recovery path has been tested against a deliberately modified record
where `games` becomes `appearances`. The resulting drift is correctly
detected as `missing: ["games"]`, `unexpected: ["appearances"]`. The first
implementation rejected this mapping because the two field names have low
lexical similarity, which exposed a limitation in treating semantic field
aliases as ordinary string similarity. The mapping was added as an
explicit trusted domain alias, and the repair then passes the complete
validation suite and is classified `RECOVER`.

A real, not synthetic, failure was also caught in production data: a
majority of scraped records were arriving with `xG` and `xAG` in place of
`goals`, `assists`, and `starts`, an upstream extraction issue in the
Bright Data collector template, not a bug in this pipeline. Sentinel
correctly refused to treat expected-value metrics as substitutes for
actual-value ones and quarantined those records rather than silently
inserting wrong numbers. See `ERRORS.md` for the full trace.

A separate dataset-level failure was caught when the expected record-count
range was hardcoded as a flat total calibrated to one competition's size.
Moving from the Premier League to the Championship changed the number of
squads from 20 to 24, and the fixed range broke immediately. It's now
derived from however many distinct squads are actually present in the
data (`PLAYERS_PER_SQUAD_RANGE` in `validation/schema.py`), so it adapts
to whichever competition the data came from instead of assuming one.

## Current Project Structure

    football-data-sentinel/
    ├── data/
    │   ├── sample/
    │   │   └── players_raw.json
    │   └── runs/
    ├── frontend/
    ├── scraper/
    │   └── refresh.py
    ├── validation/
    │   ├── ai_healer.py
    │   ├── drift.py
    │   ├── recovery.py
    │   ├── report.py
    │   ├── schema.py
    │   └── status.py
    ├── tests/
    │   ├── test_engine.py
    │   ├── test_failures.py
    │   └── test_schema.py
    ├── pipeline.py
    ├── server.py
    ├── requirements.txt
    ├── ERRORS.md
    └── README.md

## Running the Pipeline

Install the one third-party dependency:

    pip install -r requirements.txt

From the project root:

    python pipeline.py data/raw/latest.json

or against the bundled sample data:

    python pipeline.py

Set `GEMINI_API_KEY` to enable the AI-assisted mapping fallback. Without
it, Sentinel runs on the deterministic path only.

To trigger a fresh scrape via Bright Data:

    python scraper/refresh.py

and to run the HTTP ingestion endpoint the frontend talks to:

    python server.py

## API

`server.py` exposes three routes:

`GET /health` confirms the server is running.

`GET /api/report` returns whatever's currently saved in
`data/runs/latest.json`, the report from the most recent pipeline run.
This is what the dashboard reads on load and on manual refresh.

`POST /api/process` accepts a raw scraper payload directly in the
request body and runs it through the full pipeline synchronously,
returning the resulting report.

`POST /api/refresh` triggers a live Bright Data collection via
`scraper/refresh.py`, then runs the result through the pipeline and
returns the report. This is a real, working, network-bound endpoint,
a full collection can take anywhere from tens of seconds to several
minutes depending on Bright Data's queue, so a client calling it
should show a loading state rather than assume a fast response.

## AI Disclosure

AI assistance (Claude) was used throughout this project's development,
for debugging, architectural review, writing and fixing tests, and
implementing the AI-assisted recovery fallback described above. Every
change was run and verified against real data and the real test suite
before being adopted, not accepted on faith, several proposed changes
from AI assistance were rejected or corrected after verification
surfaced real problems with them (documented in `ERRORS.md`). The
author understands the full architecture and can explain any part of
it: why validation, drift detection, and recovery are separate
concerns, why the AI fallback is bounded by a hard-coded blocklist it
cannot override, and why several specific bugs (wrong competition ID,
a stale range check, a hardcoded record-count assumption) existed and
how each was found and fixed.