def detect_drift(record: dict, expected_fields: list[str]) -> dict:
    """Compare record fields with the expected schema."""
    actual_fields = set(record.keys())
    expected_fields = set(expected_fields)

    missing = sorted(expected_fields - actual_fields)
    unexpected = sorted(actual_fields - expected_fields)

    return {
        "missing": missing,
        "unexpected": unexpected,
        "detected": bool(missing or unexpected),
    }

from difflib import SequenceMatcher


def suggest_mapping(unexpected_field: str, missing_field: str) -> dict:
    """Suggest whether an unexpected field could replace a missing field."""
    confidence = SequenceMatcher(
        None,
        unexpected_field.lower(),
        missing_field.lower(),
    ).ratio()

    return {
        "unexpected_field": unexpected_field,
        "missing_field": missing_field,
        "confidence": round(confidence, 3),
    }