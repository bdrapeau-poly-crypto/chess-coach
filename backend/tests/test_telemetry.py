from sqlalchemy import select

from app.coach.loop import CoachRunResult
from app.models import UsageEvent
from app.telemetry import record_coach_result


def test_coach_usage_is_persisted_without_response_content(session):
    result = CoachRunResult(
        answer="Private coaching response",
        provider="anthropic",
        model="claude-haiku-4-5",
        input_tokens=120,
        output_tokens=30,
        cache_read_tokens=80,
        cache_write_tokens=40,
        tool_rounds=2,
    )
    record_coach_result(session, result, username="player", duration_ms=250)
    session.commit()

    event = session.scalar(select(UsageEvent))
    assert event.provider == "anthropic"
    assert event.input_tokens == 120
    assert event.cache_read_tokens == 80
    assert event.tool_rounds == 2
    assert "Private coaching response" not in str(event.details)
