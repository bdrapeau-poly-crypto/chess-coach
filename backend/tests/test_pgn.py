from datetime import UTC, datetime

import pytest

from app.ingestion.pgn import PgnParseError, normalize_username, parse_game

PGN = """[Event "Live Chess"]
[Site "Chess.com"]
[Date "2026.09.19"]
[Round "-"]
[White "ExampleUser"]
[Black "Opponent"]
[Result "1-0"]
[ECO "C20"]
[Opening "King's Pawn Game"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 1-0
"""


@pytest.mark.parametrize(
    ("value", "expected"),
    [("ExampleUser", "exampleuser"), ("  abc-123_  ", "abc-123_")],
)
def test_normalize_username(value, expected):
    assert normalize_username(value) == expected


@pytest.mark.parametrize("value", ["", "spaces fail", "bad!", "x" * 65])
def test_normalize_username_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        normalize_username(value)


def test_parse_game_extracts_user_context():
    parsed = parse_game(
        {
            "pgn": PGN,
            "uuid": "game-1",
            "url": "https://www.chess.com/game/live/game-1",
            "end_time": 1_795_000_000,
            "time_control": "600",
        },
        "exampleuser",
    )
    assert parsed.external_id == "game-1"
    assert parsed.user_color == "white"
    assert parsed.opponent == "Opponent"
    assert parsed.result == "win"
    assert parsed.eco == "C20"
    assert parsed.opening_name == "King's Pawn Game"
    assert parsed.played_at == datetime.fromtimestamp(1_795_000_000, UTC)


def test_parse_game_rejects_missing_pgn():
    with pytest.raises(PgnParseError):
        parse_game({}, "exampleuser")


def test_parse_game_rejects_unrelated_user():
    with pytest.raises(PgnParseError):
        parse_game({"pgn": PGN}, "someoneelse")
