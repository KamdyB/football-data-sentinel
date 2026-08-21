from __future__ import annotations

import os
from typing import Any

from domain.models import (
    Drift,
    RecordOutcome,
    Repair,
    RunStatus,
)
from domain.ports import RecoveryAdvisor

from validation.drift import (
    detect_drift,
    suggest_field_mappings,
)

from validation.recovery import (
    attempt_multi_repair,
)

from validation.schema import (
    REQUIRED_FIELDS,
    check_numeric_fields,
    check_ranges,
    check_relationships,
    check_text_fields,
    validate_record,
)

from validation.status import classify_status


RECOVERY_THRESHOLD = float(
    os.getenv(
        "SENTINEL_RECOVERY_THRESHOLD",
        "0.85",
    )
)


def validate_record_completely(
    record: dict[str, Any],
) -> list[str]:

    return (
        validate_record(record)
        + check_text_fields(record)
        + check_numeric_fields(record)
        + check_ranges(record)
        + check_relationships(record)
    )


class SentinelEngine:

    def __init__(
        self,
        advisor: RecoveryAdvisor | None = None,
    ) -> None:

        self._advisor = advisor

    def process_batch(
        self,
        players: list[dict[str, Any]],
    ) -> list[RecordOutcome]:

        ai_cache = self._prepare_ai_cache(players)

        return [
            self.process_record(
                player,
                ai_cache,
            )
            for player in players
        ]

    def process_record(
        self,
        player: dict[str, Any],
        ai_cache: dict[
            tuple[
                tuple[str, ...],
                tuple[str, ...],
            ],
            list[dict[str, Any]],
        ],
    ) -> RecordOutcome:

        initial_errors = (
            validate_record_completely(player)
        )

        drift_raw = detect_drift(
            player,
            REQUIRED_FIELDS,
        )

        drift = Drift(
            missing=tuple(
                drift_raw["missing"]
            ),
            unexpected=tuple(
                drift_raw.get(
                    "unexpected",
                    [],
                )
            ),
        )

        if not drift.missing:

            status = RunStatus(
                classify_status(
                    initial_errors,
                    drift_raw,
                    None,
                ).value.upper()
            )

            return RecordOutcome(
                record=player,
                status=status,
                errors=tuple(initial_errors),
                drift=drift,
            )

        mapping = suggest_field_mappings(
            list(drift.missing),
            list(drift.unexpected),
            RECOVERY_THRESHOLD,
        )

        ai_mappings = ai_cache.get(
            self._signature(drift_raw),
            [],
        )

        if ai_mappings:
            mapping = {
                "accepted": (
                    mapping["accepted"]
                    + ai_mappings
                ),
                "candidates": (
                    mapping["candidates"]
                    + ai_mappings
                ),
            }

        repair_raw = attempt_multi_repair(
            player,
            mapping,
        )

        repair = Repair(
            attempted=True,
            success=bool(
                repair_raw.get("success")
            ),
            reason=repair_raw.get("reason"),
            applied=tuple(
                repair_raw.get(
                    "applied",
                    [],
                )
            ),
            candidates=tuple(
                repair_raw.get(
                    "attempted",
                    repair_raw.get(
                        "candidates",
                        mapping.get(
                            "candidates",
                            [],
                        ),
                    ),
                )
            ),
            errors=tuple(
                repair_raw.get(
                    "errors",
                    [],
                )
            ),
            method=(
                "ai+deterministic"
                if ai_mappings
                else "deterministic"
            ),
        )

        final_record = (
            repair_raw.get(
                "record",
                player,
            )
        )

        final_errors = (
            validate_record_completely(
                final_record
            )
            if repair.success
            else initial_errors
        )

        status = RunStatus(
            classify_status(
                final_errors,
                drift_raw,
                repair_raw,
            ).value.upper()
        )

        return RecordOutcome(
            record=final_record,
            status=status,
            errors=tuple(final_errors),
            drift=drift,
            repair=repair,
        )

    def _prepare_ai_cache(
        self,
        players: list[dict[str, Any]],
    ) -> dict[
        tuple[
            tuple[str, ...],
            tuple[str, ...],
        ],
        list[dict[str, Any]],
    ]:

        if self._advisor is None:
            return {}

        requests = []
        signatures = []
        seen = set()

        for player in players:

            drift = detect_drift(
                player,
                REQUIRED_FIELDS,
            )

            if not drift["missing"]:
                continue

            signature = self._signature(
                drift
            )

            if signature in seen:
                continue

            seen.add(signature)

            deterministic = (
                suggest_field_mappings(
                    drift["missing"],
                    drift.get(
                        "unexpected",
                        [],
                    ),
                    RECOVERY_THRESHOLD,
                )
            )

            resolved = {
                item["missing_field"]
                for item
                in deterministic["accepted"]
            }

            unresolved = [
                field
                for field in drift["missing"]
                if field not in resolved
            ]

            candidates = sorted({
                item["unexpected_field"]
                for item
                in deterministic["candidates"]
                if (
                    item["missing_field"]
                    in unresolved
                    and item["method"]
                    != "blocked_non_equivalent"
                )
            })

            if not candidates:
                continue

            requests.append({
                "missing": unresolved,
                "candidates": candidates,
                "sample": player,
            })

            signatures.append(signature)

        if not requests:
            return {}

        batches = self._advisor.suggest_batch(
            requests
        )

        cache = {}

        for index, signature in enumerate(
            signatures
        ):
            cache[signature] = (
                batches[index]
                if index < len(batches)
                else []
            )

        return cache

    @staticmethod
    def _signature(
        drift: dict[str, Any],
    ):
        return (
            tuple(
                sorted(
                    drift["missing"]
                )
            ),
            tuple(
                sorted(
                    drift.get(
                        "unexpected",
                        [],
                    )
                )
            ),
        )