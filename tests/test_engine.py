from pipeline import run_pipeline
from validation.schema import is_player_row


def test_is_player_row_filters_blank_and_header_rows():
    assert is_player_row({"player_name": "  Player "}) is False
    assert is_player_row({"player_name": "Tyler Adams"}) is True
    print("test_is_player_row_filters_blank_and_header_rows: PASS")


def test_cross_field_violation_lands_in_quarantine_count():
    corrupt_mock = {
        "players": [
            {"player_name": "Brenden Aaronson", "nation": "USA", "position": "MF",
             "age": "25", "squad": "Leeds", "games": "32", "starts": "40",
             "minutes": "2400", "goals": "4", "assists": "5"}
            ]
        }
    output = run_pipeline(corrupt_mock)

    assert output["status"] == "fail"
    assert output["records"]["quarantined"] == 1
    assert output["records"]["final_trusted"] == 0
    print("test_cross_field_violation_lands_in_quarantine_count: PASS")


def test_xg_xag_drift_is_rejected_not_guessed():
    # Regression test for the real bug found in the 2026-08-19 run: the
    # collector was substituting xG/xAG for goals/assists/starts on a
    # majority of rows. Those are different metrics, not aliases, so
    # Sentinel must quarantine rather than silently rename the field.
    corrupt_mock = {
        "players": [
            {"player_name": "Jerome Abbey", "nation": "eng", "position": "MF",
             "age": 15, "squad": "Wolves", "games": 1, "minutes": 17,
             "xG": "N/A", "xAG": "N/A"}
            ]
        }
    output = run_pipeline(corrupt_mock)

    assert output["records"]["final_trusted"] == 0
    assert output["records"]["recovered"] == 0
    assert output["records"]["quarantined"] == 1
    print("test_xg_xag_drift_is_rejected_not_guessed: PASS")


def test_appearances_alias_still_recovers():
    # Confirms the multi-field repair path didn't regress the one case
    # that's genuinely safe to auto-repair. Dataset-level checks (record
    # count, field-presence-across-dataset) run against the pre-repair raw
    # rows and will always fail on a 1-record mock, so this checks the
    # record-level outcome rather than the run's overall status.
    mock = {
        "players": [
            {"player_name": "Test Player", "nation": "eng", "position": "MF",
             "age": "24", "squad": "Test FC", "appearances": "30", "starts": "25",
             "minutes": "2200", "goals": "5", "assists": "3"}
            ]
        }
    output = run_pipeline(mock)

    assert output["records"]["recovered"] == 1
    assert output["records"]["final_trusted"] == 1
    print("test_appearances_alias_still_recovers: PASS")


if __name__ == "__main__":
    test_is_player_row_filters_blank_and_header_rows()
    test_cross_field_violation_lands_in_quarantine_count()
    test_xg_xag_drift_is_rejected_not_guessed()
    test_appearances_alias_still_recovers()
    print("\nAll engine tests passed.")
