# domain/ports.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class DataSource(Protocol):
    name: str

    def collect(self) -> dict[str, Any]:
        ...


class RunRepository(Protocol):
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
        ...

    def complete(self, report: dict[str, Any]) -> None:
        ...

    def successful_counts(self, limit: int) -> list[int]:
        ...

    def latest(self) -> dict[str, Any] | None:
        ...

    def get(self, run_id: str) -> dict[str, Any] | None:
        ...

    def history(self, limit: int) -> list[dict[str, Any]]:
        ...


class ArtifactRepository(Protocol):
    def write_json(
        self,
        run_id: str,
        name: str,
        payload: Any,
    ) -> Path:
        ...


class RecoveryAdvisor(Protocol):
    def suggest_batch(
        self,
        requests: list[dict[str, Any]],
    ) -> list[list[dict[str, Any]]]:
        ...