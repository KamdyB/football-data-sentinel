import json
from pathlib import Path

from validation.schema import (
    REQUIRED_FIELDS,
    validate_record,
    check_text_fields,
    check_numeric_fields,
    check_ranges,
    check_relationships,
    check_dataset,
    is_player_row,
    )
from validation.drift import detect_drift, suggest_mapping
from validation.recovery import attempt_repair
from validation.status import classify_status, Status
from validation.report import build_run_report


def validate_player(player: dict) -> list[str]:
    """Run all record-level validation checks."""
    return (
        validate_record(player)
        + check_text_fields(player)
        + check_numeric_fields(player)
        + check_ranges(player)
        + check_relationships(player)
        )


def process_player(player: dict) -> dict:
    """Run one record through validation, drift detection, and repair.
    Returns the final status alongside the evidence that produced it."""
    errors = validate_player(player)
    drift = detect_drift(player, REQUIRED_FIELDS)

    repair = None
    if drift["detected"]:
        # recovery.py handles one field rename at a time. More than one
        # missing or unexpected field means we can't know which unexpected
        # field maps to which missing one, so we refuse rather than guess.
        if len(drift["missing"]) == 1 and len(drift["unexpected"]) == 1:
            mapping = suggest_mapping(drift["unexpected"][0], drift["missing"][0])
            repair = attempt_repair(player, mapping)
        else:
            repair = {"success": False, "reason": "ambiguous field drift"}

    status = classify_status(errors, drift, repair)
    final_record = repair["record"] if (repair and repair.get("success")) else player

    return {
        "status": status,
        "record": final_record,
        "errors": errors,
        "drift": drift,
        "repair": repair,
        }


def run_pipeline(input_path: str) -> dict:
    with open(input_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    raw_players = data[0]["players"]
    players = [p for p in raw_players if is_player_row(p)]

    results = [process_player(p) for p in players]

    trusted = [r["record"] for r in results if r["status"] in (Status.PASS, Status.RECOVER)]
    quarantined = [
        {
            "record": r["record"],
            "status": r["status"].value,
            "errors": r["errors"],
            "drift": r["drift"],
            "repair": r["repair"],
            }
        for r in results if r["status"] not in (Status.PASS, Status.RECOVER)
        ]
    recovered_count = sum(1 for r in results if r["status"] == Status.RECOVER)
    all_errors = [error for r in results for error in r["errors"]]

    dataset_errors = check_dataset(players)

    # Per-record status already decides trusted vs quarantined. This is a
    # coarser run-level summary: a dataset problem outranks everything,
    # then any quarantine at all means the run isn't fully clean.
    if dataset_errors:
        overall_status = Status.FAIL
    elif quarantined:
        overall_status = Status.QUARANTINE
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

    return report


if __name__ == "__main__":
    report = run_pipeline("data/sample/players_raw.json")
    print(json.dumps(report, indent=2))