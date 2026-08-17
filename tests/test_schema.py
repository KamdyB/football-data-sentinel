import json
from validation.schema import (
    validate_record, check_text_fields, 
    check_numeric_fields, check_ranges,
    is_player_row, check_relationships,
    check_dataset
    )

with open("data/sample/players_raw.json", "r", encoding="utf-8") as file:
    data = json.load(file)
players = data[0]["players"]
print(f"Loaded {len(players)} player records.")

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
