import pytest
from pydantic import ValidationError

from app.coach.tools import TOOL_DEFINITIONS
from app.config import Settings, ensure_durable_database
from app.schemas import CoachRequest, DrillAttemptRequest, HistoryMessage


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        (
            "cors_origins",
            "https://one.test, https://two.test",
            ["https://one.test", "https://two.test"],
        ),
        ("tracked_usernames", "Alpha,beta", ["Alpha", "beta"]),
    ],
)
def test_settings_split_csv(field, value, expected):
    settings = Settings(**{field: value})
    assert getattr(settings, field) == expected


def test_default_model_is_current_sonnet():
    assert Settings(_env_file=None).anthropic_model == "claude-sonnet-5"
    assert sum("cache_control" in tool for tool in TOOL_DEFINITIONS) == 1
    with pytest.raises(RuntimeError, match="Production SQLite"):
        ensure_durable_database(Settings(_env_file=None, environment="production"))


def test_coach_history_is_bounded():
    history = [{"role": "user", "content": "x"}] * 21
    with pytest.raises(ValidationError):
        CoachRequest(username="u", message="question", history=history)


def test_coach_message_cannot_be_empty():
    with pytest.raises(ValidationError):
        CoachRequest(username="u", message="")


def test_history_roles_are_restricted():
    with pytest.raises(ValidationError):
        HistoryMessage(role="system", content="no")


@pytest.mark.parametrize("move", ["e2e4", "a7a8q"])
def test_drill_attempt_accepts_uci_moves(move):
    assert DrillAttemptRequest(card_id=1, attempted_move_uci=move).attempted_move_uci == move


@pytest.mark.parametrize("move", ["e2-e4", "drop table"])
def test_drill_attempt_rejects_non_uci_moves(move):
    with pytest.raises(ValidationError):
        DrillAttemptRequest(card_id=1, attempted_move_uci=move)
