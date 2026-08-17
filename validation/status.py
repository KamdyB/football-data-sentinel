from enum import Enum


class Status(Enum):
    PASS = "pass"
    WARNING = "warning"
    QUARANTINE = "quarantine"
    RECOVER = "recover"
    FAIL = "fail"


def classify_status(validation_errors, drift_result, repair_result=None):
    """Decide final status based on validation and drift/repair outcome."""
    if drift_result["detected"]:
        if repair_result is not None and repair_result["success"]:
            return Status.RECOVER
        return Status.QUARANTINE

    if validation_errors:
        return Status.FAIL

    return Status.PASS