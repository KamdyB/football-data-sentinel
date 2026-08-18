from datetime import datetime, timezone
from validation.status import Status
from validation.schema import SCHEMA_NAME, SCHEMA_VERSION

    
def build_run_report(raw_count, player_row_count, final_trusted_count,
                      recovered_count, quarantined_count, validation_errors,
                      drift_result, repair_result, status) -> dict:
    """Combine everything from one pipeline run into a single structured report."""
    return {
        "schema": {
            "name": SCHEMA_NAME,
            "version": SCHEMA_VERSION,
            },
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "status": status.value,
        "records": {
            "raw": raw_count,
            "player_rows": player_row_count,
            "recovered": recovered_count,
            "quarantined": quarantined_count,
            "final_trusted": final_trusted_count,
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