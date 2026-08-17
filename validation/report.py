def build_run_report(
    status: str,
    raw_count: int,
    valid_count: int,
    validation_results: dict,
    drift_results: dict,
) -> dict:
    """Build the structured result of one Sentinel run."""

    return {
        "status": status,
        "records": {
            "raw": raw_count,
            "valid": valid_count,
        },
        "validation": validation_results,
        "drift": drift_results,
    }