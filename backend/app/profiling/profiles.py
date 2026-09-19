from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import BlunderPosition, Game, StyleProfile, User, WeaknessProfile, utcnow

STYLE_FIELDS = ("aggression", "tactical", "positional", "endgame", "risk")


@dataclass(frozen=True)
class StyleVector:
    aggression: float
    tactical: float
    positional: float
    endgame: float
    risk: float


def refresh_weakness_profile(session: Session, user_id: int) -> None:
    session.execute(delete(WeaknessProfile).where(WeaknessProfile.user_id == user_id))
    rows = session.execute(
        select(
            BlunderPosition.motif,
            func.count(BlunderPosition.id),
            func.avg(BlunderPosition.centipawn_loss),
        )
        .join(Game, Game.id == BlunderPosition.game_id)
        .where(Game.user_id == user_id)
        .group_by(BlunderPosition.motif)
    ).all()
    for motif, count, average in rows:
        session.add(
            WeaknessProfile(
                user_id=user_id,
                motif=motif,
                frequency=int(count),
                average_severity=round(float(average), 1),
                updated_at=utcnow(),
            )
        )


def compute_style_vector(session: Session, user_id: int) -> StyleVector:
    games = session.scalars(
        select(Game).where(Game.user_id == user_id, Game.analysis_status == "completed")
    ).all()
    if not games:
        return StyleVector(50, 50, 50, 50, 50)
    results = [game.result for game in games]
    avg_acpl = sum(game.average_centipawn_loss or 0 for game in games) / len(games)
    tactical_count = (
        session.scalar(
            select(func.count(BlunderPosition.id))
            .join(Game, Game.id == BlunderPosition.game_id)
            .where(
                Game.user_id == user_id,
                BlunderPosition.motif.in_(["fork_allowed", "missed_capture", "tactical_oversight"]),
            )
        )
        or 0
    )
    decisive = sum(result in {"win", "loss"} for result in results) / len(results)
    win_rate = sum(result == "win" for result in results) / len(results)
    return StyleVector(
        aggression=round(100 * decisive, 1),
        tactical=round(min(100, 30 + 10 * tactical_count / len(games)), 1),
        positional=round(max(0, 100 - avg_acpl / 2), 1),
        endgame=round(40 + 40 * win_rate, 1),
        risk=round(min(100, avg_acpl / 2), 1),
    )


def refresh_style_profile(session: Session, user_id: int) -> StyleProfile:
    vector = compute_style_vector(session, user_id)
    profile = session.scalar(select(StyleProfile).where(StyleProfile.user_id == user_id))
    if profile is None:
        profile = StyleProfile(user_id=user_id, source="computed", sample_size=0, **asdict(vector))
        session.add(profile)
    else:
        for field, value in asdict(vector).items():
            setattr(profile, field, value)
    profile.sample_size = (
        session.scalar(
            select(func.count(Game.id)).where(
                Game.user_id == user_id, Game.analysis_status == "completed"
            )
        )
        or 0
    )
    profile.updated_at = utcnow()
    session.flush()
    return profile


def style_matches(session: Session, user_id: int) -> list[dict]:
    player = refresh_style_profile(session, user_id)
    references = session.scalars(
        select(StyleProfile).where(StyleProfile.gm_name.is_not(None))
    ).all()
    matches = []
    for reference in references:
        squared = sum(
            (float(getattr(player, field)) - float(getattr(reference, field))) ** 2
            for field in STYLE_FIELDS
        )
        distance = math.sqrt(squared / len(STYLE_FIELDS))
        matches.append(
            {
                "gm_name": reference.gm_name,
                "similarity": round(max(0.0, 100.0 - distance), 1),
                "source": reference.source,
            }
        )
    return sorted(matches, key=lambda item: item["similarity"], reverse=True)


def get_user(session: Session, username: str) -> User | None:
    return session.scalar(select(User).where(User.username == username.lower()))
