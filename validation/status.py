from enum import Enum


class Status(Enum):
    PASS = "pass"
    WARNING = "warning"
    QUARANTINE = "quarantine"
    RECOVER = "recover"
    FAIL = "fail"


def classify_status(validation_errors, drift_result, repair_result=None):
    """Decide final status based on validation and schema drift."""

    if drift_result["missing"]:
        if repair_result is not None and repair_result.get("success"):
            return Status.RECOVER

        return Status.QUARANTINE

    if drift_result["unexpected"]:
        return Status.WARNING

    if validation_errors:
        return Status.FAIL

    return Status.PASS