from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.accounts import hash_password, password_matches, router
from app.api.routes import router as api_router
from app.config import Settings, get_settings
from app.database import get_session
from app.models import PlayerAccount, PlayerSession

PASSWORD = "a-test-password-for-account"


def client_for(session, limit=100):
    app = FastAPI()
    app.include_router(router)
    app.include_router(api_router)
    settings = Settings(
        _env_file=None,
        auth_required=True,
        public_player_access=True,
        app_access_key="private-beta-access",
        session_secret="s" * 32,
        auth_attempts_per_hour=limit,
    )
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def register(client, name="test-player"):
    response = client.post("/account/register", json={"login_name": name, "password": PASSWORD})
    assert response.status_code == 201
    return response


def test_password_hash_is_salted_and_not_reversible_plaintext():
    first = hash_password(PASSWORD)
    assert first != hash_password(PASSWORD)
    assert PASSWORD not in first
    assert password_matches(PASSWORD, first)
    assert not password_matches("incorrect-password", first)
    assert not password_matches(PASSWORD, "bad hash")


def test_register_resume_login_and_revoke(session):
    client = client_for(session)
    response = register(client, "Test-Player")
    assert response.headers["cache-control"] == "no-store"
    token = response.json()["token"]
    headers = {"X-Player-Session": token}
    row = session.scalar(select(PlayerSession))
    assert row.token_hash != token
    assert session.scalar(select(PlayerAccount)).password_hash != PASSWORD
    assert (
        client.post(
            "/account/workspace", headers=headers, json={"username": "ExistingPlayer"}
        ).json()["workspace_username"]
        == "existingplayer"
    )
    assert client.get("/account/me", headers=headers).json() == {
        "login_name": "test-player",
        "workspace_username": "existingplayer",
    }
    login = client.post("/account/login", json={"login_name": "TEST-PLAYER", "password": PASSWORD})
    assert login.status_code == 200
    assert login.json()["workspace_username"] == "existingplayer"
    assert login.json()["token"] != token
    assert client.post("/account/logout", headers=headers).status_code == 200
    assert client.get("/account/me", headers=headers).status_code == 401
    assert (
        client.get("/account/me", headers={"X-Player-Session": login.json()["token"]}).status_code
        == 200
    )


def test_accounts_cannot_modify_other_saved_workspaces_or_gain_admin(session):
    client = client_for(session)
    one = register(client, "first-player").json()["token"]
    two = register(client, "second-player").json()["token"]
    assert client.post("/account/workspace", json={"username": "player"}).status_code == 401
    client.post(
        "/account/workspace", headers={"X-Player-Session": one}, json={"username": "player"}
    )
    assert (
        client.get("/account/me", headers={"X-Player-Session": two}).json()["workspace_username"]
        is None
    )
    assert (
        client.get(
            "/metrics/summary", headers={"Authorization": f"Bearer {one}", "X-Player-Session": one}
        ).status_code
        == 401
    )
    assert client.get("/users/tracked", headers={"X-Player-Session": one}).status_code == 401
    assert (
        client.get("/account/me", headers={"X-Player-Session": "forged-token"}).status_code == 401
    )


def test_expired_session_and_wrong_password_are_rejected(session):
    client = client_for(session)
    token = register(client).json()["token"]
    stored = session.scalar(select(PlayerSession))
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    assert client.get("/account/me", headers={"X-Player-Session": token}).status_code == 401
    wrong = {"login_name": "test-player", "password": "wrong-password-attempt"}
    unknown = {**wrong, "login_name": "unknown-player"}
    assert (
        client.post("/account/login", json=wrong).json()
        == client.post("/account/login", json=unknown).json()
    )


def test_duplicate_case_and_invalid_credentials(session):
    client = client_for(session)
    register(client)
    assert (
        client.post(
            "/account/register", json={"login_name": "TEST-PLAYER", "password": PASSWORD}
        ).status_code
        == 409
    )
    assert (
        client.post("/account/register", json={"login_name": "x", "password": "short"}).status_code
        == 422
    )


def test_account_attempts_are_rate_limited(session):
    client = client_for(session, limit=1)
    register(client)
    assert (
        client.post(
            "/account/login", json={"login_name": "test-player", "password": PASSWORD}
        ).status_code
        == 429
    )


def test_validation_never_echoes_passwords(session):
    client = client_for(session)
    response = client.post(
        "/account/register", json={"login_name": "valid-player", "password": "private"}
    )
    assert response.status_code == 422
    assert "private" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_recovery_reset_rotates_codes_revokes_sessions_and_preserves_workspace(session):
    from app.models import PlayerRecoveryCode

    client = client_for(session)
    created = register(client).json()
    codes = created["recovery_codes"]
    assert len(codes) == len(set(codes)) == 8
    rows = session.scalars(select(PlayerRecoveryCode)).all()
    assert len(rows) == 8
    assert all(row.code_hash not in codes for row in rows)
    headers = {"X-Player-Session": created["token"]}
    client.post("/account/workspace", headers=headers, json={"username": "player"})
    other_session = client.post(
        "/account/login", json={"login_name": "test-player", "password": PASSWORD}
    ).json()["token"]
    payload = {
        "login_name": "test-player",
        "password": "a-new-test-password",
        "recovery_code": codes[0],
    }
    reset = client.post("/account/reset-password", json=payload)
    assert reset.status_code == 200
    assert reset.headers["cache-control"] == "no-store"
    replacement = reset.json()["recovery_codes"]
    assert len(replacement) == 8 and not set(replacement).intersection(codes)
    for token in [created["token"], other_session]:
        assert client.get("/account/me", headers={"X-Player-Session": token}).status_code == 401
    assert client.post("/account/reset-password", json=payload).status_code == 400
    assert (
        client.post(
            "/account/login", json={"login_name": "test-player", "password": PASSWORD}
        ).status_code
        == 401
    )
    login = client.post(
        "/account/login", json={"login_name": "test-player", "password": payload["password"]}
    )
    assert login.status_code == 200
    assert login.json()["workspace_username"] == "player"
    assert session.scalar(select(PlayerAccount)).password_hash != payload["password"]


def test_existing_accounts_can_generate_codes_only_with_password(session):
    client = client_for(session)
    created = register(client).json()
    headers = {"X-Player-Session": created["token"]}
    assert client.post("/account/recovery-codes", json={"password": PASSWORD}).status_code == 401
    assert (
        client.post(
            "/account/recovery-codes", headers=headers, json={"password": "incorrect-password"}
        ).status_code
        == 401
    )
    generated = client.post("/account/recovery-codes", headers=headers, json={"password": PASSWORD})
    assert generated.status_code == 200
    assert len(generated.json()["recovery_codes"]) == 8
    old = {
        "login_name": "test-player",
        "password": PASSWORD,
        "recovery_code": created["recovery_codes"][0],
    }
    assert client.post("/account/reset-password", json=old).status_code == 400


def test_recovery_code_is_bound_to_its_account_and_not_consumed_on_invalid_password(session):
    client = client_for(session)
    first = register(client, "first-player").json()
    register(client, "second-player")
    payload = {
        "login_name": "second-player",
        "password": PASSWORD,
        "recovery_code": first["recovery_codes"][0],
    }
    assert client.post("/account/reset-password", json=payload).status_code == 400
    payload["login_name"] = "first-player"
    payload["password"] = "short"
    assert client.post("/account/reset-password", json=payload).status_code == 422
    payload["password"] = PASSWORD
    assert client.post("/account/reset-password", json=payload).status_code == 200
