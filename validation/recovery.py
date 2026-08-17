from validation.schema import (
    validate_record, check_text_fields,
    check_numeric_fields, check_ranges,
    check_relationships,
    )


def attempt_repair(record: dict, mapping: dict, confidence_threshold: float = 0.85) -> dict:
    """Attempt a safe field rename without modifying the original record."""
    confidence = mapping["confidence"]

    if confidence < confidence_threshold:
        return {
            "success": False,
            "reason": "confidence below threshold",
            "record": record.copy(),
            }

    old_field = mapping["unexpected_field"]
    new_field = mapping["missing_field"]

    repaired_record = record.copy()

    if old_field not in repaired_record:
        return {
            "success": False,
            "reason": "unexpected field not present in record",
            "record": repaired_record,
            }

    repaired_record[new_field] = repaired_record.pop(old_field)

    remaining_errors = (
        validate_record(repaired_record)
        + check_text_fields(repaired_record)
        + check_numeric_fields(repaired_record)
        + check_ranges(repaired_record)
        + check_relationships(repaired_record)
        )

    if remaining_errors:
        return {
            "success": False,
            "reason": "repaired record still fails validation",
            "record": record.copy(),
            "errors": remaining_errors,
            }

    return {
        "success": True,
        "reason": "field mapping applied and revalidated",
        "record": repaired_record,
        }