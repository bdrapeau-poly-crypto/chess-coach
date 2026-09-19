from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import BlunderPosition, DrillAttempt, DrillCard, Game

BOX_INTERVALS = {
    1: timedelta(days=1),
    2: timedelta(days=3),
    3: timedelta(days=7),
    4: timedelta(days=14),
    5: timedelta(days=30),
}


def schedule_attempt(
    card: DrillCard, correct: bool, now: datetime | None = None
) -> tuple[int, datetime]:
    current = now or datetime.now(UTC)
    next_box = min(5, card.box + 1) if correct else 1
    return next_box, current + BOX_INTERVALS[next_box]


def queue_from_blunders(
    session: Session, user_id: int, *, minimum_severity: int = 100, limit: int = 20
) -> int:
    positions = session.scalars(
        select(BlunderPosition)
        .join(Game, Game.id == BlunderPosition.game_id)
        .where(Game.user_id == user_id, BlunderPosition.centipawn_loss >= minimum_severity)
        .order_by(BlunderPosition.centipawn_loss.desc())
        .limit(limit)
    ).all()
    created = 0
    for position in positions:
        existing = session.scalar(
            select(DrillCard.id).where(
                DrillCard.user_id == user_id,
                DrillCard.position_id == position.id,
                DrillCard.theme == position.motif,
            )
        )
        if existing is None:
            session.add(DrillCard(user_id=user_id, position_id=position.id, theme=position.motif))
            created += 1
    session.flush()
    return created


def record_attempt(
    session: Session,
    card: DrillCard,
    *,
    correct: bool,
    attempted_move_uci: str | None,
    now: datetime | None = None,
) -> DrillAttempt:
    previous_box = card.box
    next_box, due_at = schedule_attempt(card, correct, now)
    card.box = next_box
    card.due_at = due_at
    attempt = DrillAttempt(
        card_id=card.id,
        correct=correct,
        attempted_move_uci=attempted_move_uci,
        previous_box=previous_box,
        next_box=next_box,
        attempted_at=now or datetime.now(UTC),
    )
    session.add(attempt)
    session.flush()
    return attempt


def mastery(session: Session, user_id: int) -> list[dict]:
    rows = session.execute(
        select(
            DrillCard.theme,
            func.count(DrillCard.id),
            func.avg(DrillCard.box),
            func.sum(case((DrillCard.box >= 4, 1), else_=0)),
        )
        .where(DrillCard.user_id == user_id, DrillCard.retired.is_(False))
        .group_by(DrillCard.theme)
    ).all()
    return [
        {
            "theme": theme,
            "cards": int(cards),
            "average_box": round(float(average_box), 2),
            "mastered": int(mastered or 0),
        }
        for theme, cards, average_box, mastered in rows
    ]
