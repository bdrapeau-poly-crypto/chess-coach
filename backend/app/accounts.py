from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_session
from app.ingestion.pgn import normalize_username
from app.models import PlayerAccount, PlayerSession
from app.security import enforce_rate_limit, request_identity


class AccountRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def redact_validation(request: Request):
            try:
                return await handler(request)
            except RequestValidationError:
                # Validation responses must not echo passwords back to clients.
                return JSONResponse(
                    status_code=422,
                    content={"detail": "Check the account fields and password length."},
                    headers={"Cache-Control": "no-store"},
                )

        return redact_validation


router = APIRouter(prefix="/account", tags=["player accounts"], route_class=AccountRoute)
# Scrypt parameters are fixed so stored data cannot request arbitrary work.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**15, 8, 3


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode(),
        salt=bytes.fromhex(salt),
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=64 * 1024 * 1024,
        dklen=32,
    ).hex()
    return f"scrypt-v1${salt}${digest}"


def password_matches(password: str, stored: str) -> bool:
    try:
        version, salt, _ = stored.split("$")
        return version == "scrypt-v1" and secrets.compare_digest(
            hash_password(password, salt), stored
        )
    except (ValueError, TypeError):
        return False


class Credentials(BaseModel):
    login_name: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(min_length=12, max_length=128)

    @field_validator("login_name")
    @classmethod
    def lower_name(cls, value: str) -> str:
        return value.lower()


class WorkspaceRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)

    @field_validator("username")
    @classmethod
    def normalize(cls, value: str) -> str:
        return normalize_username(value)


def _limit(request: Request, session: Session, settings: Settings) -> None:
    enforce_rate_limit(
        session,
        category="player-account",
        identity=request_identity(request, settings),
        limit=settings.auth_attempts_per_hour,
    )


def _token(request: Request) -> str:
    # Kept separate from administrator authentication, including in the browser.
    value = request.headers.get("X-Player-Session", "")
    if not value or len(value) > 128:
        raise HTTPException(status_code=401, detail="Sign in to your Chess Coach account")
    return hashlib.sha256(value.encode()).hexdigest()


def require_account(request: Request, session: Session) -> PlayerSession:
    row = session.get(PlayerSession, _token(request))
    if row is None:
        raise HTTPException(status_code=401, detail="Your sign-in has expired. Sign in again.")
    expires = (
        row.expires_at.replace(tzinfo=UTC) if row.expires_at.tzinfo is None else row.expires_at
    )
    if expires <= datetime.now(UTC):
        raise HTTPException(status_code=401, detail="Your sign-in has expired. Sign in again.")
    return row


def _view(account: PlayerAccount) -> dict:
    return {"login_name": account.login_name, "workspace_username": account.workspace_username}


def _issue(account: PlayerAccount, session: Session, response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(UTC)
    session.execute(
        delete(PlayerSession)
        .where(PlayerSession.expires_at <= now)
        .execution_options(synchronize_session="fetch")
    )
    token = secrets.token_urlsafe(32)
    expiry = now + timedelta(days=30)
    session.add(
        PlayerSession(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            account_id=account.id,
            expires_at=expiry,
        )
    )
    session.commit()
    return {**_view(account), "token": token, "expires_at": expiry}


@router.post("/register", status_code=201)
def register(
    payload: Credentials,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    _limit(request, session, settings)
    account = PlayerAccount(
        login_name=payload.login_name, password_hash=hash_password(payload.password)
    )
    session.add(account)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Choose a different account name") from exc
    return _issue(account, session, response)


@router.post("/login")
def login(
    payload: Credentials,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    _limit(request, session, settings)
    account = session.scalar(
        select(PlayerAccount).where(PlayerAccount.login_name == payload.login_name)
    )
    # Unknown names also perform the same expensive password derivation.
    stored = account.password_hash if account else "scrypt-v1$" + "00" * 16 + "$" + "00" * 32
    valid = password_matches(payload.password, stored)
    if not account or not valid:
        raise HTTPException(status_code=401, detail="Incorrect account name or password")
    return _issue(account, session, response)


@router.get("/me")
def me(request: Request, response: Response, session: Session = Depends(get_session)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return _view(require_account(request, session).account)


@router.post("/workspace")
def save_workspace(
    payload: WorkspaceRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    account = require_account(request, session).account
    account.workspace_username = payload.username
    session.commit()
    return _view(account)


@router.post("/logout")
def logout(request: Request, response: Response, session: Session = Depends(get_session)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    row = require_account(request, session)
    session.delete(row)
    session.commit()
    return {"signed_out": True}
