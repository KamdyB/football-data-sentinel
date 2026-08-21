import json
import os
from pathlib import Path
import sys

from validation.schema import (
    REQUIRED_FIELDS,
    validate_record,
    check_text_fields,
    check_numeric_fields,
    check_ranges,
    check_relationships,
    check_dataset,
    check_duplicates,
    is_player_row,
    )
from validation.drift import detect_drift, suggest_field_mappings
from validation.recovery import attempt_multi_repair
from validation.status import classify_status, Status


AI_HEALING_ENABLED = bool(os.environ.get("GEMINI_API_KEY"))


def validate_player(player: dict) -> list[str]:
    """Run all record-level validation checks."""
    return (
        validate_record(player)
        + check_text_fields(player)
        + check_numeric_fields(player)
        + check_ranges(player)
        + check_relationships(player)
        )


def _drift_signature(drift: dict) -> tuple:
    return (tuple(sorted(drift["missing"])), tuple(sorted(drift.get("unexpected", []))))


def _precompute_ai_mappings(players: list[dict]) -> dict:
    """
    Collect every unresolved mapping across the entire dataset and resolve
    them with at most ONE Gemini request.

    Deterministic mappings are resolved locally first.
    AI is only asked about what remains unresolved.
    """

    if not AI_HEALING_ENABLED:
        return {}

    from validation.ai_healer import suggest_ai_mappings_batch

    signatures = {}

    for player in players:
        drift = detect_drift(player, REQUIRED_FIELDS)

        if not drift["missing"]:
            continue

        sig = _drift_signature(drift)

        signatures.setdefault(
            sig,
            {
                "drift": drift,
                "sample_player": player,
            },
        )

    ai_requests = []
    signature_order = []

    for sig, item in signatures.items():
        drift = item["drift"]
        sample_player = item["sample_player"]

        mapping_result = suggest_field_mappings(
            drift["missing"],
            drift.get("unexpected", []),
        )

        resolved = {
            mapping["missing_field"]
            for mapping in mapping_result["accepted"]
        }

        unresolved = [
            field
            for field in drift["missing"]
            if field not in resolved
        ]

        if not unresolved:
            continue

        safe_candidates = sorted(
            {
                candidate["unexpected_field"]
                for candidate in mapping_result["candidates"]
                if (
                    candidate["missing_field"] in unresolved
                    and candidate["method"] != "blocked_non_equivalent"
                )
            }
        )

        if not safe_candidates:
            continue

        signature_order.append(sig)

        ai_requests.append(
            {
                "missing": unresolved,
                "candidates": safe_candidates,
                "sample": sample_player,
            }
        )

    if not ai_requests:
        return {}

    # ONE Gemini request for the entire run.
    batch_results = suggest_ai_mappings_batch(ai_requests)

    cache = {}

    for index, sig in enumerate(signature_order):
        mappings = []

        if index < len(batch_results):
            mappings = batch_results[index].get("mappings", [])

        cache[sig] = mappings

    return cache


def _attempt_ai_repair(player: dict, drift: dict, mapping_result: dict, ai_cache: dict) -> dict:
    ai_mappings = ai_cache.get(_drift_signature(drift), [])

    if not ai_mappings:
        return attempt_multi_repair(player, mapping_result)

    combined = {
        "accepted": mapping_result["accepted"] + ai_mappings,
        "candidates": mapping_result["candidates"] + ai_mappings,
        }
    return attempt_multi_repair(player, combined)


def process_player(player: dict, ai_cache: dict | None = None) -> dict:
    """Run one record through validation, drift detection, and repair."""
    errors = validate_player(player)

    drift = detect_drift(player, REQUIRED_FIELDS)

    repair = None

    if drift["missing"]:
        mapping_result = suggest_field_mappings(
            drift["missing"],
            drift.get("unexpected", []),
        )
        repair = attempt_multi_repair(player, mapping_result)

        if not repair["success"] and AI_HEALING_ENABLED:
            repair = _attempt_ai_repair(player, drift, mapping_result, ai_cache or {})

    final_record = (
        repair["record"]
        if repair is not None and repair.get("success")
        else player
    )

    if repair is not None and repair.get("success"):
        final_errors = validate_player(final_record)
    else:
        final_errors = errors

    status = classify_status(
        final_errors,
        drift,
        repair,
    )

    return {
        "status": status,
        "record": final_record,
        "errors": final_errors,
        "drift": drift,
        "repair": repair,
    }


def run_pipeline(input_source) -> dict:
    """Accept a raw JSON file path or a direct scraper payload."""
    
    if isinstance(input_source, str):
        with open(input_source, "r", encoding="utf-8") as file:
             data = json.load(file)
    elif isinstance(input_source, (dict, list)):
        data = input_source
    else:
        raise ValueError("pipeline input must be a file path, JSON object, or JSON list")

    if isinstance(data, list):
       if not data or not isinstance(data[0], dict):
           raise ValueError("JSON list must contain a player payload object")
       raw_players = data[0].get("players", [])
    elif isinstance(data, dict):
       raw_players = data.get("players", [])
    else:
       raise ValueError("unsupported JSON payload")
      
    if not isinstance(raw_players, list):
       raise ValueError("'players' must be a list")

    players = [p for p in raw_players if is_player_row(p)]
    duplicates = check_duplicates(players)

    ai_cache = _precompute_ai_mappings(players)
    results = [process_player(p, ai_cache) for p in players]

    trusted = [r["record"] for r in results if r["status"] in (Status.PASS, Status.RECOVER, Status.WARNING,)]
    quarantined = [
        {
            "record": r["record"],
            "status": r["status"].value,
            "errors": r["errors"],
            "drift": r["drift"],
            "repair": r["repair"],
            }
        for r in results if r["status"] in (Status.QUARANTINE, Status.FAIL,)
        ]
    recovered_count = sum(1 for r in results if r["status"] == Status.RECOVER)
    all_errors = [error for r in results for error in r["errors"]]

    dataset_errors = check_dataset(players)

    # Per-record status already decides trusted vs quarantined. This is a
    # coarser run-level summary: a dataset problem outranks everything,
    # then any quarantine at all means the run isn't fully clean.
    record_statuses = [r["status"] for r in results]

    if dataset_errors:
        overall_status = Status.FAIL
    elif Status.QUARANTINE in record_statuses:
        overall_status = Status.QUARANTINE
    elif Status.FAIL in record_statuses:
        overall_status = Status.FAIL
    elif Status.RECOVER in record_statuses:
        overall_status = Status.RECOVER
    elif Status.WARNING in record_statuses:
        overall_status = Status.WARNING
    else:
        overall_status = Status.PASS

    drifted = [r["drift"] for r in results if r["drift"]["detected"]]
    run_drift = {
        "detected": bool(drifted),
        "missing": sorted({field for d in drifted for field in d["missing"]}),
        "unexpected": sorted({field for d in drifted for field in d["unexpected"]}),
        }


    Path("data/processed").mkdir(parents=True, exist_ok=True)
    Path("data/quarantine").mkdir(parents=True, exist_ok=True)
    Path("data/runs").mkdir(parents=True, exist_ok=True)

    with open("data/processed/players.json", "w", encoding="utf-8") as file:
        json.dump(trusted, file, indent=2)

    with open("data/quarantine/players.json", "w", encoding="utf-8") as file:
        json.dump(quarantined, file, indent=2)

    timestamp = report["collected_at"].replace(":", "").replace("-", "").split(".")[0] + "Z"
    with open(f"data/runs/{timestamp}.json", "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    with open("data/runs/latest.json", "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    return report


def print_summary(report: dict) -> None:
    """Human-readable one-glance verdict, for a person, not a machine."""
    status = report["status"].upper()
    records = report["records"]

    print(f"\nSENTINEL RUN — {status}")
    print(f"Source rows:     {records['raw']}")
    print(f"Player rows:     {records['player_rows']}")
    print(f"Trusted:         {records['final_trusted']}")
    print(f"Recovered:       {records['recovered']}")
    print(f"Quarantined:     {records['quarantined']}")

    if status == "PASS":
        print("Dataset is trusted. Safe to use data/processed/players.json.\n")
    elif status == "RECOVER":
        print("Dataset is trusted after automatic repair. See run report for what changed.\n")
    else:
        print("Dataset is NOT fully trusted. Check data/quarantine/players.json before using this dataset.\n")


if __name__ == "__main__":
    input_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "data/raw/latest.json"
    )

    try:
        report = run_pipeline(input_path)
    except FileNotFoundError:
        print(
            f"No raw data found at {input_path}. "
            "Run the scraper first, then refresh."
        )
        sys.exit(1)
    except json.JSONDecodeError:
        print(
            f"{input_path} exists but isn't valid JSON. "
            "The scrape may have failed partway."
        )
        sys.exit(1)

    print_summary(report)

# THIN ENTRY POINT ONLY

from __future__ import annotations

import os

from application.orchestrator import (
    SentinelOrchestrator,
)

from sources.brightdata import (
    BrightDataSource,
)

from sources.file import (
    FileDataSource,
)

from storage.artifacts import (
    FileArtifactRepository,
)

from storage.runs import (
    SQLiteRunRepository,
)

from validation.ai_healer import (
    GeminiRecoveryAdvisor,
)


def build_orchestrator() -> SentinelOrchestrator:

    source_kind = os.getenv(
        "SENTINEL_SOURCE",
        "brightdata",
    ).lower()

    source = (
        FileDataSource(
            os.getenv(
                "SENTINEL_RAW_PATH",
                "data/raw/latest.json",
            )
        )
        if source_kind == "file"
        else BrightDataSource()
    )

    advisor = None

    if os.getenv(
        "GEMINI_API_KEY"
    ):

        try:
            advisor = (
                GeminiRecoveryAdvisor()
            )
        except RuntimeError:
            advisor = None

    return SentinelOrchestrator(
        source=source,
        runs=SQLiteRunRepository(),
        artifacts=FileArtifactRepository(),
        advisor=advisor,
        baseline_tolerance=float(
            os.getenv(
                "SENTINEL_BASELINE_TOLERANCE",
                "0.10",
            )
        ),
        baseline_window=int(
            os.getenv(
                "SENTINEL_BASELINE_WINDOW",
                "5",
            )
        ),
    )


def run_pipeline(
    payload: dict | None = None,
) -> dict:

    return build_orchestrator().run(
        payload
    )


if __name__ == "__main__":

    report = run_pipeline()

    print(
        "\n"
        f"SENTINEL   {report['status']}\n"
        f"RUN        {report['run_id']}\n"
        f"SOURCE     {report['source']}\n"
        f"RAW        {report['records']['raw']}\n"
        f"PLAYER ROWS {report['records']['player_rows']}\n"
        f"TRUSTED    {report['records']['final_trusted']}\n"
        f"RECOVERED  {report['records']['recovered']}\n"
        f"QUARANTINE {report['records']['quarantined']}\n"
        f"FAILED     {report['records']['failed']}\n"
    )