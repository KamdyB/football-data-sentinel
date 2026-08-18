# Sentinel — Engineering Error Log

> This document records significant failures encountered while building
> Football Data Sentinel. Errors are preserved intentionally as part of the
> project's engineering history and debugging evidence.

---

## Error Log

### ERR-001 — FBref CSV contained unexpected divider/header rows

**Stage:** Raw data ingestion  
**Status:** Resolved

**Symptom**

The downloaded FBref dataset contained rows that did not represent actual
player records, including blank/divider/header-style rows.

**Expected**

Every row in the raw dataset should represent one player record.

**Actual**

The dataset contained structural rows mixed into the player data.

**Root cause**

FBref's exported table structure contains formatting/header artifacts that
are not obvious when viewing the rendered webpage.

**Resolution**

Investigated the raw dataset and identified the structural pattern before
cleaning the data.

**Engineering lesson**

Do not assume that a webpage's visual table representation is equivalent to
its machine-readable data representation.

**Why this matters to Sentinel**

This became one of the motivations for building validation around the
scraper output rather than trusting successful extraction alone.

---

### ERR-002 — `Unnamed` columns appeared in the FBref dataset

**Stage:** Data ingestion / cleaning  
**Status:** Resolved

**Symptom**

The imported CSV contained multiple columns named `Unnamed`.

**Expected**

Columns should correspond to meaningful football statistics.

**Actual**

FBref's multi-level/header structure produced unnamed columns during import.

**Resolution**

Inspected the raw structure and combined the FBref headers before applying
normal cleaning and type conversion.

**Engineering lesson**

Schema interpretation must happen before generic cleaning.

---

### ERR-003 — Numeric conversion encountered incompatible values

**Stage:** Data cleaning  
**Status:** Resolved

**Symptom**

Some statistical columns could not immediately be treated as numeric.

**Expected**

Statistical fields should contain numeric values suitable for validation and
analysis.

**Actual**

Raw scraped values included representations that required conversion.

**Resolution**

Implemented reusable numeric conversion utilities and applied them to the
appropriate fields.

**Engineering lesson**

Scraped data should be treated as untrusted input even when the source is
considered reliable.

---

### ERR-004 — `TypeError: 'method' object is not subscriptable`

**Stage:** Data analysis  
**Status:** Resolved

**Symptom**

Code attempted to subscript an object that was actually a method.

**Expected**

The expression should return a subscriptable value.

**Actual**

A method reference was being treated as though its result had already been
called.

**Root cause**

Incorrect method invocation.

**Resolution**

Inspected the expression and corrected the method call.

**Engineering lesson**

When working with pandas objects, distinguish carefully between a method
itself and the value returned by calling that method.

---

### ERR-005 — `data/runs` directory did not exist

**Stage:** Run reporting  
**Status:** Resolved

**Symptom**

The pipeline attempted to write a run report into `data/runs/`, but the
directory did not exist.

**Expected**

The pipeline should successfully persist a run report.

**Actual**

File creation failed because the destination directory had not been
created.

**Resolution**

Created the required directory before writing run reports.

**Engineering lesson**

A file path being valid does not guarantee that its parent directory exists.
Production code should explicitly manage required output directories.

---

### ERR-006 — PowerShell `echo.` command behaved unexpectedly

**Stage:** Development environment  
**Status:** Resolved

**Symptom**

A shell command used to create/format files behaved differently in
PowerShell than expected.

**Expected**

The command should create the intended output.

**Actual**

PowerShell interpreted the command differently from the expected shell
syntax.

**Resolution**

Used PowerShell-compatible commands instead.

**Engineering lesson**

Shell commands are environment-dependent. Reproducible project instructions
should specify the expected shell or use cross-platform Python/file APIs.

---

### ERR-007 — `required_fields` / `REQUIRED_FIELDS` was not defined

**Stage:** Schema testing  
**Status:** Resolved

**Symptom**

The controlled test attempted to use `REQUIRED_FIELDS`, but the name was not
available in the test file.

**Expected**

The test should have access to the project's canonical schema definition.

**Actual**

The constant had not been imported.

**Resolution**

Imported `REQUIRED_FIELDS` from `validation.schema`.

**Engineering lesson**

The schema should have one source of truth. Tests should import the project's
actual schema rather than recreate it locally.

---

### ERR-008 — Drift test initially returned no drift

**Stage:** Schema drift detection  
**Status:** Expected test result

**Expected**

No drift should be detected in a valid record.

**Resolution**

Confirmed this was the correct control case before introducing a deliberately
broken record.

**Engineering lesson**

A good failure test needs a known-good control case. Otherwise it is
impossible to distinguish a broken validator from a correctly passing record.

---

### ERR-009 — Deliberate `games` → `appearances` schema drift

**Stage:** Schema drift detection  
**Status:** Detected successfully

**Test input**

The expected field:

```text
games
was replaced with:

appearances

Observed

{
    'missing': ['games'],
    'unexpected': ['appearances'],
    'detected': True
}

Expected

Sentinel should identify both the missing expected field and the unexpected incoming field.

Result

PASS.

Engineering lesson

Sentinel can distinguish structural schema drift from ordinary record-level validation errors.

### ERR-010 — Low-confidence mapping produced RECOVER

Stage: Failure classification / recovery
Status: Identified and corrected

Symptom

The mapping:

appearances → games

received a low similarity score:

0.375

but the original status classifier returned:

Status.RECOVER

Problem

RECOVER implied that recovery had actually succeeded, even though only a possible mapping had been discovered.

Why this was dangerous

The system was reporting an intended action as a completed outcome.

Resolution

Changed the state-machine logic so that drift alone cannot produce RECOVER.

A repair must:

Pass the confidence threshold.

Actually be applied.

Be revalidated successfully.

Otherwise the record is escalated to QUARANTINE.

Engineering lesson

A status must describe an observed outcome, not the system's intention.

ERR-011 — attempt_repair() reported success before revalidation

Stage: Recovery engine
Status: Corrected

Symptom

attempt_repair() declared:

success: True

immediately after renaming the field.

Problem

A syntactically successful rename does not prove that the resulting record is valid.

Resolution

Repair now follows:

confidence gate
      ↓
copy record
      ↓
apply mapping
      ↓
validate repaired record
      ↓
success / refusal

RECOVER is only possible after successful revalidation.

Engineering lesson

Self-healing requires verification. A repair that has not been validated is only a proposed repair.

ERR-012 — classify_status() lacked repair outcome

Stage: Pipeline state machine
Status: Corrected

Symptom

Status classification depended on drift detection but did not know whether the attempted repair succeeded.

Problem

Two independent components could disagree:

drift detected → RECOVER
repair failed  → QUARANTINE

Resolution

classify_status() now receives the repair result.

The intended relationship is:

DRIFT
  ↓
REPAIR
  ↓
REVALIDATION
  ↓
SUCCESS → RECOVER
FAILURE → QUARANTINE

Engineering lesson

Final state should be determined from the actual pipeline outcome, not from an earlier prediction.

ERR-013 — EXPECTED_FIELDS import failure

Stage: Automated tests
Status: Resolved

Error

ImportError: cannot import name 'EXPECTED_FIELDS'
from 'validation.drift'

Root cause

The test suite attempted to import a constant that did not exist in validation.drift.

The project's actual schema definition was already located in:

validation.schema.REQUIRED_FIELDS

Resolution

Changed the import to:

from validation.schema import REQUIRED_FIELDS
from validation.drift import detect_drift, suggest_mapping

And changed:

detect_drift(record, EXPECTED_FIELDS)

to:

detect_drift(record, REQUIRED_FIELDS)

Engineering lesson

Do not invent parallel constants for tests. Tests should consume the same canonical contract used by the application.