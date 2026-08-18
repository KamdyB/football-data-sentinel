from pipeline import run_pipeline
from validation.schema import is_player_row

def test_validation_constraints():
    assert is_player_row({"player_name": "  Player "}) is False
    assert is_player_row({"player_name": "Tyler Adams"}) is True

    corrupt_mock = {
        "players": [
            {"player_name": "Brenden Aaronson", "nation": "USA", "position": "MF", "age": "25", "squad": "Leeds", "games": "32", "starts": "40", "minutes": "2400", "goals": "4", "assists": "5"}
        ]
    }
    output = run_pipeline(corrupt_mock)
    assert output["meta"]["quarantined"] == 1
    print("All functional system assertions passed cleanly.")

if __name__ == "__main__":
    test_validation_constraints()