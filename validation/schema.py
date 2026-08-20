from collections import Counter

REQUIRED_FIELDS = [
    "player_name", "nation",
    "position", "age",
    "squad", "games",
    "starts", "minutes",
    "goals", "assists",
    ]

NUMERIC_FIELDS = ["age", "games", "starts", "minutes", "goals", "assists"]
TEXT_FIELDS = ["player_name", "nation", "position", "squad"]

RANGE_CHECKS = {
    "age": (15, 45),
    "games": (0, 46),
    "starts": (0, 46),
    "minutes": (0, 4140),  # 46 games x 90 min, matches the games/starts cap above
    "goals": (0, 60),
    "assists": (0, 40),
    }

# Plausible registered squad size band, used to derive an expected total
# record count from however many distinct squads are actually present,
# rather than hardcoding a total that only holds for one competition.
PLAYERS_PER_SQUAD_RANGE = (18, 35)
SCHEMA_NAME = "championship_player_stats"
SCHEMA_VERSION = "1.1"

def validate_record(record: dict) -> list[str]:
    """Return problems found in one player record."""
    errors = []

    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"missing field: {field}")

    return errors


def check_text_fields(record: dict) -> list[str]:
    """Return errors for text fields that aren't strings."""
    errors = []

    for field in TEXT_FIELDS:
        if field not in record:
            continue
        if not isinstance(record[field], str):
            actual = type(record[field]).__name__
            errors.append(f"{field}: expected str, got {actual}")

    return errors


def check_numeric_fields(record: dict) -> list[str]:
    """Return errors for numeric fields that can't convert to a number."""
    errors = []

    for field in NUMERIC_FIELDS:
        if field not in record:
            continue
        value = record[field]
        try:
            float(value)
        except (TypeError, ValueError):
            errors.append(f"{field}: expected numeric string, got {value!r}")

    return errors


def check_types(record: dict) -> list[str]:
    """Run all type checks on one record and combine the results."""
    return check_text_fields(record) + check_numeric_fields(record)

def check_ranges(record: dict) -> list[str]:
    """Return errors for numeric fields outside a plausible range."""
    errors = []

    for field, (low, high) in RANGE_CHECKS.items():
        if field not in record:
            continue
        try:
            value = float(record[field])
        except (TypeError, ValueError):
            continue
        if not (low <= value <= high):
            errors.append(f"{field}: {value} outside range {low}-{high}")

    return errors

def is_player_row(record: dict) -> bool:
    name = record.get("player_name")

    if not isinstance(name, str):
        return False

    name = name.strip()

    return bool(name) and name.lower() != "player"

def check_relationships(record: dict) -> list[str]:
    """Return errors for numeric fields that contradict each other."""
    errors = []

    try:
        games = float(record["games"])
        starts = float(record["starts"])
    except (TypeError, ValueError, KeyError):
        return errors

    if starts > games:
        errors.append(f"starts ({starts}) exceeds games ({games})")

    return errors

def check_record_count(records: list[dict], squad_field: str = "squad") -> list[str]:
    """Return an error if the dataset size is outside a range derived from
    the number of distinct squads actually present. A competition's total
    record count scales with how many squads it has, so this check adapts
    to whatever competition the data came from instead of assuming one
    fixed total."""
    errors = []
    count = len(records)
    squad_count = len({r.get(squad_field) for r in records if r.get(squad_field)})

    if squad_count == 0:
        errors.append("record count check: no squads found in records")
        return errors

    low_per_squad, high_per_squad = PLAYERS_PER_SQUAD_RANGE
    low = squad_count * low_per_squad
    high = squad_count * high_per_squad

    if not (low <= count <= high):
        errors.append(
            f"record count {count} outside expected range {low}-{high} "
            f"for {squad_count} squads"
            )

    return errors

def check_field_not_all_empty(records: list[dict], field: str) -> list[str]:
    """Return an error if every record is missing this field's value."""
    errors = []
    values = [r.get(field) for r in records]

    if all(v in (None, "") for v in values):
        errors.append(f"{field}: every record is empty or missing")

    return errors

def check_dataset(records: list[dict]) -> list[str]:
    """Run all dataset-level checks and combine the results."""
    errors = check_record_count(records)

    for field in REQUIRED_FIELDS:
        errors += check_field_not_all_empty(records, field)

    return errors

def check_duplicates(records: list[dict], name_field: str = "player_name",
                      group_field: str = "squad") -> list[dict]:
    """Return values in name_field appearing more than once, grouped by
    group_field. In this schema that means players appearing under more
    than one squad, usually a mid-season transfer. A group_field repeated
    identically for the same name_field value suggests the same row was
    scraped twice rather than a real transfer."""
    grouped = {}

    for record in records:
        identity = (record.get(name_field) or "").strip().lower()
        group = (record.get(group_field) or "").strip()

        if not identity:
            continue

        grouped.setdefault(identity, []).append(group)

    duplicates = []
    for identity, groups in grouped.items():
        if len(groups) > 1:
            duplicates.append({
                name_field: identity,
                f"{group_field}s": groups,
                "count": len(groups),
                "likely_transfer": len(set(groups)) > 1,
            })

    return duplicates