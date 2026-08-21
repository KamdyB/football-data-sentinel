REQUIRED_FIELDS = [
    "player_name",
    "nation",
    "position",
    "age",
    "squad",
    "games",
    "starts",
    "minutes",
    "goals",
    "assists",
]

NUMERIC_FIELDS = [
    "age",
    "games",
    "starts",
    "minutes",
    "goals",
    "assists",
]

TEXT_FIELDS = [
    "player_name",
    "nation",
    "position",
    "squad",
]

RANGE_CHECKS = {
    "age": (15, 45),
    "games": (0, 46),
    "starts": (0, 46),
    "minutes": (0, 3420),
    "goals": (0, 60),
    "assists": (0, 40),
}

SCHEMA_NAME = "championship_player_stats"
SCHEMA_VERSION = "2.0"


def validate_record(record: dict) -> list[str]:
    return [
        f"missing field: {field}"
        for field in REQUIRED_FIELDS
        if field not in record
    ]


def check_text_fields(record: dict) -> list[str]:
    errors = []

    for field in TEXT_FIELDS:
        if field not in record:
            continue

        if not isinstance(record[field], str):
            errors.append(
                f"{field}: expected str, "
                f"got {type(record[field]).__name__}"
            )

    return errors


def check_numeric_fields(record: dict) -> list[str]:
    errors = []

    for field in NUMERIC_FIELDS:
        if field not in record:
            continue

        try:
            float(record[field])
        except (TypeError, ValueError):
            errors.append(
                f"{field}: expected numeric value, "
                f"got {record[field]!r}"
            )

    return errors


def check_ranges(record: dict) -> list[str]:
    errors = []

    for field, (low, high) in RANGE_CHECKS.items():
        if field not in record:
            continue

        try:
            value = float(record[field])
        except (TypeError, ValueError):
            continue

        if not low <= value <= high:
            errors.append(
                f"{field}: {value} outside range {low}-{high}"
            )

    return errors


def is_player_row(record: dict) -> bool:
    name = record.get("player_name")

    if not isinstance(name, str):
        return False

    name = name.strip()

    return bool(name) and name.lower() != "player"


def check_relationships(record: dict) -> list[str]:
    errors = []

    try:
        games = float(record["games"])
        starts = float(record["starts"])
    except (TypeError, ValueError, KeyError):
        return errors

    if starts > games:
        errors.append(
            f"starts ({starts}) exceeds games ({games})"
        )

    return errors


def check_field_not_all_empty(
    records: list[dict],
    field: str,
) -> list[str]:

    if records and all(
        record.get(field) in (None, "")
        for record in records
    ):
        return [
            f"{field}: every record is empty or missing"
        ]

    return []


def check_dataset(records: list[dict]) -> list[str]:
    errors = []

    if not records:
        return ["dataset contains no player rows"]

    for field in REQUIRED_FIELDS:
        errors.extend(
            check_field_not_all_empty(
                records,
                field,
            )
        )

    return errors


def check_duplicates(
    records: list[dict],
    name_field: str = "player_name",
    group_field: str = "squad",
) -> list[dict]:

    grouped = {}

    for record in records:
        identity = (
            record.get(name_field) or ""
        ).strip().lower()

        group = (
            record.get(group_field) or ""
        ).strip()

        if not identity:
            continue

        grouped.setdefault(
            identity,
            [],
        ).append(group)

    duplicates = []

    for identity, groups in grouped.items():
        if len(groups) > 1:
            duplicates.append({
                name_field: identity,
                f"{group_field}s": groups,
                "count": len(groups),
                "likely_transfer": (
                    len(set(groups)) > 1
                ),
            })

    return duplicates