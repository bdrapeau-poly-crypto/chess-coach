from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.models import UsageEvent

if TYPE_CHECKING:
    from app.coach.loop import CoachRunResult

logger = logging.getLogger("chess_coach.telemetry")


def record_usage_event(
    session: Session,
    *,
    event_type: str,
    status: str,
    duration_ms: int,
    username: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    tool_rounds: int = 0,
    error_type: str | None = None,
    details: dict | None = None,
) -> UsageEvent:
    event = UsageEvent(
        event_type=event_type,
        status=status,
        duration_ms=max(0, duration_ms),
        username=username,
        provider=provider,
        model=model,
        input_tokens=max(0, input_tokens),
        output_tokens=max(0, output_tokens),
        cache_read_tokens=max(0, cache_read_tokens),
        cache_write_tokens=max(0, cache_write_tokens),
        tool_rounds=max(0, tool_rounds),
        error_type=error_type,
        details=details or {},
    )
    session.add(event)
    logger.info(
        "usage_event %s",
        json.dumps(
            {
                "event_type": event_type,
                "status": status,
                "duration_ms": event.duration_ms,
                "provider": provider,
                "model": model,
                "input_tokens": event.input_tokens,
                "output_tokens": event.output_tokens,
                "cache_read_tokens": event.cache_read_tokens,
                "cache_write_tokens": event.cache_write_tokens,
                "tool_rounds": event.tool_rounds,
                "error_type": error_type,
                "details": event.details,
            },
            sort_keys=True,
        ),
    )
    return event


def record_coach_result(
    session: Session,
    result: CoachRunResult,
    *,
    username: str,
    duration_ms: int,
) -> UsageEvent:
    values = asdict(result)
    values.pop("answer")
    return record_usage_event(
        session,
        event_type="coach",
        status="completed",
        duration_ms=duration_ms,
        username=username,
        **values,
    )
