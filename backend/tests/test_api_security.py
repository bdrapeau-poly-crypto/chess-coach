from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.routes import router
from app.config import Settings, get_settings
from app.database import get_session
from app.models import DrillAttempt, UsageEvent, User
from app.seed import seed_demo_data


def secured_client(session, **setting_values) -> TestClient:
    settings = Settings(
        _env_file=None,
        auth_required=True,
        public_player_access=False,
        app_access_key="private-beta-access",
        session_secret="s" * 32,
        **setting_values,
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_ingest_requires_a_short_lived_session(session):
    client = secured_client(session)
    assert client.post("/ingest/player").status_code == 401
    assert client.post("/auth/session", json={"access_key": "wrong"}).status_code == 401

    login = client.post("/auth/session", json={"access_key": "private-beta-access"})
    assert login.status_code == 200
    token = login.json()["token"]
    assert token and "private-beta-access" not in token

    response = client.post("/ingest/player", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 202
    assert response.json()["username"] == "player"


def test_auth_attempts_are_rate_limited(session):
    client = secured_client(session, auth_attempts_per_hour=1)
    assert client.post("/auth/session", json={"access_key": "wrong"}).status_code == 401
    response = client.post("/auth/session", json={"access_key": "private-beta-access"})
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


def test_public_demo_attempt_is_stateless(session):
    seed_demo_data(session)
    client = secured_client(session)
    card = client.get("/drill/demo/queue").json()[0]
    response = client.post(
        "/drill/demo/attempt",
        json={"card_id": card["card_id"], "attempted_move_uci": "e2e4"},
    )
    assert response.status_code == 200
    assert response.json()["demo"] is True
    assert session.scalar(select(func.count(DrillAttempt.id))) == 0


def test_metrics_summary_requires_authentication(session):
    session.add(
        UsageEvent(
            event_type="coach",
            status="completed",
            duration_ms=25,
            input_tokens=10,
            output_tokens=5,
        )
    )
    session.commit()
    client = secured_client(session)
    assert client.get("/metrics/summary").status_code == 401
    token = client.post(
        "/auth/session", json={"access_key": "private-beta-access"}
    ).json()["token"]
    response = client.get(
        "/metrics/summary", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["events"][0]["input_tokens"] == 10
    assert response.json()["ai_budget"] == {
        "daily_limit_usd": 0.5,
        "committed_usd": 0.0,
        "remaining_usd": 0.5,
    }


def test_tracked_users_requires_authentication_and_excludes_demo(session):
    session.add_all(
        [
            User(username="real-player", display_name="Real", is_tracked=True),
            User(username="not-tracked", display_name="Other", is_tracked=False),
            User(username="demo", display_name="Demo", is_demo=True, is_tracked=True),
        ]
    )
    session.commit()
    client = secured_client(session)

    assert client.get("/users/tracked").status_code == 401
    token = client.post(
        "/auth/session", json={"access_key": "private-beta-access"}
    ).json()["token"]
    response = client.get(
        "/users/tracked", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json() == {"usernames": ["real-player"]}
