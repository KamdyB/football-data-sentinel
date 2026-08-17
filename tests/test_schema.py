import json
from validation.schema import (
    validate_record, check_text_fields, 
    check_numeric_fields, check_ranges,
    is_player_row, check_relationships,
    check_dataset, REQUIRED_FIELDS,
    )

from validation.drift import (
    detect_drift,
    suggest_mapping,
)

from validation.status import (
    Status,
    classify_status,
)

from validation.recovery import (
    attempt_repair,
)

from validation.report import (
    build_run_report,
)

with open("data/sample/players_raw.json", "r", encoding="utf-8") as file:
    data = json.load(file)
players = data[0]["players"]
print(f"Loaded {len(players)} player records.")

player = players[0]
drift = detect_drift(player, REQUIRED_FIELDS)

print("DRIFT TEST")
print(drift)

broken_player = player.copy()

broken_player["appearances"] = broken_player.pop("games")

drift = detect_drift(
    broken_player,
    REQUIRED_FIELDS,
)

print("BROKEN RECORD")
print(drift)

mapping = suggest_mapping(
    "appearances",
    "games",
)

print("MAPPING")
print(mapping)

status = classify_status(
    validation_errors=[],
    drift_result=drift,
)

repair = attempt_repair(
    broken_player,
    mapping,
)

print("REPAIR")
print(repair)


print("STATUS")
print(status)

mapping = {
    "unexpected_field": "appearances",
    "missing_field": "games",
    "confidence": 0.95,
}


players = [p for p in players if is_player_row(p)]
print(f"{len(players)} valid player rows after filtering.")
    
total_errors = 0
for i, player in enumerate(players):
    if not is_player_row(player):
        continue
    errors = validate_record(player)
    errors += check_text_fields(player)
    errors += check_numeric_fields(player)
    errors += check_ranges(player)
    errors += check_relationships(player)
    dataset_errors = check_dataset(players)

    if errors:
        total_errors += len(errors)
        print(f"Record {i}: {errors}")

if total_errors == 0:
    print("Schema validation passed.")
else:
    print(f"Found {total_errors} schema errors.")

if dataset_errors:
    print(f"Dataset-level issues: {dataset_errors}")
else:
    print("Dataset-level checks passed.")
