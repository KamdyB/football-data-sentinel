# domain/models.py

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RunStatus(str, Enum):
    RUNNING = "RUNNING"
    PASS = "PASS"
    RECOVER = "RECOVER"
    WARNING = "WARNING"
    QUARANTINE = "QUARANTINE"
    FAIL = "FAIL"


@dataclass(frozen=True)
class Drift:
    missing: tuple[str, ...] = ()
    unexpected: tuple[str, ...] = ()

    @property
    def detected(self) -> bool:
        return bool(self.missing or self.unexpected)

    def as_dict(self) -> dict[str, Any]:
        return {
            "detected": self.detected,
            "missing": list(self.missing),
            "unexpected": list(self.unexpected),
        }


@dataclass(frozen=True)
class Repair:
    attempted: bool = False
    success: bool = False
    reason: str | None = None
    applied: tuple[dict[str, Any], ...] = ()
    candidates: tuple[dict[str, Any], ...] = ()
    errors: tuple[str, ...] = ()
    method: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "success": self.success,
            "reason": self.reason,
            "applied": list(self.applied),
            "candidates": list(self.candidates),
            "errors": list(self.errors),
            "method": self.method,
        }


@dataclass(frozen=True)
class RecordOutcome:
    record: dict[str, Any]
    status: RunStatus
    errors: tuple[str, ...] = ()
    drift: Drift = Drift()
    repair: Repair = Repair()

    def as_dict(self) -> dict[str, Any]:
        return {
            "record": self.record,
            "status": self.status.value,
            "errors": list(self.errors),
            "drift": self.drift.as_dict(),
            "repair": self.repair.as_dict(),
        }


@dataclass
class RunContext:
    run_id: str
    source: str
    schema_name: str
    schema_version: str
    started_at: str
    input_sha256: str

    finished_at: str | None = None
    status: RunStatus = RunStatus.RUNNING

    raw_count: int = 0
    player_row_count: int = 0
    trusted_count: int = 0
    recovered_count: int = 0
    quarantined_count: int = 0
    failed_count: int = 0

    errors: list[str] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)

    def event(self, stage: str, **details: Any) -> None:
        self.events.append({
            "stage": stage,
            "at": _utc_now(),
            **details,
        })


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()