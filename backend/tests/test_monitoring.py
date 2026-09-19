from app.api.routes import health


def test_health_omits_commit_outside_render(monkeypatch):
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)

    assert health() == {"status": "ok"}


def test_health_exposes_render_commit(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")

    assert health() == {"status": "ok", "commit": "abc123"}
