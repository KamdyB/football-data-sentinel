# Collection

Data is collected via a custom Bright Data Scraper Studio collector, not
local parsing code. The collector ID is:

    c_msx0vnthdbenf0tf7

Target: fbref.com, EFL Championship 2025-26 stats page. The parser logic
(which HTML table maps to which field) lives in Scraper Studio's hosted
editor, not in this repository. `refresh.py` only triggers that collector
and retrieves its output, it does not scrape anything itself.

Extracted fields: player_name, nation, position, age, squad, games,
starts, minutes, goals, assists.

## Triggering a collection

    python -c "from scraper.refresh import refresh; print(refresh())"

or via `python scraper/refresh.py` directly. This calls Bright Data's
documented `POST /dca/trigger` endpoint, polls `GET /dca/dataset` until
the collection finishes, and saves the result to `data/raw/latest.json`.

Required environment variables: `BRIGHTDATA_API_TOKEN`. Optional:
`BRIGHTDATA_POLL_INTERVAL` (seconds between polls, default 30),
`BRIGHTDATA_MAX_ATTEMPTS` (default 60).

If a collection returns under 400 rows, `refresh()` treats that as
anomalous and retries once before saving anyway, so Sentinel's own
validation can catch and report the anomaly rather than it silently
producing a near-empty dataset.

## A real bug found here, not a hypothetical one

The collector was originally pointed at FBref competition ID 9, the
Premier League, not competition ID 10, the Championship. Every scrape
this session before the fix came back with Premier League squads
(Arsenal, Liverpool, Manchester City) instead of Championship ones. It
went unnoticed until the squad names in the raw JSON were checked
directly, the row count alone looked plausible for either league. Fixed
by pointing `TARGET_URL` at comp 10. Full writeup in `ERRORS.md`.