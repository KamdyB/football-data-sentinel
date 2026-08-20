import json
import os
import time
from pathlib import Path
import sys

from validation.schema import (
    REQUIRED_FIELDS,
    validate_record,
    check_text_fields,
    check_numeric_fields,
    check_ranges,
    check_relationships,
    check_dataset,
    check_duplicates,
    is_player_row,
    )
from validation.drift import detect_drift, suggest_field_mappings
from validation.recovery import attempt_multi_repair
from validation.status import classify_status, Status
from validation.report import build_run_report

AI_HEALING_ENABLED = bool(os.environ.get("GEMINI_API_KEY"))
AI_CALLS_PER_MINUTE = 5  # Gemini free tier ceiling


def validate_player(player: dict) -> list[str]:
    """Run all record-level validation checks."""
    return (
        validate_record(player)
        + check_text_fields(player)
        + check_numeric_fields(player)
        + check_ranges(player)
        + check_relationships(player)
        )


def _drift_signature(drift: dict) -> tuple:
    return (tuple(sorted(drift["missing"])), tuple(sorted(drift.get("unexpected", []))))


def _precompute_ai_mappings(players: list[dict]) -> dict:
    """One AI call per distinct drift signature in the dataset, not one per
    record. Schema drift is structural: every record sharing the same
    missing/unexpected fields has the same underlying cause, so the same
    question doesn't need asking hundreds of times. Also keeps the run
    under the Gemini free tier's requests-per-minute ceiling."""
    if not AI_HEALING_ENABLED:
        return {}

    from validation.ai_healer import suggest_ai_mapping

    signatures = {}
    for player in players:
        drift = detect_drift(player, REQUIRED_FIELDS)
        if not drift["missing"]:
            continue
        sig = _drift_signature(drift)
        signatures.setdefault(sig, (drift, player))

    cache = {}
    calls_made = 0

    for sig, (drift, sample_player) in signatures.items():
        mapping_result = suggest_field_mappings(drift["missing"], drift.get("unexpected", []))
        resolved = {m["missing_field"] for m in mapping_result["accepted"]}
        unresolved = [f for f in drift["missing"] if f not in resolved]

        ai_mappings = []
        for missing_field in unresolved:
            safe_candidates = [
                c["unexpected_field"] for c in mapping_result["candidates"]
                if c["missing_field"] == missing_field
                and c["method"] != "blocked_non_equivalent"
                ]
            if not safe_candidates:
                continue

            if calls_made > 0 and calls_made % AI_CALLS_PER_MINUTE == 0:
                time.sleep(65)

            suggestion = suggest_ai_mapping(missing_field, safe_candidates, sample_player)
            calls_made += 1
            if suggestion:
                ai_mappings.append(suggestion)

        cache[sig] = ai_mappings

    return cache


def _attempt_ai_repair(player: dict, drift: dict, mapping_result: dict, ai_cache: dict) -> dict:
    ai_mappings = ai_cache.get(_drift_signature(drift), [])

    if not ai_mappings:
        return attempt_multi_repair(player, mapping_result)

    combined = {
        "accepted": mapping_result["accepted"] + ai_mappings,
        "candidates": mapping_result["candidates"] + ai_mappings,
        }
    return attempt_multi_repair(player, combined)


def process_player(player: dict, ai_cache: dict | None = None) -> dict:
    """Run one record through validation, drift detection, and repair."""
    errors = validate_player(player)

    drift = detect_drift(player, REQUIRED_FIELDS)

    repair = None

    if drift["missing"]:
        mapping_result = suggest_field_mappings(
            drift["missing"],
            drift.get("unexpected", []),
        )
        repair = attempt_multi_repair(player, mapping_result)

        if not repair["success"] and AI_HEALING_ENABLED:
            repair = _attempt_ai_repair(player, drift, mapping_result, ai_cache or {})

    final_record = (
        repair["record"]
        if repair is not None and repair.get("success")
        else player
    )

    if repair is not None and repair.get("success"):
        final_errors = validate_player(final_record)
    else:
        final_errors = errors

    status = classify_status(
        final_errors,
        drift,
        repair,
    )

    return {
        "status": status,
        "record": final_record,
        "errors": final_errors,
        "drift": drift,
        "repair": repair,
    }


def run_pipeline(input_source) -> dict:
    """Accept a raw JSON file path or a direct scraper payload."""
    
    if isinstance(input_source, str):
        with open(input_source, "r", encoding="utf-8") as file:
             data = json.load(file)
    elif isinstance(input_source, (dict, list)):
        data = input_source
    else:
        raise ValueError("pipeline input must be a file path, JSON object, or JSON list")

    if isinstance(data, list):
       if not data or not isinstance(data[0], dict):
           raise ValueError("JSON list must contain a player payload object")
       raw_players = data[0].get("players", [])
    elif isinstance(data, dict):
       raw_players = data.get("players", [])
    else:
       raise ValueError("unsupported JSON payload")
      
    if not isinstance(raw_players, list):
       raise ValueError("'players' must be a list")

    players = [p for p in raw_players if is_player_row(p)]
    duplicates = check_duplicates(players)

    ai_cache = _precompute_ai_mappings(players)
    results = [process_player(p, ai_cache) for p in players]

    trusted = [r["record"] for r in results if r["status"] in (Status.PASS, Status.RECOVER, Status.WARNING,)]
    quarantined = [
        {
            "record": r["record"],
            "status": r["status"].value,
            "errors": r["errors"],
            "drift": r["drift"],
            "repair": r["repair"],
            }
        for r in results if r["status"] in (Status.QUARANTINE, Status.FAIL,)
        ]
    recovered_count = sum(1 for r in results if r["status"] == Status.RECOVER)
    all_errors = [error for r in results for error in r["errors"]]

    dataset_errors = check_dataset(players)

    # Per-record status already decides trusted vs quarantined. This is a
    # coarser run-level summary: a dataset problem outranks everything,
    # then any quarantine at all means the run isn't fully clean.
    record_statuses = [r["status"] for r in results]

    if dataset_errors:
        overall_status = Status.FAIL
    elif Status.QUARANTINE in record_statuses:
        overall_status = Status.QUARANTINE
    elif Status.FAIL in record_statuses:
        overall_status = Status.FAIL
    elif Status.RECOVER in record_statuses:
        overall_status = Status.RECOVER
    elif Status.WARNING in record_statuses:
        overall_status = Status.WARNING
    else:
        overall_status = Status.PASS

    drifted = [r["drift"] for r in results if r["drift"]["detected"]]
    run_drift = {
        "detected": bool(drifted),
        "missing": sorted({field for d in drifted for field in d["missing"]}),
        "unexpected": sorted({field for d in drifted for field in d["unexpected"]}),
        }

    report = build_run_report(
        raw_count=len(raw_players),
        player_row_count=len(players),
        final_trusted_count=len(trusted),
        recovered_count=recovered_count,
        quarantined_count=len(quarantined),
        validation_errors=all_errors + [f"dataset: {e}" for e in dataset_errors],
        drift_result=run_drift,
         repair_result=None,
        status=overall_status,
        duplicates=duplicates,
        )

    Path("data/processed").mkdir(parents=True, exist_ok=True)
    Path("data/quarantine").mkdir(parents=True, exist_ok=True)
    Path("data/runs").mkdir(parents=True, exist_ok=True)

    with open("data/processed/players.json", "w", encoding="utf-8") as file:
        json.dump(trusted, file, indent=2)

    with open("data/quarantine/players.json", "w", encoding="utf-8") as file:
        json.dump(quarantined, file, indent=2)

    timestamp = report["collected_at"].replace(":", "").replace("-", "").split(".")[0] + "Z"
    with open(f"data/runs/{timestamp}.json", "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    with open("data/runs/latest.json", "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    return report


def print_summary(report: dict) -> None:
    """Human-readable one-glance verdict, for a person, not a machine."""
    status = report["status"].upper()
    records = report["records"]

    print(f"\nSENTINEL RUN — {status}")
    print(f"Source rows:     {records['raw']}")
    print(f"Player rows:     {records['player_rows']}")
    print(f"Trusted:         {records['final_trusted']}")
    print(f"Recovered:       {records['recovered']}")
    print(f"Quarantined:     {records['quarantined']}")

    if status == "PASS":
        print("Dataset is trusted. Safe to use data/processed/players.json.\n")
    elif status == "RECOVER":
        print("Dataset is trusted after automatic repair. See run report for what changed.\n")
    else:
        print("Dataset is NOT fully trusted. Check data/quarantine/players.json before using this dataset.\n")


if __name__ == "__main__":
    input_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "data/raw/latest.json"
    )

    try:
        report = run_pipeline(input_path)
    except FileNotFoundError:
        print(
            f"No raw data found at {input_path}. "
            "Run the scraper first, then refresh."
        )
        sys.exit(1)
    except json.JSONDecodeError:
        print(
            f"{input_path} exists but isn't valid JSON. "
            "The scrape may have failed partway."
        )
        sys.exit(1)

    print_summary(report)