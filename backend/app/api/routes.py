from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime, timedelta
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.analysis.engine import stockfish_health
from app.coach.loop import CoachUnavailable, run_coach_loop
from app.config import Settings, get_settings
from app.database import get_session
from app.ingestion.pgn import normalize_username
from app.jobs.ingest import create_ingest_job
from app.models import (
    BlunderPosition,
    DrillCard,
    Game,
    IngestJob,
    StyleProfile,
    UsageEvent,
    User,
    WeaknessProfile,
)
from app.practice.leitner import mastery, queue_from_blunders, record_attempt
from app.profiling.profiles import STYLE_FIELDS, get_user, refresh_style_profile, style_matches
from app.schemas import (
    CoachRequest,
    CoachResponse,
    DrillAttemptRequest,
    DrillCardResponse,
    JobResponse,
    SessionRequest,
    SessionResponse,
    StyleGapResponse,
)
from app.security import (
    bearer_token,
    enforce_rate_limit,
    issue_session_token,
    request_identity,
    require_authenticated,
    verify_session_token,
)
from app.telemetry import record_coach_result, record_usage_event

router = APIRouter()


def require_user(session: Session, username: str):
    try:
        normalized = normalize_username(username)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user = get_user(session, normalized)
    if user is None:
        raise HTTPException(status_code=404, detail="Player has not been ingested")
    return user


@router.get("/health")
def health() -> dict:
    result = {"status": "ok"}
    if commit := os.getenv("RENDER_GIT_COMMIT"):
        result["commit"] = commit
    return result


@router.get("/health/stockfish")
def health_stockfish(settings: Settings = Depends(get_settings)) -> dict:
    result = stockfish_health(settings)
    if result["status"] != "ok":
        raise HTTPException(status_code=503, detail=result)
    return result


@router.get("/auth/session", response_model=SessionResponse)
def auth_status(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> SessionResponse:
    authenticated = not settings.auth_required or verify_session_token(
        bearer_token(request), settings
    )
    return SessionResponse(authenticated=authenticated, auth_required=settings.auth_required)


@router.post("/auth/session", response_model=SessionResponse)
def create_session(
    payload: SessionRequest,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SessionResponse:
    if not settings.auth_required:
        return SessionResponse(authenticated=True, auth_required=False)
    enforce_rate_limit(
        session,
        category="auth",
        identity=request_identity(request, settings),
        limit=settings.auth_attempts_per_hour,
    )
    if not settings.app_access_key or not secrets.compare_digest(
        payload.access_key, settings.app_access_key
    ):
        raise HTTPException(status_code=401, detail="Invalid private beta access key")
    token, expires_at = issue_session_token(settings)
    return SessionResponse(
        authenticated=True,
        auth_required=True,
        token=token,
        expires_at=expires_at,
    )


@router.post("/ingest/{username}", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest(
    username: str,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> JobResponse:
    principal = require_authenticated(request, settings)
    enforce_rate_limit(
        session,
        category="ingest",
        identity=principal,
        limit=settings.ingest_requests_per_hour,
    )
    try:
        job, created = create_ingest_job(session, username)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JobResponse(
        job_id=job.id,
        username=job.username,
        status=job.status,
        deduplicated=not created,
    )


@router.get("/ingest/jobs/{job_id}")
def ingest_status(
    job_id: int,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    require_authenticated(request, settings)
    job = session.get(IngestJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.id,
        "username": job.username,
        "status": job.status,
        "games_fetched": job.games_fetched,
        "games_analyzed": job.games_analyzed,
        "games_failed": job.games_failed,
        "error": job.error,
    }


@router.get("/users/tracked")
def tracked_users(
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    require_authenticated(request, settings)
    usernames = session.scalars(
        select(User.username)
        .where(User.is_tracked.is_(True), User.is_demo.is_(False))
        .order_by(User.username)
    ).all()
    return {"usernames": list(usernames)}


@router.get("/profile/{username}")
def profile(username: str, session: Session = Depends(get_session)) -> dict:
    user = require_user(session, username)
    weaknesses = session.scalars(
        select(WeaknessProfile)
        .where(WeaknessProfile.user_id == user.id)
        .order_by(WeaknessProfile.frequency.desc(), WeaknessProfile.average_severity.desc())
    ).all()
    totals = session.execute(
        select(
            func.count(Game.id),
            func.sum(case((Game.result == "win", 1), else_=0)),
            func.sum(case((Game.result == "loss", 1), else_=0)),
            func.sum(case((Game.result == "draw", 1), else_=0)),
            func.avg(Game.accuracy),
        ).where(Game.user_id == user.id)
    ).one()
    games, wins, losses, draws, accuracy = totals
    return {
        "username": user.username,
        "summary": {
            "games": int(games),
            "wins": int(wins or 0),
            "losses": int(losses or 0),
            "draws": int(draws or 0),
            "local_accuracy": round(float(accuracy), 1) if accuracy is not None else None,
        },
        "weaknesses": [
            {
                "theme": row.motif,
                "frequency": row.frequency,
                "average_severity": row.average_severity,
            }
            for row in weaknesses
        ],
    }


@router.get("/style/{username}/match")
def style_match(username: str, session: Session = Depends(get_session)) -> dict:
    user = require_user(session, username)
    matches = style_matches(session, user.id)
    session.commit()
    return {
        "username": user.username,
        "matches": matches,
        "coverage_note": (
            f"Ranked against {len(matches)} illustrative seeded grandmaster references; "
            "this is not an all-grandmaster corpus."
        ),
    }


@router.get("/style-gap/{username}", response_model=StyleGapResponse)
def style_gap(
    username: str,
    gm: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> StyleGapResponse:
    user = require_user(session, username)
    player = refresh_style_profile(session, user.id)
    if gm:
        reference = session.scalar(select(StyleProfile).where(StyleProfile.gm_name == gm))
    else:
        matches = style_matches(session, user.id)
        reference = (
            session.scalar(
                select(StyleProfile).where(StyleProfile.gm_name == matches[0]["gm_name"])
            )
            if matches
            else None
        )
    if reference is None:
        raise HTTPException(status_code=404, detail="Grandmaster reference not found")
    player_values = {field: float(getattr(player, field)) for field in STYLE_FIELDS}
    gm_values = {field: float(getattr(reference, field)) for field in STYLE_FIELDS}
    response = StyleGapResponse(
        username=user.username,
        gm_name=reference.gm_name or "Unknown",
        player=player_values,
        grandmaster=gm_values,
        gap={field: round(player_values[field] - gm_values[field], 1) for field in STYLE_FIELDS},
    )
    session.commit()
    return response


@router.get("/blunders/{username}")
def blunders(
    username: str,
    theme: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict:
    user = require_user(session, username)
    query = (
        select(BlunderPosition)
        .join(Game, Game.id == BlunderPosition.game_id)
        .where(Game.user_id == user.id)
        .order_by(BlunderPosition.centipawn_loss.desc())
        .limit(limit)
    )
    if theme:
        query = query.where(BlunderPosition.motif == theme)
    rows = session.scalars(query).all()
    return {
        "username": user.username,
        "positions": [
            {
                "id": row.id,
                "game_id": row.game_id,
                "ply": row.ply,
                "fen": row.fen_before,
                "played_move": row.played_move_uci,
                "best_move": row.best_move_uci,
                "centipawn_loss": row.centipawn_loss,
                "theme": row.motif,
                "evidence": row.motif_evidence,
            }
            for row in rows
        ],
    }


@router.get("/openings/{username}")
def openings(username: str, session: Session = Depends(get_session)) -> dict:
    user = require_user(session, username)
    from app.coach.tools import CoachTools

    return {
        "username": user.username,
        "openings": CoachTools(session, username).get_opening_stats(20),
    }


@router.get("/drill/{username}/queue", response_model=list[DrillCardResponse])
def drill_queue(
    username: str,
    limit: int = Query(default=10, ge=1, le=50),
    session: Session = Depends(get_session),
) -> list[DrillCardResponse]:
    user = require_user(session, username)
    cards = session.scalars(
        select(DrillCard)
        .where(DrillCard.user_id == user.id, DrillCard.retired.is_(False))
        .order_by(DrillCard.due_at.asc(), DrillCard.box.asc())
        .limit(limit)
    ).all()
    return [
        DrillCardResponse(
            card_id=card.id,
            theme=card.theme,
            box=card.box,
            due_at=card.due_at,
            fen=card.position.fen_before,
            label=f"Find the improvement after {card.position.played_move_uci}",
            orientation=card.position.game.user_color,
        )
        for card in cards
    ]


@router.post("/drill/{username}/queue")
def prepare_drill_queue(
    username: str,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    user = require_user(session, username)
    if user.is_demo:
        return {"username": user.username, "created": 0, "demo": True}
    principal = require_authenticated(request, settings)
    enforce_rate_limit(
        session,
        category="drill",
        identity=principal,
        limit=settings.drill_mutations_per_hour,
    )
    created = queue_from_blunders(session, user.id)
    session.commit()
    return {"username": user.username, "created": created}


@router.post("/drill/{username}/attempt")
def drill_attempt(
    username: str,
    payload: DrillAttemptRequest,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    user = require_user(session, username)
    card = session.scalar(
        select(DrillCard).where(DrillCard.id == payload.card_id, DrillCard.user_id == user.id)
    )
    if card is None:
        raise HTTPException(status_code=404, detail="Drill card not found")
    expected = card.position.best_move_uci
    correct = expected is not None and payload.attempted_move_uci.lower() == expected.lower()
    if user.is_demo:
        return {
            "attempt_id": None,
            "correct": correct,
            "correct_move": expected,
            "previous_box": card.box,
            "next_box": card.box,
            "due_at": card.due_at,
            "demo": True,
        }
    principal = require_authenticated(request, settings)
    enforce_rate_limit(
        session,
        category="drill",
        identity=principal,
        limit=settings.drill_mutations_per_hour,
    )
    attempt = record_attempt(
        session,
        card,
        correct=correct,
        attempted_move_uci=payload.attempted_move_uci,
        now=datetime.now(UTC),
    )
    session.commit()
    return {
        "attempt_id": attempt.id,
        "correct": attempt.correct,
        "correct_move": expected,
        "previous_box": attempt.previous_box,
        "next_box": attempt.next_box,
        "due_at": card.due_at,
    }


@router.get("/drill/{username}/mastery")
def drill_mastery(username: str, session: Session = Depends(get_session)) -> dict:
    user = require_user(session, username)
    return {"username": user.username, "themes": mastery(session, user.id)}


@router.post("/coach", response_model=CoachResponse)
def coach(
    payload: CoachRequest,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CoachResponse:
    require_user(session, payload.username)
    principal = require_authenticated(request, settings)
    enforce_rate_limit(
        session,
        category="coach",
        identity=principal,
        limit=settings.coach_requests_per_hour,
    )
    started = perf_counter()
    try:
        result = run_coach_loop(
            session,
            settings,
            username=payload.username,
            message=payload.message,
            history=[message.model_dump() for message in payload.history],
        )
    except CoachUnavailable as exc:
        record_usage_event(
            session,
            event_type="coach",
            status="failed",
            duration_ms=int((perf_counter() - started) * 1000),
            username=payload.username,
            provider=settings.ai_provider,
            error_type=type(exc).__name__,
        )
        session.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        session.rollback()
        record_usage_event(
            session,
            event_type="coach",
            status="failed",
            duration_ms=int((perf_counter() - started) * 1000),
            username=payload.username,
            provider=settings.ai_provider,
            error_type=type(exc).__name__,
        )
        session.commit()
        raise
    record_coach_result(
        session,
        result,
        username=payload.username,
        duration_ms=int((perf_counter() - started) * 1000),
    )
    session.commit()
    return CoachResponse(answer=result.answer)


@router.get("/metrics/summary")
def metrics_summary(
    request: Request,
    days: int = Query(default=30, ge=1, le=90),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    require_authenticated(request, settings)
    since = datetime.now(UTC) - timedelta(days=days)
    rows = session.execute(
        select(
            UsageEvent.event_type,
            UsageEvent.status,
            func.count(UsageEvent.id),
            func.sum(UsageEvent.duration_ms),
            func.sum(UsageEvent.input_tokens),
            func.sum(UsageEvent.output_tokens),
            func.sum(UsageEvent.cache_read_tokens),
            func.sum(UsageEvent.cache_write_tokens),
        )
        .where(UsageEvent.created_at >= since)
        .group_by(UsageEvent.event_type, UsageEvent.status)
    ).all()
    return {
        "days": days,
        "events": [
            {
                "event_type": event_type,
                "status": event_status,
                "count": int(count),
                "duration_ms": int(duration_ms or 0),
                "input_tokens": int(input_tokens or 0),
                "output_tokens": int(output_tokens or 0),
                "cache_read_tokens": int(cache_read_tokens or 0),
                "cache_write_tokens": int(cache_write_tokens or 0),
            }
            for (
                event_type,
                event_status,
                count,
                duration_ms,
                input_tokens,
                output_tokens,
                cache_read_tokens,
                cache_write_tokens,
            ) in rows
        ],
    }
