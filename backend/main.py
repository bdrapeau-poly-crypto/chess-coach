# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Brian J. Drapeau

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.accounts import router as account_router
from app.api.routes import router
from app.config import ensure_durable_database, ensure_security_configuration, get_settings
from app.database import SessionLocal, create_schema
from app.jobs.scheduler import build_scheduler
from app.jobs.worker import JobWorker
from app.seed import seed_demo_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_durable_database(settings)
    ensure_security_configuration(settings)
    create_schema()
    if settings.seed_demo_data:
        with SessionLocal() as session:
            seed_demo_data(session)
    scheduler = None
    worker = None
    if settings.run_job_worker:
        worker = JobWorker()
        worker.start()
        logger.info("Database-backed ingest worker started")
    if settings.run_scheduler:
        scheduler = build_scheduler()
        scheduler.start()
        logger.info("Local APScheduler started")
    yield
    if scheduler:
        scheduler.shutdown(wait=False)
    if worker:
        worker.stop()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys([*settings.cors_origins, settings.public_web_origin])),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Player-Session"],
)
app.include_router(router)

app.include_router(account_router)
