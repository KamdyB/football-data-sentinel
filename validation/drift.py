from difflib import SequenceMatcher


FIELD_ALIASES = {
    "appearances": "games",
    "matches_played": "games",
    "minutes_played": "minutes",
    "goals_scored": "goals",
}


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


def suggest_mapping(unexpected_field: str, missing_field: str) -> dict:
    """Suggest whether an unexpected field could replace a missing field."""

    normalized_unexpected = unexpected_field.lower()
    normalized_missing = missing_field.lower()

    # Explicit domain mapping takes precedence over fuzzy matching.
    if FIELD_ALIASES.get(normalized_unexpected) == normalized_missing:
        confidence = 1.0
        method = "trusted_alias"
    else:
        confidence = SequenceMatcher(
            None,
            normalized_unexpected,
            normalized_missing,
        ).ratio()
        method = "fuzzy"

    return {
        "unexpected_field": unexpected_field,
        "missing_field": missing_field,
        "confidence": round(confidence, 3),
        "method": method,
    }