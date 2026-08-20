import json
from validation.schema import (
    validate_record, check_text_fields, 
    check_numeric_fields, check_ranges,
    is_player_row, check_relationships,
    check_dataset, check_duplicates, REQUIRED_FIELDS,
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

repair = attempt_repair(
    broken_player,
    mapping,
    )

print("REPAIR")
print(repair)

status = classify_status(
    validation_errors=[],
    drift_result=drift,
    repair_result=repair,
    )

print("STATUS")
print(status)

players = [p for p in players if is_player_row(p)]
print(f"{len(players)} valid player rows after filtering.")

all_errors = []
for i, player in enumerate(players):
    if not is_player_row(player):
        continue
    errors = validate_record(player)
    errors += check_text_fields(player)
    errors += check_numeric_fields(player)
    errors += check_ranges(player)
    errors += check_relationships(player)

    if errors:
        all_errors.extend(errors)
        print(f"Record {i}: {errors}")

dataset_errors = check_dataset(players)

if not all_errors:
    print("Schema validation passed.")
else:
    print(f"Found {len(all_errors)} schema errors.")

if dataset_errors:
    print(f"Dataset-level issues: {dataset_errors}")
else:
    print("Dataset-level checks passed.")


from datetime import datetime, timezone

report = build_run_report(
    raw_count=len(data[0]["players"]),
    player_row_count=len(players),
    final_trusted_count=len(players) - len(all_errors),
    recovered_count=1 if repair["success"] else 0,
    quarantined_count=len(all_errors),
    validation_errors=all_errors + dataset_errors,
    drift_result=drift,
    repair_result=repair,
    status=status,
    duplicates=check_duplicates(players),
    )

timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
with open(f"data/runs/{timestamp}.json", "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)

print("RUN REPORT")
print(json.dumps(report, indent=2))