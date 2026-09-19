from datetime import UTC, datetime, timedelta

import pytest

from app.ingestion.chesscom import ArchiveResponse
from app.jobs import ingest as ingest_module
from app.jobs.ingest import _fetch_games, create_ingest_job, release_stale_jobs
from app.models import ArchiveCache, IngestJob, JobStatus


def test_stale_queued_job_is_superseded(session):
    old = IngestJob(
        username="player",
        status=JobStatus.QUEUED,
        requested_at=datetime.now(UTC) - timedelta(hours=1),
    )
    session.add(old)
    session.commit()
    new, created = create_ingest_job(session, "player")
    assert created is True
    assert new.id != old.id
    assert old.status == JobStatus.FAILED


def test_stale_running_job_is_superseded(session):
    old = IngestJob(
        username="player",
        status=JobStatus.RUNNING,
        lease_expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    session.add(old)
    session.commit()
    new, created = create_ingest_job(session, "player")
    assert created is True
    assert new.id != old.id


def test_release_stale_jobs_requeues_work(session):
    job = IngestJob(
        username="player",
        status=JobStatus.RUNNING,
        lease_expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    session.add(job)
    session.commit()
    assert release_stale_jobs(session) == 1
    assert job.status == JobStatus.QUEUED


def test_release_stale_jobs_ignores_queued(session):
    session.add(IngestJob(username="player", status=JobStatus.QUEUED))
    session.commit()
    assert release_stale_jobs(session) == 0


def test_release_stale_jobs_ignores_live_lease(session):
    session.add(
        IngestJob(
            username="player",
            status=JobStatus.RUNNING,
            lease_expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    session.commit()
    assert release_stale_jobs(session) == 0


@pytest.mark.parametrize("username", ["", "bad name", "bad!", "x" * 65])
def test_create_job_validates_username(session, username):
    with pytest.raises(ValueError):
        create_ingest_job(session, username)


def test_failed_job_allows_retry(session):
    first, _ = create_ingest_job(session, "retry-player")
    first.status = JobStatus.FAILED
    session.commit()
    second, created = create_ingest_job(session, "retry-player")
    assert created is True
    assert second.id != first.id


@pytest.mark.asyncio
async def test_partial_resume_bypasses_archive_validators(session, monkeypatch):
    session.add(
        ArchiveCache(
            username="player",
            archive_url="https://example.test/archive",
            etag="old-etag",
            last_modified="old-date",
        )
    )
    session.commit()
    calls = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get_archives(self, username):
            return ["https://example.test/archive"]

        async def get_archive(self, url, *, etag=None, last_modified=None):
            calls.append((etag, last_modified))
            return ArchiveResponse(url, [{"pgn": "game"}], "new-etag", "new-date")

    monkeypatch.setattr(ingest_module, "ChessComClient", FakeClient)

    games = await _fetch_games(session, "player", 10, force_refresh=True)

    assert games == [{"pgn": "game"}]
    assert calls == [(None, None)]
