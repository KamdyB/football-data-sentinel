from enum import Enum


class Status(Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    QUARANTINE = "QUARANTINE"
    RECOVER = "RECOVER"
    FAIL = "FAIL"


def classify_status(
    validation_errors,
    drift_result,
    repair_result=None,
):
    if drift_result.get("missing"):

        if (
            repair_result is not None
            and repair_result.get("success")
            and not validation_errors
        ):
            return Status.RECOVER

        return Status.QUARANTINE

    if validation_errors:
        return Status.FAIL

    if drift_result.get("unexpected"):
        return Status.WARNING

    return Status.PASS