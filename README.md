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

Not yet built: schema drift detection, automated recovery,
quarantine handling, structured logging. See project roadmap.