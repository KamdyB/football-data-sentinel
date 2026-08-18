import json
from pathlib import Path
from datetime import datetime, timezone

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
from validation.status import classify_status
from validation.report import build_run_report


def validate_player(player: dict) -> list[str]:
    """Run all record-level validation checks."""
    errors = []

    errors += validate_record(player)
    errors += check_text_fields(player)
    errors += check_numeric_fields(player)
    errors += check_ranges(player)
    errors += check_relationships(player)

    return errors


def run_pipeline(input_path: str) -> dict:
    # ---------------------------------------------------------
    # 1. LOAD RAW DATA
    # ---------------------------------------------------------
    with open(input_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    raw_players = data[0]["players"]

    # ---------------------------------------------------------
    # 2. REMOVE STRUCTURAL / NON-PLAYER ROWS
    # ---------------------------------------------------------
    players = [
        player
        for player in raw_players
        if is_player_row(player)
    ]

    # ---------------------------------------------------------
    # 3. VALIDATE EVERY PLAYER
    # ---------------------------------------------------------
    record_results = []
    validation_errors = []

    for i, player in enumerate(players):
        errors = validate_player(player)

        record_results.append({
            "index": i,
            "record": player,
            "errors": errors,
        })

        validation_errors.extend(
            f"record {i}: {error}"
            for error in errors
        )

    # ---------------------------------------------------------
    # 4. DATASET-LEVEL VALIDATION
    # ---------------------------------------------------------
    dataset_errors = check_dataset(players)

    validation_errors.extend(
        f"dataset: {error}"
        for error in dataset_errors
    )

    # ---------------------------------------------------------
    # 5. DETECT DRIFT + ATTEMPT SAFE RECOVERY
    # ---------------------------------------------------------
    repair_results = []

    for result in record_results:
        player = result["record"]
        index = result["index"]

        drift_result = detect_drift(
            player,
            REQUIRED_FIELDS,
        )

        if not drift_result["detected"]:
            continue

        # Current recovery.py supports one field rename at a time.
        # Refuse ambiguous multi-field mappings rather than guessing.
        if (
            len(drift_result["missing"]) != 1
            or len(drift_result["unexpected"]) != 1
        ):
            repair_results.append({
                "record": index,
                "attempted": False,
                "success": False,
                "reason": "ambiguous field drift",
                "drift": drift_result,
            })
            continue

        missing_field = drift_result["missing"][0]
        unexpected_field = drift_result["unexpected"][0]

        mapping = suggest_mapping(
            unexpected_field,
            missing_field,
        )

        repair = attempt_repair(
            player,
            mapping,
        )

        repair_results.append({
            "record": index,
            "attempted": True,
            "mapping": mapping,
            **repair,
        })

    # ---------------------------------------------------------
    # 6. DETERMINE RUN-LEVEL DRIFT
    # ---------------------------------------------------------
    drifted_records = []

    for result in record_results:
        drift_result = detect_drift(
            result["record"],
            REQUIRED_FIELDS,
        )

        if drift_result["detected"]:
            drifted_records.append(drift_result)

    if drifted_records:
        drift_result = {
            "detected": True,
            "missing": sorted({
                field
                for drift in drifted_records
                for field in drift["missing"]
            }),
            "unexpected": sorted({
                field
                for drift in drifted_records
                for field in drift["unexpected"]
            }),
        }
    else:
        drift_result = {
            "detected": False,
            "missing": [],
            "unexpected": [],
        }

    # ---------------------------------------------------------
    # 7. DETERMINE RECOVERY RESULT
    # ---------------------------------------------------------
    if repair_results:
        all_recovered = all(
            result["success"]
            for result in repair_results
        )

        repair_result = {
            "attempted": True,
            "success": all_recovered,
            "records": repair_results,
        }
    else:
        repair_result = None

    # ---------------------------------------------------------
    # 8. FINAL STATUS
    # ---------------------------------------------------------
    status = classify_status(
        validation_errors,
        drift_result,
        repair_result,
    )

    # ---------------------------------------------------------
    # 9. BUILD RUN REPORT
    # ---------------------------------------------------------
    valid_count = sum(
        1
        for result in record_results
        if not result["errors"]
    )

    report = build_run_report(
        raw_count=len(raw_players),
        valid_count=valid_count,
        validation_errors=validation_errors,
        drift_result=drift_result,
        repair_result=repair_result,
        status=status,
    )

    # ---------------------------------------------------------
    # 10. PERSIST RUN REPORT
    # ---------------------------------------------------------
    runs_dir = Path("data/runs")
    runs_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    report_path = runs_dir / f"{timestamp}.json"

    with open(
        report_path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            report,
            file,
            indent=2,
        )

    return report


if __name__ == "__main__":
    report = run_pipeline(
        "data/sample/players_raw.json"
    )

    print(json.dumps(report, indent=2))