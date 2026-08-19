# Error Log

Real errors encountered while building the Sentinel validation
pipeline, in the order they happened. Kept on purpose, since
catching and fixing these is part of the evidence that the
system's decisions can be trusted.

Each entry: what was run, what went wrong, what was expected,
what fixed it, what it taught.

## 1. ModuleNotFoundError: No module named 'validation'

Command run: python tests/test_schema.py

Running the file directly only adds its own folder to Python's
search path, not the repo root, so the import couldn't find
validation/. Fixed by running as a module from the repo root
instead: python -m tests.test_schema

Dotted imports need the project root on the path. Running a file
directly and running it as a module are not the same thing.

## 2. Type checks failed on every field

EXPECTED_TYPES checked for real Python int/float, but scraped
values arrive as strings ("24", not 24), so every record failed
every check. Fixed by replacing direct type checks with
conversion checks: numeric fields are validated by attempting
float(value) inside a try/except, not by checking raw Python
type.

Scraped data should be validated for what it actually is, not for
what the underlying concept usually looks like.

## 3. Blank divider rows in scraped data

Every 26th record failed all six numeric checks at once, all
fields returning None. Printed one directly and found it was a
fully blank row, not a real player. FBref's combined stats table
includes blank divider rows between squads. Fixed by adding
is_player_row() to filter these before validation runs. 573 raw
rows became 551 real player records.

A webpage's visible table and its underlying data structure
aren't always the same thing.

## 4. Filtering logic placed inside the loop

The filtering message printed 551 times instead of once, because
the filter was written inside the for loop instead of before it.
Fixed by moving filtering to run once, before the loop.

## 5. classify_status() and attempt_repair() disagreed

For a low-confidence drift mapping, status printed RECOVER while
the repair result separately said success: False. classify_status
was being called before attempt_repair had run, so it made a
decision without knowing whether repair had actually succeeded.
Fixed by reordering the pipeline so repair always runs first, and
its real result is passed into classify_status.

A status should describe an outcome that already happened, not a
prediction of what might happen.

## 6. FileNotFoundError writing the run report

data/runs/ did not exist, so writing the report file failed.
Fixed by creating the folder before running.

A valid file path doesn't guarantee its parent folder exists.

## 7. echo. not recognized in PowerShell

echo. is a Windows CMD trick, not valid PowerShell. Not needed in
the end, since a real run already put a file in the folder.
PowerShell's equivalent, if needed later, is New-Item.

Shell syntax is environment-specific and should be checked against
the shell actually being used.

## 8. ImportError: cannot import name 'EXPECTED_FIELDS'

The test file tried to import a constant that was never defined.
The project's real constant for this purpose is REQUIRED_FIELDS,
already defined in schema.py. Fixed by importing REQUIRED_FIELDS
from validation.schema instead.

Tests should use the project's one real schema definition, not a
second name invented for convenience.

## 9. ImportError: cannot import name 'SCHEMA_NAME'

report.py was written to import SCHEMA_NAME and SCHEMA_VERSION
before those constants existed in schema.py. Fixed by adding both
constants to schema.py.

## 10. Duplicate constants in schema.py

NUMERIC_FIELDS and TEXT_FIELDS were each defined twice in the
same file, with identical values. Fixed by removing the duplicate
pair.

## 11. run_pipeline only accepted a file path

server.py needed to hand the pipeline a parsed JSON payload
directly, not a file path, but run_pipeline only knew how to open
a file. Caught before it reached a live request. Fixed by making
run_pipeline accept either a string path or a dict, checking the
input type before deciding how to load the data.

An API boundary and a command-line entry point don't always want
the same input shape. The function underneath both needs to
handle both, not assume one caller's convention.

## 12. Extra fields were quarantining otherwise valid records

If the source added a new field without removing anything
required, drift detection correctly flagged it as unexpected, but
classify_status treated any drift the same way and quarantined
the whole record even though nothing was actually missing or
broken. Fixed by splitting the logic: only a missing required
field triggers repair-or-quarantine, an extra field alone produces
WARNING instead, and the record stays in the trusted set.

A validator should fail on a real problem, not on the source
simply changing in a way that isn't a problem.

## 13. check_duplicates never flagged real duplicates

check_duplicates keyed on (player_name, squad) together. A player
appearing under two different squads, the real case for a
mid-season transfer, produced two different keys instead of one
repeated key, so the count never exceeded 1 and nothing was ever
flagged, even against a real dataset known to contain transfers.

Fixed by grouping on player_name alone and collecting every squad
associated with it. A name appearing more than once is now
correctly reported, with likely_transfer distinguishing different
squads (a transfer) from the same squad repeated (a probable
scraping duplicate).

Also fixed a related null-safety gap: record.get(field, "") only
applies its default when the key is missing, not when the key is
present with a None value, which could throw AttributeError on
.strip(). Switched to record.get(field) or "" to cover both cases.

Grouping the wrong fields together produces a function that runs
without error and returns a plausible-looking empty result. An
empty result is not the same as a correct one, and deserves the
same suspicion as an error message would.