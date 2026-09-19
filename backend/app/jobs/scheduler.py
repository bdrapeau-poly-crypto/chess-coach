from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings
from app.database import SessionLocal
from app.jobs.ingest import create_ingest_job, run_ingest_job_sync


def refresh_tracked_users() -> None:
    settings = get_settings()
    for username in settings.tracked_usernames:
        with SessionLocal() as session:
            job, created = create_ingest_job(session, username)
        if created:
            run_ingest_job_sync(job.id)


def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        refresh_tracked_users,
        trigger="cron",
        hour=3,
        minute=0,
        id="nightly-tracked-user-refresh",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler
