from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.config import Settings
from app.models import RateLimitBucket
from app.security import enforce_rate_limit, issue_session_token, verify_session_token


def security_settings(**values) -> Settings:
    return Settings(
        _env_file=None,
        auth_required=True,
        app_access_key="private-beta-access",
        session_secret="s" * 32,
        **values,
    )


def test_signed_session_token_expires_and_rejects_tampering():
    settings = security_settings(session_ttl_hours=2)
    now = datetime(2026, 9, 19, tzinfo=UTC)
    token, expires_at = issue_session_token(settings, now=now)
    assert expires_at == now + timedelta(hours=2)
    assert verify_session_token(token, settings, now=now + timedelta(hours=1)) is True
    assert verify_session_token(f"{token}x", settings, now=now) is False
    assert verify_session_token(token, settings, now=now + timedelta(hours=3)) is False


def test_rate_limit_is_persisted_and_returns_retry_after(session):
    now = datetime(2026, 9, 19, 12, 15, tzinfo=UTC)
    enforce_rate_limit(
        session, category="coach", identity="visitor", limit=2, now=now
    )
    enforce_rate_limit(
        session, category="coach", identity="visitor", limit=2, now=now
    )
    with pytest.raises(HTTPException) as caught:
        enforce_rate_limit(
            session, category="coach", identity="visitor", limit=2, now=now
        )
    assert caught.value.status_code == 429
    assert caught.value.headers["Retry-After"] == "2700"
    assert session.scalar(select(func.max(RateLimitBucket.request_count))) == 3


def test_rate_limit_separates_categories_and_windows(session):
    now = datetime(2026, 9, 19, 12, 59, tzinfo=UTC)
    enforce_rate_limit(session, category="coach", identity="visitor", limit=1, now=now)
    enforce_rate_limit(session, category="ingest", identity="visitor", limit=1, now=now)
    enforce_rate_limit(
        session,
        category="coach",
        identity="visitor",
        limit=1,
        now=now + timedelta(minutes=2),
    )
    assert session.scalar(select(func.count(RateLimitBucket.id))) == 3
