from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class SQLiteRunRepository:

    def __init__(
        self,
        path: str = "data/sentinel.db",
    ) -> None:

        self.path = Path(path)

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._initialize()

    def _connect(
        self,
    ) -> sqlite3.Connection:

        connection = sqlite3.connect(
            self.path,
            timeout=30,
        )

        connection.row_factory = (
            sqlite3.Row
        )

        return connection

    def _initialize(self) -> None:

        with self._connect() as connection:

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    schema_name TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_sha256 TEXT NOT NULL,

                    raw_count INTEGER
                        NOT NULL DEFAULT 0,

                    player_row_count INTEGER
                        NOT NULL DEFAULT 0,

                    trusted_count INTEGER
                        NOT NULL DEFAULT 0,

                    recovered_count INTEGER
                        NOT NULL DEFAULT 0,

                    quarantined_count INTEGER
                        NOT NULL DEFAULT 0,

                    failed_count INTEGER
                        NOT NULL DEFAULT 0,

                    started_at TEXT NOT NULL,
                    finished_at TEXT,

                    report_json TEXT
                        NOT NULL DEFAULT '{}'
                )
                """
            )

    def start(
        self,
        *,
        run_id: str,
        source: str,
        schema_name: str,
        schema_version: str,
        started_at: str,
        input_sha256: str,
    ) -> None:

        with self._connect() as connection:

            connection.execute(
                """
                INSERT INTO runs (
                    run_id,
                    source,
                    schema_name,
                    schema_version,
                    status,
                    input_sha256,
                    started_at
                )
                VALUES (
                    ?, ?, ?, ?, 'RUNNING', ?, ?
                )
                """,
                (
                    run_id,
                    source,
                    schema_name,
                    schema_version,
                    input_sha256,
                    started_at,
                ),
            )

    def complete(
        self,
        report: dict[str, Any],
    ) -> None:

        records = report.get(
            "records",
            {},
        )

        with self._connect() as connection:

            connection.execute(
                """
                UPDATE runs
                SET status = ?,
                    raw_count = ?,
                    player_row_count = ?,
                    trusted_count = ?,
                    recovered_count = ?,
                    quarantined_count = ?,
                    failed_count = ?,
                    finished_at = ?,
                    report_json = ?
                WHERE run_id = ?
                """,
                (
                    report["status"],
                    records.get(
                        "raw",
                        0,
                    ),
                    records.get(
                        "player_rows",
                        0,
                    ),
                    records.get(
                        "final_trusted",
                        0,
                    ),
                    records.get(
                        "recovered",
                        0,
                    ),
                    records.get(
                        "quarantined",
                        0,
                    ),
                    records.get(
                        "failed",
                        0,
                    ),
                    report.get(
                        "finished_at"
                    ),
                    json.dumps(
                        report,
                        ensure_ascii=False,
                    ),
                    report["run_id"],
                ),
            )

    def successful_counts(
        self,
        limit: int = 5,
    ) -> list[int]:

        with self._connect() as connection:

            rows = connection.execute(
                """
                SELECT trusted_count
                FROM runs
                WHERE status IN (
                    'PASS',
                    'RECOVER',
                    'WARNING'
                )
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            int(row["trusted_count"])
            for row in reversed(rows)
        ]

    def latest(
        self,
    ) -> dict[str, Any] | None:

        with self._connect() as connection:

            row = connection.execute(
                """
                SELECT report_json
                FROM runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            ).fetchone()

        return (
            json.loads(
                row["report_json"]
            )
            if row
            else None
        )

    def get(
        self,
        run_id: str,
    ) -> dict[str, Any] | None:

        with self._connect() as connection:

            row = connection.execute(
                """
                SELECT report_json
                FROM runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()

        return (
            json.loads(
                row["report_json"]
            )
            if row
            else None
        )

    def history(
        self,
        limit: int = 20,
    ) -> list[dict[str, Any]]:

        with self._connect() as connection:

            rows = connection.execute(
                """
                SELECT
                    run_id,
                    source,
                    status,
                    raw_count,
                    player_row_count,
                    trusted_count,
                    recovered_count,
                    quarantined_count,
                    failed_count,
                    started_at,
                    finished_at
                FROM runs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            dict(row)
            for row in rows
        ]