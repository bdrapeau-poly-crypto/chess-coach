from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.api.routes import drill_attempt
from app.models import BlunderPosition, DrillCard, Game, User
from app.practice.leitner import BOX_INTERVALS, mastery, queue_from_blunders, record_attempt
from app.schemas import DrillAttemptRequest


def add_practice_data(session):
    user = User(username="practice")
    other = User(username="other-practice")
    session.add_all([user, other])
    session.flush()
    game = Game(
        user_id=user.id,
        external_id="p-game",
        pgn_hash="p-hash",
        raw_pgn="pgn",
        user_color="white",
        result="loss",
    )
    other_game = Game(
        user_id=other.id,
        external_id="o-game",
        pgn_hash="o-hash",
        raw_pgn="pgn",
        user_color="white",
        result="loss",
    )
    session.add_all([game, other_game])
    session.flush()
    positions = []
    for index, severity in enumerate([90, 150, 300, 600], start=1):
        position = BlunderPosition(
            game_id=game.id,
            ply=index,
            fen_before=f"8/8/8/8/8/8/4K3/7k w - - 0 {index}",
            fen_after=f"8/8/8/8/8/4K3/8/7k b - - 1 {index}",
            played_move_uci="e2e3",
            best_move_uci="e2f2",
            centipawn_loss=severity,
            motif="fork" if index % 2 else "pin",
        )
        positions.append(position)
    session.add_all(positions)
    session.add(
        BlunderPosition(
            game_id=other_game.id,
            ply=1,
            fen_before="8/8/8/8/8/8/4K3/7k w - - 0 1",
            fen_after="8/8/8/8/8/4K3/8/7k b - - 1 1",
            played_move_uci="e2e3",
            best_move_uci="e2f2",
            centipawn_loss=900,
            motif="other",
        )
    )
    session.commit()
    return user, other, positions


def test_queue_filters_below_minimum_severity(session):
    user, _, _ = add_practice_data(session)
    assert queue_from_blunders(session, user.id, minimum_severity=100) == 3


def test_queue_honors_limit(session):
    user, _, _ = add_practice_data(session)
    assert queue_from_blunders(session, user.id, limit=2) == 2


def test_queue_is_idempotent(session):
    user, _, _ = add_practice_data(session)
    queue_from_blunders(session, user.id)
    assert queue_from_blunders(session, user.id) == 0


def test_correct_attempt_records_transition(session):
    user, _, _ = add_practice_data(session)
    queue_from_blunders(session, user.id, limit=1)
    card = session.scalar(select(DrillCard))
    attempt = record_attempt(session, card, correct=True, attempted_move_uci="e2f2")
    assert (attempt.previous_box, attempt.next_box, card.box) == (1, 2, 2)


def test_incorrect_attempt_resets_card(session):
    user, _, _ = add_practice_data(session)
    queue_from_blunders(session, user.id, limit=1)
    card = session.scalar(select(DrillCard))
    card.box = 4
    attempt = record_attempt(session, card, correct=False, attempted_move_uci="e2e3")
    assert attempt.next_box == 1


def test_attempt_response_reveals_correct_move_after_grading(session):
    user, _, _ = add_practice_data(session)
    queue_from_blunders(session, user.id, limit=1)
    card = session.scalar(select(DrillCard))

    result = drill_attempt(
        "practice",
        DrillAttemptRequest(card_id=card.id, attempted_move_uci="e2e3"),
        session,
    )

    assert result["correct"] is False
    assert result["correct_move"] == "e2f2"


def test_mastery_summarizes_theme(session):
    user, _, _ = add_practice_data(session)
    queue_from_blunders(session, user.id)
    rows = mastery(session, user.id)
    assert sum(row["cards"] for row in rows) == 3


@pytest.mark.parametrize("lower,higher", [(1, 2), (2, 3), (3, 4), (4, 5)])
def test_box_intervals_increase(lower, higher):
    assert BOX_INTERVALS[lower] < BOX_INTERVALS[higher]


def test_queue_excludes_other_users_positions(session):
    user, _, _ = add_practice_data(session)
    queue_from_blunders(session, user.id)
    assert session.scalar(select(func.count(DrillCard.id))) == 3


def test_queue_orders_most_severe_first(session):
    user, _, _ = add_practice_data(session)
    queue_from_blunders(session, user.id, limit=1)
    card = session.scalar(select(DrillCard))
    assert card.position.centipawn_loss == 600


def test_mastery_keeps_themes_separate(session):
    user, _, _ = add_practice_data(session)
    queue_from_blunders(session, user.id)
    assert {row["theme"] for row in mastery(session, user.id)} == {"fork", "pin"}


def test_attempt_uses_supplied_timestamp(session):
    user, _, _ = add_practice_data(session)
    queue_from_blunders(session, user.id, limit=1)
    card = session.scalar(select(DrillCard))
    now = datetime(2026, 9, 19, tzinfo=UTC)
    attempt = record_attempt(session, card, correct=True, attempted_move_uci="e2f2", now=now)
    assert attempt.attempted_at == now


def test_new_cards_are_due_immediately(session):
    user, _, _ = add_practice_data(session)
    before = datetime.now(UTC).replace(tzinfo=None)
    queue_from_blunders(session, user.id, limit=1)
    card = session.scalar(select(DrillCard))
    due = card.due_at.replace(tzinfo=None)
    assert before <= due <= datetime.now(UTC).replace(tzinfo=None)
