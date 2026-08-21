from __future__ import annotations

from pathlib import Path

from application.engine import (
    SentinelEngine,
)

from application.orchestrator import (
    SentinelOrchestrator,
)

from domain.models import (
    RunStatus,
)

from storage.artifacts import (
    FileArtifactRepository,
)

from storage.runs import (
    SQLiteRunRepository,
)

from validation.drift import (
    suggest_mapping,
)

from validation.recovery import (
    attempt_repair,
)

from validation.schema import (
    check_dataset,
    check_relationships,
)


GOOD_RECORD = {
    "player_name": "Test Player",
    "nation": "eng",
    "position": "MF",
    "age": 24,
    "squad": "Test FC",
    "games": 30,
    "starts": 25,
    "minutes": 2200,
    "goals": 5,
    "assists": 3,
}


def payload(
    count: int = 551,
) -> dict:

    return {
        "players": [
            GOOD_RECORD
            | {
                "player_name":
                    f"Player {i}"
            }
            for i in range(count)
        ]
    }


def test_semantically_distinct_fields_are_blocked():

    record = GOOD_RECORD.copy()

    del record["goals"]
    del record["assists"]

    record["xG"] = "0.4"
    record["xAG"] = "0.2"

    result = (
        SentinelEngine()
        .process_record(
            record,
            {},
        )
    )

    assert (
        result.status
        is RunStatus.QUARANTINE
    )


def test_high_confidence_repair_succeeds():

    record = GOOD_RECORD.copy()

    record["Games"] = (
        record.pop("games")
    )

    mapping = suggest_mapping(
        "Games",
        "games",
    )

    repair = attempt_repair(
        record,
        mapping,
    )

    assert repair["success"] is True
    assert "games" in repair["record"]


def test_dynamic_baseline_rejects_large_count_shift(
    tmp_path: Path,
):

    repo = SQLiteRunRepository(
        str(
            tmp_path
            / "runs.db"
        )
    )

    artifacts = (
        FileArtifactRepository(
            str(
                tmp_path
                / "artifacts"
            )
        )
    )

    class Source:

        name = "test"

        def collect(self):
            return payload(551)

    pipeline = SentinelOrchestrator(
        source=Source(),
        runs=repo,
        artifacts=artifacts,
    )

    for _ in range(3):
        pipeline.run()

    class SmallSource:

        name = "test"

        def collect(self):
            return payload(100)

    pipeline = SentinelOrchestrator(
        source=SmallSource(),
        runs=repo,
        artifacts=artifacts,
    )

    report = pipeline.run()

    assert (
        report["status"]
        == "FAIL"
    )

    assert any(
        "historical baseline"
        in error
        for error
        in report[
            "validation"
        ][
            "dataset_errors"
        ]
    )


def test_full_pipeline_persists_one_run_identity(
    tmp_path: Path,
):

    repo = SQLiteRunRepository(
        str(
            tmp_path
            / "runs.db"
        )
    )

    artifacts = (
        FileArtifactRepository(
            str(
                tmp_path
                / "artifacts"
            )
        )
    )

    class Source:

        name = "test"

        def collect(self):
            return payload(551)

    report = (
        SentinelOrchestrator(
            source=Source(),
            runs=repo,
            artifacts=artifacts,
        )
        .run()
    )

    run_id = report[
        "run_id"
    ]

    stored = repo.get(
        run_id
    )

    assert (
        stored["run_id"]
        == run_id
    )

    assert (
        stored["status"]
        == report["status"]
    )

    assert (
        tmp_path
        / "artifacts"
        / run_id
        / "raw.json"
    ).exists()

    assert (
        tmp_path
        / "artifacts"
        / run_id
        / "trusted.json"
    ).exists()

    assert (
        tmp_path
        / "artifacts"
        / run_id
        / "quarantine.json"
    ).exists()

    assert (
        tmp_path
        / "artifacts"
        / run_id
        / "report.json"
    ).exists()


def test_schema_has_no_static_dataset_count_policy():

    source = Path(
        "validation/schema.py"
    ).read_text(
        encoding="utf-8"
    )

    assert (
        "EXPECTED_RECORD_RANGE"
        not in source
    )

    assert (
        check_dataset(
            [GOOD_RECORD]
        )
        == []
    )

    assert (
        check_relationships(
            GOOD_RECORD
        )
        == []
    )