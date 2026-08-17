from validation.status import Status


def build_run_report(raw_count: int, valid_count: int, validation_errors: list,
                      drift_result: dict, repair_result: dict, status: Status) -> dict:
    """Combine everything from one pipeline run into a single structured report."""
    return {
        "status": status.value,
        "records": {
            "raw": raw_count,
            "valid": valid_count,
            },
        "validation": {
            "passed": len(validation_errors) == 0,
            "errors": validation_errors,
            },
        "drift": {
            "detected": drift_result["detected"],
            "missing": drift_result["missing"],
            "unexpected": drift_result["unexpected"],
            },
        "repair": repair_result if repair_result is not None else {"attempted": False},
        }