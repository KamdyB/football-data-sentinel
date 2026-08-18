import json
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
    """Run one record through validation, drift detection, and repair."""

    errors = validate_player(player)

    drift = detect_drift(player, REQUIRED_FIELDS)

    repair = None

    if drift["missing"]:
        if (
            len(drift["missing"]) == 1
            and len(drift["unexpected"]) == 1
        ):
            mapping = suggest_mapping(
                drift["unexpected"][0],
                drift["missing"][0],
            )

            repair = attempt_repair(player, mapping)

        else:
            repair = {
                "success": False,
                "reason": "ambiguous field drift",
                "record": player.copy(),
            }

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


def run_pipeline(input_path: str) -> dict:
    with open(input_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    raw_players = data[0]["players"]
    players = [p for p in raw_players if is_player_row(p)]
    duplicates = check_duplicates(players)

    results = [process_player(p) for p in players]

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
        )
    report["duplicates"] = duplicates

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
    