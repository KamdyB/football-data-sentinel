from difflib import SequenceMatcher


FIELD_ALIASES = {
    "appearances": "games",
    "matches_played": "games",
    "minutes_played": "minutes",
    "goals_scored": "goals",
}

# Fields that must never be treated as a stand-in for each other, no matter
# how a fuzzy string score comes out. xG and xAG are expected-value metrics,
# not renamed versions of goals/assists, so a rename-repair between them
# would insert a wrong number rather than fix a missing one. This is a hard
# boundary, checked before any similarity scoring happens.
BLOCKED_PAIRS = {
    ("xg", "goals"), ("xag", "assists"),
    ("xg", "assists"), ("xag", "goals"),
    ("xg", "starts"), ("xag", "starts"),
    ("xg", "games"), ("xag", "games"),
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

    if (normalized_unexpected, normalized_missing) in BLOCKED_PAIRS:
        return {
            "unexpected_field": unexpected_field,
            "missing_field": missing_field,
            "confidence": 0.0,
            "method": "blocked_non_equivalent",
            }

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


def suggest_field_mappings(missing_fields: list[str], unexpected_fields: list[str],
                            confidence_threshold: float = 0.85) -> dict:
    """Score every missing/unexpected pair and greedily assign the best
    non-blocked match above the confidence threshold to each missing field.
    Each unexpected field can only be used once. Returns both the accepted
    mappings and the full candidate list, so a record that can't be safely
    repaired still carries a record of what was tried and why it was
    rejected."""
    candidates = [
        suggest_mapping(unexpected_field, missing_field)
        for missing_field in missing_fields
        for unexpected_field in unexpected_fields
        ]
    candidates.sort(key=lambda candidate: candidate["confidence"], reverse=True)

    used_unexpected = set()
    used_missing = set()
    accepted = []

    for candidate in candidates:
        if candidate["confidence"] < confidence_threshold:
            continue
        if candidate["missing_field"] in used_missing:
            continue
        if candidate["unexpected_field"] in used_unexpected:
            continue

        accepted.append(candidate)
        used_missing.add(candidate["missing_field"])
        used_unexpected.add(candidate["unexpected_field"])

    return {
        "accepted": accepted,
        "candidates": candidates,
        }