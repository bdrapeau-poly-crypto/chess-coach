from datetime import UTC, datetime, timedelta

import pytest

from app.jobs.ingest import create_ingest_job, release_stale_jobs
from app.models import IngestJob, JobStatus


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
