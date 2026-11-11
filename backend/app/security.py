from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import RateLimitBucket


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_session_token(settings: Settings, now: datetime | None = None) -> tuple[str, datetime]:
    if not settings.session_secret:
        raise RuntimeError("SESSION_SECRET is not configured")
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(hours=settings.session_ttl_hours)
    payload = {
        "exp": int(expires_at.timestamp()),
        "iat": int(issued_at.timestamp()),
        "jti": secrets.token_urlsafe(12),
        "v": 1,
    }
    encoded = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = _encode(
        hmac.new(settings.session_secret.encode(), encoded.encode(), hashlib.sha256).digest()
    )
    return f"{encoded}.{signature}", expires_at


def verify_session_token(
    token: str | None,
    settings: Settings,
    now: datetime | None = None,
) -> bool:
    if not token or not settings.session_secret:
        return False
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected_signature = _encode(
            hmac.new(settings.session_secret.encode(), encoded.encode(), hashlib.sha256).digest()
        )
        if not secrets.compare_digest(supplied_signature, expected_signature):
            return False
        payload = json.loads(_decode(encoded))
        current = int((now or datetime.now(UTC)).timestamp())
        return payload.get("v") == 1 and int(payload["exp"]) > current
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False


def bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    return token if scheme.lower() == "bearer" and token else None


def require_authenticated(request: Request, settings: Settings) -> str:
    if not settings.auth_required:
        return "development"
    token = bearer_token(request)
    if not verify_session_token(token, settings):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Private beta access is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return hashlib.sha256(token.encode()).hexdigest()


def require_player_access(request: Request, settings: Settings) -> str:
    """Public players share no admin privileges and are limited per network address."""
    if settings.public_player_access:
        return f"public:{request_identity(request, settings)}"
    return require_authenticated(request, settings)


def request_identity(request: Request, settings: Settings) -> str:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(
    session: Session,
    *,
    category: str,
    identity: str,
    limit: int,
    window_seconds: int = 3600,
    now: datetime | None = None,
) -> None:
    if limit <= 0:
        return
    current = now or datetime.now(UTC)
    epoch = int(current.timestamp())
    window_start = datetime.fromtimestamp(epoch - (epoch % window_seconds), tz=UTC)
    identity_hash = hashlib.sha256(identity.encode()).hexdigest()
    bucket = session.scalar(
        select(RateLimitBucket)
        .where(
            RateLimitBucket.category == category,
            RateLimitBucket.identity_hash == identity_hash,
            RateLimitBucket.window_start == window_start,
        )
        .with_for_update()
    )
    if bucket is None:
        bucket = RateLimitBucket(
            category=category,
            identity_hash=identity_hash,
            window_start=window_start,
            request_count=1,
        )
        session.add(bucket)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            bucket = session.scalar(
                select(RateLimitBucket)
                .where(
                    RateLimitBucket.category == category,
                    RateLimitBucket.identity_hash == identity_hash,
                    RateLimitBucket.window_start == window_start,
                )
                .with_for_update()
            )
            if bucket is None:
                raise
            bucket.request_count += 1
    else:
        bucket.request_count += 1
    if bucket.request_count > limit:
        retry_after = max(1, window_seconds - (epoch % window_seconds))
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Request limit reached. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )
    session.commit()
