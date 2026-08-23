from validation.schema import (
    validate_record, check_text_fields,
    check_numeric_fields, check_ranges,
    check_relationships, check_dataset,
    )
from validation.schema import REQUIRED_FIELDS
from validation.drift import detect_drift, suggest_mapping, suggest_field_mappings
from validation.recovery import attempt_repair, attempt_multi_repair
from validation.status import classify_status, Status


GOOD_RECORD = {
    "player_name": "Test Player", "nation": "eng", "position": "MF",
    "age": 24, "squad": "Test FC", "games": 30, "starts": 25,
    "minutes": 2200, "goals": 5, "assists": 3,
    }


def test_missing_field():
    record = GOOD_RECORD.copy()
    del record["age"]
    errors = validate_record(record)
    assert "missing field: age" in errors
    print("test_missing_field: PASS")


def test_wrong_type():
    record = GOOD_RECORD.copy()
    record["goals"] = "four"
    errors = check_numeric_fields(record)
    assert any("goals" in e for e in errors)
    print("test_wrong_type: PASS")


def test_impossible_value():
    record = GOOD_RECORD.copy()
    record["age"] = 200
    errors = check_ranges(record)
    assert any("age" in e for e in errors)
    print("test_impossible_value: PASS")


def test_cross_field_violation():
    record = GOOD_RECORD.copy()
    record["starts"] = 40
    errors = check_relationships(record)
    assert any("exceeds" in e for e in errors)
    print("test_cross_field_violation: PASS")


def test_record_count_drop():
    tiny_dataset = [GOOD_RECORD.copy() for _ in range(5)]
    errors = check_dataset(tiny_dataset)
    assert any("record count" in e for e in errors)
    print("test_record_count_drop: PASS")


def test_low_confidence_repair_refuses():
    record = GOOD_RECORD.copy()
    record["gp"] = record.pop("games")  # short, unrelated-looking name, not a known alias
    drift = detect_drift(record, REQUIRED_FIELDS)
    mapping = suggest_mapping("gp", "games")
    repair = attempt_repair(record, mapping)
    status = classify_status([], drift, repair)

    assert repair["success"] is False
    assert status == Status.QUARANTINE
    print("test_low_confidence_repair_refuses: PASS")


def test_high_confidence_repair_succeeds():
    record = GOOD_RECORD.copy()
    record["Games"] = record.pop("games")  # near-identical name, high similarity
    drift = detect_drift(record, REQUIRED_FIELDS)
    mapping = suggest_mapping("Games", "games")
    repair = attempt_repair(record, mapping)
    status = classify_status([], drift, repair)

    assert repair["success"] is True
    assert status == Status.RECOVER
    print("test_high_confidence_repair_succeeds: PASS")


def test_semantically_distinct_field_never_auto_maps():
    # xG and xAG are expected-value metrics, not renamed goals/assists.
    # Even at whatever fuzzy score they'd score, this pair must be
    # rejected outright, not just below-threshold.
    record = GOOD_RECORD.copy()
    del record["goals"]
    del record["assists"]
    record["xG"] = "0.4"
    record["xAG"] = "0.2"

    drift = detect_drift(record, REQUIRED_FIELDS)
    mapping_result = suggest_field_mappings(drift["missing"], drift["unexpected"])
    repair = attempt_multi_repair(record, mapping_result)

    blocked_methods = {c["method"] for c in mapping_result["candidates"]}
    assert "blocked_non_equivalent" in blocked_methods
    assert repair["success"] is False
    print("test_semantically_distinct_field_never_auto_maps: PASS")


if __name__ == "__main__":
    test_missing_field()
    test_wrong_type()
    test_impossible_value()
    test_cross_field_violation()
    test_record_count_drop()
    test_low_confidence_repair_refuses()
    test_high_confidence_repair_succeeds()
    test_semantically_distinct_field_never_auto_maps()
    print("\nAll failure-taxonomy tests passed.")