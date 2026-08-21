from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

from application.engine import SentinelEngine

from domain.models import (
    RunContext,
    RunStatus,
)

from domain.ports import (
    ArtifactRepository,
    DataSource,
    RecoveryAdvisor,
    RunRepository,
)

from validation.schema import (
    REQUIRED_FIELDS,
    SCHEMA_NAME,
    SCHEMA_VERSION,
    check_dataset,
    check_duplicates,
    is_player_row,
)


class DatasetBaseline:

    def __init__(
        self,
        history: list[int],
        tolerance: float = 0.10,
    ) -> None:

        self.history = history
        self.tolerance = tolerance

    def errors(
        self,
        current_count: int,
    ) -> list[str]:

        if len(self.history) < 3:
            return []

        ordered = sorted(
            self.history
        )

        middle = len(ordered) // 2

        centre = (
            ordered[middle]
            if len(ordered) % 2
            else (
                ordered[middle - 1]
                + ordered[middle]
            ) / 2
        )

        lower = (
            centre
            * (1 - self.tolerance)
        )

        upper = (
            centre
            * (1 + self.tolerance)
        )

        if not lower <= current_count <= upper:
            return [
                (
                    f"record count "
                    f"{current_count} outside "
                    f"historical baseline "
                    f"{lower:.0f}-{upper:.0f}"
                )
            ]

        return []


class SentinelOrchestrator:

    def __init__(
        self,
        *,
        source: DataSource,
        runs: RunRepository,
        artifacts: ArtifactRepository,
        advisor: RecoveryAdvisor | None = None,
        baseline_tolerance: float = 0.10,
        baseline_window: int = 5,
    ) -> None:

        self.source = source
        self.runs = runs
        self.artifacts = artifacts

        self.engine = SentinelEngine(
            advisor
        )

        self.baseline_tolerance = (
            baseline_tolerance
        )

        self.baseline_window = (
            baseline_window
        )

    def run(
        self,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:

        run_id = str(uuid4())
        started_at = self._now()

        source_payload = (
            payload
            if payload is not None
            else self.source.collect()
        )

        input_sha256 = self._sha256(
            source_payload
        )

        context = RunContext(
            run_id=run_id,
            source=(
                self.source.name
                if payload is None
                else "api_payload"
            ),
            schema_name=SCHEMA_NAME,
            schema_version=SCHEMA_VERSION,
            started_at=started_at,
            input_sha256=input_sha256,
        )

        self.runs.start(
            run_id=run_id,
            source=context.source,
            schema_name=context.schema_name,
            schema_version=context.schema_version,
            started_at=started_at,
            input_sha256=input_sha256,
        )

        context.event(
            "run.started",
            run_id=run_id,
            sha256=input_sha256,
        )

        try:

            self.artifacts.write_json(
                run_id,
                "raw.json",
                source_payload,
            )

            context.event(
                "source.collected",
                source=context.source,
            )

            raw_players = self._extract_players(
                source_payload
            )

            context.raw_count = len(
                raw_players
            )

            players = [
                row
                for row in raw_players
                if is_player_row(row)
            ]

            context.player_row_count = len(
                players
            )

            context.event(
                "rows.filtered",
                raw=context.raw_count,
                player_rows=context.player_row_count,
            )

            structural_errors = check_dataset(
                players
            )

            history = (
                self.runs.successful_counts(
                    self.baseline_window
                )
            )

            baseline_errors = (
                DatasetBaseline(
                    history,
                    self.baseline_tolerance,
                ).errors(
                    len(players)
                )
            )

            dataset_errors = (
                structural_errors
                + baseline_errors
            )

            outcomes = (
                self.engine.process_batch(
                    players
                )
            )

            trusted = [
                outcome.record
                for outcome in outcomes
                if outcome.status
                in {
                    RunStatus.PASS,
                    RunStatus.RECOVER,
                    RunStatus.WARNING,
                }
            ]

            quarantined = [
                outcome.as_dict()
                for outcome in outcomes
                if outcome.status
                in {
                    RunStatus.QUARANTINE,
                    RunStatus.FAIL,
                }
            ]

            context.trusted_count = len(
                trusted
            )

            context.recovered_count = sum(
                outcome.status
                == RunStatus.RECOVER
                for outcome in outcomes
            )

            context.quarantined_count = sum(
                outcome.status
                == RunStatus.QUARANTINE
                for outcome in outcomes
            )

            context.failed_count = sum(
                outcome.status
                == RunStatus.FAIL
                for outcome in outcomes
            )

            context.errors.extend(
                dataset_errors
            )

            context.status = (
                self._run_status(
                    outcomes,
                    dataset_errors,
                )
            )

            context.event(
                "validation.completed",
                dataset_errors=len(
                    dataset_errors
                ),
                trusted=context.trusted_count,
                recovered=context.recovered_count,
                quarantined=context.quarantined_count,
                failed=context.failed_count,
            )

            trusted_path = (
                self.artifacts.write_json(
                    run_id,
                    "trusted.json",
                    trusted,
                )
            )

            quarantine_path = (
                self.artifacts.write_json(
                    run_id,
                    "quarantine.json",
                    quarantined,
                )
            )

            report = self._report(
                context=context,
                outcomes=outcomes,
                duplicates=check_duplicates(
                    players
                ),
                dataset_errors=dataset_errors,
                history=history,
                trusted_path=trusted_path,
                quarantine_path=quarantine_path,
            )

            context.finished_at = self._now()

            report["finished_at"] = (
                context.finished_at
            )

            report_path = (
                self.artifacts.write_json(
                    run_id,
                    "report.json",
                    report,
                )
            )

            report["artifacts"]["report"] = (
                str(report_path)
            )

            self.runs.complete(
                report
            )

            context.event(
                "run.completed",
                status=context.status.value,
            )

            return report

        except Exception as exc:

            context.status = RunStatus.FAIL
            context.finished_at = self._now()

            context.errors.append(
                str(exc)
            )

            context.event(
                "run.failed",
                error=str(exc),
            )

            report = self._report(
                context=context,
                outcomes=[],
                duplicates=[],
                dataset_errors=[],
                history=self.runs.successful_counts(
                    self.baseline_window
                ),
                trusted_path=None,
                quarantine_path=None,
            )

            self.runs.complete(
                report
            )

            raise

    @staticmethod
    def _extract_players(
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:

        raw_players = payload.get(
            "players",
            [],
        )

        if not isinstance(
            raw_players,
            list,
        ):
            raise ValueError(
                "'players' must be a list"
            )

        if not all(
            isinstance(player, dict)
            for player in raw_players
        ):
            raise ValueError(
                "'players' must contain "
                "only JSON objects"
            )

        return raw_players

    @staticmethod
    def _run_status(
        outcomes,
        dataset_errors,
    ) -> RunStatus:

        if dataset_errors:
            return RunStatus.FAIL

        statuses = {
            outcome.status
            for outcome in outcomes
        }

        if RunStatus.FAIL in statuses:
            return RunStatus.FAIL

        if RunStatus.QUARANTINE in statuses:
            return RunStatus.QUARANTINE

        if RunStatus.RECOVER in statuses:
            return RunStatus.RECOVER

        if RunStatus.WARNING in statuses:
            return RunStatus.WARNING

        return RunStatus.PASS

    @staticmethod
    def _sha256(
        payload: Any,
    ) -> str:

        import json

        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

        return hashlib.sha256(
            canonical
        ).hexdigest()

    @staticmethod
    def _now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _report(
        *,
        context: RunContext,
        outcomes,
        duplicates,
        dataset_errors,
        history,
        trusted_path,
        quarantine_path,
    ):

        drift = [
            outcome.drift
            for outcome in outcomes
            if outcome.drift.detected
        ]

        repairs = [
            outcome.repair
            for outcome in outcomes
            if outcome.repair.attempted
        ]

        return {
            "run_id": context.run_id,
            "source": context.source,
            "status": context.status.value,
            "started_at": context.started_at,
            "finished_at": context.finished_at,
            "input_sha256": context.input_sha256,

            "schema": {
                "name": context.schema_name,
                "version": context.schema_version,
                "required_fields": REQUIRED_FIELDS,
            },

            "records": {
                "raw": context.raw_count,
                "player_rows": context.player_row_count,
                "final_trusted": context.trusted_count,
                "recovered": context.recovered_count,
                "quarantined": context.quarantined_count,
                "failed": context.failed_count,
            },

            "validation": {
                "passed": (
                    not dataset_errors
                    and context.failed_count == 0
                    and context.quarantined_count == 0
                ),
                "dataset_errors": dataset_errors,
                "record_errors": [
                    error
                    for outcome in outcomes
                    for error in outcome.errors
                ],
            },

            "drift": {
                "detected": bool(drift),
                "missing": sorted({
                    field
                    for item in drift
                    for field in item.missing
                }),
                "unexpected": sorted({
                    field
                    for item in drift
                    for field in item.unexpected
                }),
            },

            "recovery": {
                "attempted": bool(repairs),
                "successful": sum(
                    repair.success
                    for repair in repairs
                ),
                "applied": [
                    mapping
                    for repair in repairs
                    for mapping in repair.applied
                ],
                "methods": sorted({
                    repair.method
                    for repair in repairs
                    if repair.method
                }),
            },

            "baseline": {
                "history": history,
                "window": len(history),
            },

            "duplicates": duplicates,
            "errors": context.errors,
            "events": context.events,

            "artifacts": {
                "trusted": (
                    str(trusted_path)
                    if trusted_path
                    else None
                ),
                "quarantine": (
                    str(quarantine_path)
                    if quarantine_path
                    else None
                ),
            },
        }