from __future__ import annotations

import asyncio
import logging
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from time import perf_counter

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analysis.engine import StockfishAnalyzer
from app.analysis.game import analyze_game
from app.config import get_settings
from app.database import SessionLocal
from app.ingestion.chesscom import ChessComClient
from app.ingestion.pgn import normalize_username, parse_game
from app.models import ArchiveCache, Game, IngestJob, JobStatus, User
from app.practice.leitner import queue_from_blunders
from app.profiling.profiles import refresh_style_profile, refresh_weakness_profile
from app.telemetry import record_usage_event

logger = logging.getLogger(__name__)
LEASE_DURATION = timedelta(minutes=10)


def _is_before(value: datetime, threshold: datetime) -> bool:
    if value.tzinfo is None:
        threshold = threshold.replace(tzinfo=None)
    return value < threshold


def create_ingest_job(session: Session, username: str) -> tuple[IngestJob, bool]:
    normalized = normalize_username(username)
    now = datetime.now(UTC)
    active = session.scalar(
        select(IngestJob)
        .where(
            IngestJob.username == normalized,
            IngestJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
        .order_by(IngestJob.id.desc())
    )
    if active:
        stale_running = (
            active.status == JobStatus.RUNNING
            and active.lease_expires_at is not None
            and _is_before(active.lease_expires_at, now)
        )
        stale_queued = active.status == JobStatus.QUEUED and _is_before(
            active.requested_at,
            now - timedelta(minutes=10),
        )
        if stale_running or stale_queued:
            active.status = JobStatus.FAILED
            active.completed_at = now
            active.lease_expires_at = None
            active.error = "Stale job was superseded"
            session.commit()
        else:
            return active, False
    job = IngestJob(username=normalized, status=JobStatus.QUEUED)
    session.add(job)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        winner = session.scalar(
            select(IngestJob)
            .where(
                IngestJob.username == normalized,
                IngestJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
            .order_by(IngestJob.id.desc())
        )
        if winner is None:
            raise
        return winner, False
    session.refresh(job)
    return job, True


def _get_or_create_user(session: Session, username: str) -> User:
    user = session.scalar(select(User).where(User.username == username))
    if user is None:
        user = User(username=username, display_name=username, is_tracked=True)
        session.add(user)
        session.flush()
    elif not user.is_demo:
        user.is_tracked = True
    return user


def refresh_user_outputs(session: Session, user_id: int) -> int:
    """Rebuild derived profiles and idempotently prepare practice cards."""
    refresh_weakness_profile(session, user_id)
    refresh_style_profile(session, user_id)
    return queue_from_blunders(session, user_id)


async def _fetch_games(
    session: Session, username: str, cap: int, *, force_refresh: bool = False
) -> list[dict]:
    collected: list[dict] = []
    async with ChessComClient() as client:
        archives = await client.get_archives(username)
        for url in reversed(archives):
            cached = session.scalar(
                select(ArchiveCache).where(
                    ArchiveCache.username == username, ArchiveCache.archive_url == url
                )
            )
            response = await client.get_archive(
                url,
                etag=cached.etag if cached and not force_refresh else None,
                last_modified=cached.last_modified if cached and not force_refresh else None,
            )
            if cached is None:
                cached = ArchiveCache(username=username, archive_url=url)
                session.add(cached)
            cached.checked_at = datetime.now(UTC)
            if not response.not_modified:
                cached.etag = response.etag
                cached.last_modified = response.last_modified
                collected.extend(reversed(response.games))
            session.commit()
            # An unchanged recent archive is not a request to backfill older history.
            if response.not_modified:
                break
            if len(collected) >= cap:
                break
    return collected[:cap]


async def run_ingest_job(job_id: int) -> None:
    settings = get_settings()
    timer_started = perf_counter()
    with SessionLocal() as session:
        started_at = datetime.now(UTC)
        claimed = session.execute(
            update(IngestJob)
            .where(IngestJob.id == job_id, IngestJob.status == JobStatus.QUEUED)
            .values(
                status=JobStatus.RUNNING,
                started_at=started_at,
                lease_expires_at=started_at + LEASE_DURATION,
            )
        )
        session.commit()
        if claimed.rowcount != 1:
            return
        job = session.get(IngestJob, job_id)
        if job is None:
            return
        cache_hits = 0
        cache_misses = 0
        try:
            unfinished = session.scalar(
                select(Game.id)
                .join(User)
                .where(
                    User.username == job.username,
                    Game.analysis_status != "completed",
                )
                .limit(1)
            )
            payloads = await _fetch_games(
                session,
                job.username,
                settings.max_games_per_ingest,
                force_refresh=job.games_analyzed > 0 or unfinished is not None,
            )
            job.games_fetched = len(payloads)
            session.commit()
            user = _get_or_create_user(session, job.username)
            session.commit()

            with ExitStack() as stack:
                analyzer = None
                for payload in payloads:
                    row_id: int | None = None
                    try:
                        parsed = parse_game(payload, job.username)
                        row = session.scalar(
                            select(Game).where(
                                Game.user_id == user.id,
                                Game.external_id == parsed.external_id,
                            )
                        )
                        if row and row.analysis_status == "completed":
                            continue
                        if row is None:
                            row = Game(
                                user_id=user.id,
                                external_id=parsed.external_id,
                                url=str(payload.get("url") or "") or None,
                                pgn_hash=parsed.pgn_hash,
                                raw_pgn=parsed.pgn,
                                played_at=parsed.played_at,
                                user_color=parsed.user_color,
                                result=parsed.result,
                                opponent=parsed.opponent,
                                time_control=parsed.time_control,
                                eco=parsed.eco,
                                opening_name=parsed.opening_name,
                            )
                            session.add(row)
                            session.commit()
                        row_id = row.id
                        if analyzer is None:
                            analyzer = stack.enter_context(StockfishAnalyzer(settings))
                        analyze_game(session, row, analyzer)
                        job.games_analyzed += 1
                        job.lease_expires_at = datetime.now(UTC) + LEASE_DURATION
                        session.commit()
                    except Exception as exc:
                        session.rollback()
                        if row_id is not None:
                            failed_game = session.get(Game, row_id)
                            if failed_game:
                                failed_game.analysis_status = "failed"
                                failed_game.analysis_error = f"{type(exc).__name__}: {exc}"[:1000]
                        job = session.get(IngestJob, job_id)
                        if job:
                            job.games_failed += 1
                            job.lease_expires_at = datetime.now(UTC) + LEASE_DURATION
                            session.commit()
                        logger.warning(
                            "Game failed during ingest job %s: %s", job_id, type(exc).__name__
                        )
                if analyzer is not None:
                    cache_hits = analyzer.cache_hits
                    cache_misses = analyzer.cache_misses

            refresh_user_outputs(session, user.id)
            job = session.get(IngestJob, job_id)
            if job:
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.now(UTC)
                job.lease_expires_at = None
                record_usage_event(
                    session,
                    event_type="ingest",
                    status="completed",
                    duration_ms=int((perf_counter() - timer_started) * 1000),
                    username=job.username,
                    details={
                        "job_id": job.id,
                        "games_fetched": job.games_fetched,
                        "games_analyzed": job.games_analyzed,
                        "games_failed": job.games_failed,
                        "engine_cache_hits": cache_hits,
                        "engine_cache_misses": cache_misses,
                    },
                )
            session.commit()
        except Exception as exc:
            session.rollback()
            job = session.get(IngestJob, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.completed_at = datetime.now(UTC)
                job.lease_expires_at = None
                job.error = f"{type(exc).__name__}: {exc}"[:1000]
                record_usage_event(
                    session,
                    event_type="ingest",
                    status="failed",
                    duration_ms=int((perf_counter() - timer_started) * 1000),
                    username=job.username,
                    error_type=type(exc).__name__,
                    details={
                        "job_id": job.id,
                        "games_fetched": job.games_fetched,
                        "games_analyzed": job.games_analyzed,
                        "games_failed": job.games_failed,
                        "engine_cache_hits": cache_hits,
                        "engine_cache_misses": cache_misses,
                    },
                )
                session.commit()
            logger.exception("Ingest job %s failed", job_id)


def run_ingest_job_sync(job_id: int) -> None:
    asyncio.run(run_ingest_job(job_id))


def release_stale_jobs(session: Session) -> int:
    now = datetime.now(UTC)
    jobs = session.scalars(
        select(IngestJob).where(
            IngestJob.status == JobStatus.RUNNING,
            IngestJob.lease_expires_at < now,
        )
    ).all()
    for job in jobs:
        job.status = JobStatus.QUEUED
        job.started_at = None
        job.completed_at = None
        job.error = "Recovered after an expired worker lease"
        job.lease_expires_at = None
    session.commit()
    return len(jobs)
