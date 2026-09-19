from types import SimpleNamespace

import httpx
import pytest
from anthropic import AuthenticationError

from app.coach import loop as coach_loop
from app.coach.loop import CoachUnavailable, run_coach_loop
from app.config import Settings
from app.models import User


class FakeResponses:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return next(self._responses)


def add_user(session, username="player"):
    session.add(User(username=username, display_name=username))
    session.commit()


def test_openai_loop_executes_tools_and_returns_text(session, monkeypatch):
    add_user(session)
    tool_call = SimpleNamespace(
        type="function_call",
        name="get_weakness_profile",
        arguments="{}",
        call_id="call-1",
    )
    fake_responses = FakeResponses(
        [
            SimpleNamespace(output=[tool_call], output_text=""),
            SimpleNamespace(output=[], output_text="Focus on loose pieces."),
        ]
    )
    monkeypatch.setattr(
        coach_loop,
        "OpenAI",
        lambda **kwargs: SimpleNamespace(responses=fake_responses),
    )

    result = run_coach_loop(
        session,
        Settings(_env_file=None, openai_api_key="test-key"),
        username="player",
        message="What should I study?",
        history=[],
    )

    assert result.answer == "Focus on loose pieces."
    assert result.provider == "openai"
    assert result.tool_rounds == 1
    assert fake_responses.calls[0]["model"] == "gpt-5.3-codex"
    assert fake_responses.calls[0]["store"] is False
    assert fake_responses.calls[0]["prompt_cache_key"] == "chess-coach-v1"
    assert fake_responses.calls[1]["input"][-1] == {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": "[]",
    }


def test_openai_loop_requires_api_key(session):
    add_user(session)
    with pytest.raises(CoachUnavailable, match="OPENAI_API_KEY"):
        run_coach_loop(
            session,
            Settings(_env_file=None),
            username="player",
            message="Help",
            history=[],
        )


def test_unknown_provider_is_rejected(session):
    add_user(session)
    with pytest.raises(CoachUnavailable, match="AI_PROVIDER"):
        run_coach_loop(
            session,
            Settings(_env_file=None, ai_provider="other"),
            username="player",
            message="Help",
            history=[],
        )


def test_anthropic_authentication_error_is_actionable(session, monkeypatch):
    add_user(session)
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(401, request=request)

    class FailingMessages:
        def create(self, **kwargs):
            raise AuthenticationError(
                "API key is invalid",
                response=response,
                body={"error": {"type": "authentication_error"}},
            )

    monkeypatch.setattr(
        coach_loop,
        "Anthropic",
        lambda **kwargs: SimpleNamespace(messages=FailingMessages()),
    )

    with pytest.raises(CoachUnavailable, match="Update ANTHROPIC_API_KEY in Render"):
        run_coach_loop(
            session,
            Settings(
                _env_file=None,
                ai_provider="anthropic",
                anthropic_api_key="invalid-test-key",
            ),
            username="player",
            message="Queue drills",
            history=[],
        )
