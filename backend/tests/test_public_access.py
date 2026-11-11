from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.routes import router
from app.config import Settings, get_settings
from app.database import get_session
from app.models import DrillAttempt, User
from app.seed import seed_demo_data


def public_client(session, **values):
    settings = Settings(
        _env_file=None, auth_required=True, public_player_access=True,
        app_access_key="administrator-access", session_secret="s" * 32,
        trust_proxy_headers=True, **values,
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_players_can_start_analysis_without_password(session):
    client = public_client(session)
    assert client.get("/auth/session").json()["auth_required"] is False
    job = client.post("/ingest/player-one")
    assert job.status_code == 202
    assert client.get(f"/ingest/jobs/{job.json()['job_id']}").status_code == 200


def test_public_rate_limits_are_separate_per_visitor(session):
    client = public_client(session, ingest_requests_per_hour=1)
    first = {"x-forwarded-for": "192.0.2.1"}
    other = {"x-forwarded-for": "192.0.2.2"}
    assert client.post("/ingest/player-one", headers=first).status_code == 202
    assert client.post("/ingest/player-two", headers=first).status_code == 429
    assert client.post("/ingest/player-two", headers=other).status_code == 202


def test_public_access_keeps_admin_endpoints_protected(session):
    client = public_client(session)
    assert client.get("/metrics/summary").status_code == 401
    assert client.get("/users/tracked").status_code == 401
    assert client.post("/auth/session", json={"access_key": "wrong"}).status_code == 401
    login = client.post("/auth/session", json={"access_key": "administrator-access"})
    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    assert client.get("/metrics/summary", headers=headers).status_code == 200
    assert client.get("/users/tracked", headers=headers).status_code == 200


def test_public_practice_does_not_change_shared_history(session):
    seed_demo_data(session)
    user = session.scalar(select(User).where(User.username == "demo"))
    user.username = "real-player"
    user.is_demo = False
    session.commit()
    client = public_client(session)
    before = client.get("/drill/real-player/queue").json()
    card = before[0]
    response = client.post("/drill/real-player/attempt", json={
        "card_id": card["card_id"], "attempted_move_uci": "e2e4",
    })
    assert response.status_code == 200
    assert response.json()["progress_saved"] is False
    assert session.scalar(select(func.count(DrillAttempt.id))) == 0
    assert client.get("/drill/real-player/queue").json() == before


def test_public_coach_keeps_budget_enforcement_and_rate_limit(session, monkeypatch):
    from app.coach.loop import CoachUnavailable
    seed_demo_data(session)
    def unavailable(*args, **kwargs):
        raise CoachUnavailable("Daily AI budget exhausted")
    monkeypatch.setattr("app.api.routes.run_coach_loop", unavailable)
    client = public_client(session, coach_requests_per_hour=1)
    body = {"username": "demo", "message": "Help me practice"}
    response = client.post("/coach", json=body)
    assert response.status_code == 503
    assert "budget" in response.json()["detail"]
    assert client.post("/coach", json=body).status_code == 429


def test_public_release_cannot_disable_production_admin_protection():
    import pytest

    from app.config import ensure_security_configuration
    with pytest.raises(RuntimeError, match="administrator authentication"):
        ensure_security_configuration(Settings(
            _env_file=None, environment="production", public_player_access=True,
            auth_required=False,
        ))
