import pytest
from sqlalchemy import func, select

from app.coach.tools import CoachTools
from app.models import BlunderPosition, DrillCard, Game, User, WeaknessProfile


@pytest.fixture
def coach_data(session):
    user = User(username="coach-player")
    other = User(username="other")
    session.add_all([user, other])
    session.flush()
    old = Game(
        user_id=user.id,
        external_id="old",
        pgn_hash="old-hash",
        raw_pgn="pgn",
        user_color="white",
        result="loss",
        opening_name="Sicilian Defense",
        analysis_status="completed",
        accuracy=60,
        average_centipawn_loss=100,
    )
    recent = Game(
        user_id=user.id,
        external_id="recent",
        pgn_hash="recent-hash",
        raw_pgn="pgn",
        user_color="black",
        result="win",
        opening_name="Sicilian Defense",
        analysis_status="completed",
        accuracy=80,
        average_centipawn_loss=50,
    )
    unknown = Game(
        user_id=user.id,
        external_id="unknown",
        pgn_hash="unknown-hash",
        raw_pgn="pgn",
        user_color="white",
        result="draw",
        analysis_status="completed",
        accuracy=70,
        average_centipawn_loss=75,
    )
    session.add_all([old, recent, unknown])
    session.flush()
    position = BlunderPosition(
        game_id=recent.id,
        ply=4,
        fen_before="8/8/8/8/8/8/4K3/7k w - - 0 1",
        fen_after="8/8/8/8/8/4K3/8/7k b - - 1 1",
        played_move_uci="e2e3",
        best_move_uci="e2f2",
        centipawn_loss=300,
        motif="fork_allowed",
    )
    session.add(position)
    session.add_all(
        [
            WeaknessProfile(
                user_id=user.id, motif="fork_allowed", frequency=3, average_severity=300
            ),
            WeaknessProfile(user_id=user.id, motif="inaccuracy", frequency=1, average_severity=120),
        ]
    )
    session.commit()
    return user, other, old, recent, unknown, position


def test_unknown_user_is_rejected(session):
    with pytest.raises(ValueError, match="Unknown player"):
        CoachTools(session, "missing")


def test_recent_games_respect_limit(session, coach_data):
    tools = CoachTools(session, "coach-player")
    assert len(tools.get_recent_games(limit=2)) == 2


def test_recent_games_include_local_metric_label(session, coach_data):
    row = CoachTools(session, "coach-player").get_recent_games(limit=1)[0]
    assert "local_accuracy" in row
    assert "analysis_status" in row


def test_weaknesses_are_frequency_ranked(session, coach_data):
    rows = CoachTools(session, "coach-player").get_weakness_profile()
    assert [row["theme"] for row in rows] == ["fork_allowed", "inaccuracy"]


def test_game_details_are_scoped_to_owner(session, coach_data):
    _, _, _, recent, _, _ = coach_data
    details = CoachTools(session, "coach-player").get_game_details(recent.id)
    assert details["positions"][0]["fen"].startswith("8/8")


def test_game_details_hide_another_users_game(session, coach_data):
    _, other, *_ = coach_data
    other_game = Game(
        user_id=other.id,
        external_id="private",
        pgn_hash="private-hash",
        raw_pgn="pgn",
        user_color="white",
        result="win",
    )
    session.add(other_game)
    session.commit()
    assert "error" in CoachTools(session, "coach-player").get_game_details(other_game.id)


def test_opening_stats_aggregate_results(session, coach_data):
    rows = CoachTools(session, "coach-player").get_opening_stats()
    sicilian = next(row for row in rows if row["opening"] == "Sicilian Defense")
    assert sicilian["games"] == 2
    assert (sicilian["wins"], sicilian["losses"]) == (1, 1)


def test_opening_stats_preserve_unknown_bucket(session, coach_data):
    rows = CoachTools(session, "coach-player").get_opening_stats()
    assert any(row["opening"] == "Unknown" and row["draws"] == 1 for row in rows)


def test_queue_practice_creates_cards(session, coach_data):
    result = CoachTools(session, "coach-player").queue_practice()
    assert result["created"] == 1
    assert result["total_queued"] == 1
    assert result["due_now"] == 1
    assert session.scalar(select(func.count(DrillCard.id))) == 1


def test_queue_practice_is_idempotent(session, coach_data):
    tools = CoachTools(session, "coach-player")
    tools.queue_practice()
    result = tools.queue_practice()
    assert result["created"] == 0
    assert result["total_queued"] == 1


@pytest.mark.parametrize(
    "name",
    [
        "get_recent_games",
        "get_weakness_profile",
        "get_game_details",
        "get_opening_stats",
        "queue_practice",
    ],
)
def test_execute_routes_declared_tools(session, coach_data, name):
    _, _, _, recent, _, _ = coach_data
    arguments = {"game_id": recent.id} if name == "get_game_details" else {}
    assert CoachTools(session, "coach-player").execute(name, arguments) is not None
