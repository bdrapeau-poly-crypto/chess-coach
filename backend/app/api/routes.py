from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    WeaknessProfile,
)
from app.practice.leitner import mastery, record_attempt
from app.profiling.profiles import STYLE_FIELDS, get_user, refresh_style_profile, style_matches
from app.schemas import (
    CoachRequest,
    CoachResponse,
    DrillAttemptRequest,
    DrillCardResponse,
    JobResponse,
    StyleGapResponse,
)

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
    return {"status": "ok"}


@router.get("/health/stockfish")
def health_stockfish(settings: Settings = Depends(get_settings)) -> dict:
    result = stockfish_health(settings)
    if result["status"] != "ok":
        raise HTTPException(status_code=503, detail=result)
    return result


@router.post("/ingest/{username}", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest(
    username: str,
    session: Session = Depends(get_session),
) -> JobResponse:
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
def ingest_status(job_id: int, session: Session = Depends(get_session)) -> dict:
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
        "coverage_note": "Ranked against the currently loaded reference corpus.",
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


@router.post("/drill/{username}/attempt")
def drill_attempt(
    username: str,
    payload: DrillAttemptRequest,
    session: Session = Depends(get_session),
) -> dict:
    user = require_user(session, username)
    card = session.scalar(
        select(DrillCard).where(DrillCard.id == payload.card_id, DrillCard.user_id == user.id)
    )
    if card is None:
        raise HTTPException(status_code=404, detail="Drill card not found")
    expected = card.position.best_move_uci
    correct = expected is not None and payload.attempted_move_uci.lower() == expected.lower()
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
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> CoachResponse:
    require_user(session, payload.username)
    try:
        answer = run_coach_loop(
            session,
            settings,
            username=payload.username,
            message=payload.message,
            history=[message.model_dump() for message in payload.history],
        )
    except CoachUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return CoachResponse(answer=answer)
