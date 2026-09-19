from __future__ import annotations

import logging
import threading

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.jobs.ingest import release_stale_jobs, run_ingest_job_sync
from app.models import IngestJob, JobStatus

logger = logging.getLogger(__name__)


class JobWorker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="ingest-worker", daemon=True)

    def start(self) -> None:
        with SessionLocal() as session:
            recovered = release_stale_jobs(session)
            if recovered:
                logger.warning("Recovered %s stale ingest jobs", recovered)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=5)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            with SessionLocal() as session:
                job_id = session.scalar(
                    select(IngestJob.id)
                    .where(IngestJob.status == JobStatus.QUEUED)
                    .order_by(IngestJob.requested_at, IngestJob.id)
                    .limit(1)
                )
            if job_id is None:
                self.stop_event.wait(self.settings.job_poll_seconds)
                continue
            try:
                run_ingest_job_sync(job_id)
            except Exception:
                logger.exception("Unexpected worker failure for job %s", job_id)
