from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(128))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    is_tracked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    games: Mapped[list[Game]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(128))
    url: Mapped[str | None] = mapped_column(String(512))
    pgn_hash: Mapped[str] = mapped_column(String(64), index=True)
    raw_pgn: Mapped[str] = mapped_column(Text)
    played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    user_color: Mapped[str] = mapped_column(String(5))
    result: Mapped[str] = mapped_column(String(16))
    opponent: Mapped[str | None] = mapped_column(String(64))
    time_control: Mapped[str | None] = mapped_column(String(32))
    eco: Mapped[str | None] = mapped_column(String(8))
    opening_name: Mapped[str | None] = mapped_column(String(160))
    analysis_status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    analysis_error: Mapped[str | None] = mapped_column(Text)
    accuracy: Mapped[float | None] = mapped_column(Float)
    average_centipawn_loss: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="games")
    positions: Mapped[list[BlunderPosition]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("user_id", "external_id", name="uq_game_user_external"),)


class EngineCache(Base):
    __tablename__ = "engine_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    fen: Mapped[str] = mapped_column(String(120))
    engine_signature: Mapped[str] = mapped_column(String(160))
    depth: Mapped[int] = mapped_column(Integer)
    score_cp: Mapped[int] = mapped_column(Integer)
    best_move_uci: Mapped[str | None] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BlunderPosition(Base):
    __tablename__ = "blunder_positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    ply: Mapped[int] = mapped_column(Integer)
    fen_before: Mapped[str] = mapped_column(String(120))
    fen_after: Mapped[str] = mapped_column(String(120))
    played_move_uci: Mapped[str] = mapped_column(String(8))
    best_move_uci: Mapped[str | None] = mapped_column(String(8))
    centipawn_loss: Mapped[int] = mapped_column(Integer, index=True)
    motif: Mapped[str] = mapped_column(String(64), index=True)
    motif_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    game: Mapped[Game] = relationship(back_populates="positions")
    drill_cards: Mapped[list[DrillCard]] = relationship(back_populates="position")

    __table_args__ = (UniqueConstraint("game_id", "ply", name="uq_blunder_game_ply"),)


class WeaknessProfile(Base):
    __tablename__ = "weakness_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    motif: Mapped[str] = mapped_column(String(64))
    frequency: Mapped[int] = mapped_column(Integer)
    average_severity: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("user_id", "motif", name="uq_weakness_user_motif"),)


class StyleProfile(Base):
    __tablename__ = "style_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, unique=True
    )
    gm_name: Mapped[str | None] = mapped_column(String(128), unique=True)
    source: Mapped[str] = mapped_column(String(64), default="computed")
    aggression: Mapped[float] = mapped_column(Float)
    tactical: Mapped[float] = mapped_column(Float)
    positional: Mapped[float] = mapped_column(Float)
    endgame: Mapped[float] = mapped_column(Float)
    risk: Mapped[float] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DrillCard(Base):
    __tablename__ = "drill_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    position_id: Mapped[int] = mapped_column(
        ForeignKey("blunder_positions.id", ondelete="CASCADE"), index=True
    )
    theme: Mapped[str] = mapped_column(String(64), index=True)
    box: Mapped[int] = mapped_column(Integer, default=1)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    retired: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    position: Mapped[BlunderPosition] = relationship(back_populates="drill_cards")
    attempts: Mapped[list[DrillAttempt]] = relationship(
        back_populates="card", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "position_id", "theme", name="uq_drill_user_position_theme"),
    )


class DrillAttempt(Base):
    __tablename__ = "drill_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(
        ForeignKey("drill_cards.id", ondelete="CASCADE"), index=True
    )
    correct: Mapped[bool] = mapped_column(Boolean)
    attempted_move_uci: Mapped[str | None] = mapped_column(String(8))
    previous_box: Mapped[int] = mapped_column(Integer)
    next_box: Mapped[int] = mapped_column(Integer)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    card: Mapped[DrillCard] = relationship(back_populates="attempts")


class IngestJob(Base):
    __tablename__ = "ingest_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.QUEUED, index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    games_fetched: Mapped[int] = mapped_column(Integer, default=0)
    games_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    games_failed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


Index(
    "uq_ingest_active_username",
    IngestJob.username,
    unique=True,
    sqlite_where=text("status IN ('queued', 'running')"),
    postgresql_where=text("status IN ('queued', 'running')"),
)


class ArchiveCache(Base):
    __tablename__ = "archive_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    archive_url: Mapped[str] = mapped_column(String(512))
    etag: Mapped[str | None] = mapped_column(String(256))
    last_modified: Mapped[str | None] = mapped_column(String(128))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("username", "archive_url", name="uq_archive_user_url"),)


class SeedVersion(Base):
    __tablename__ = "seed_versions"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    applied_on: Mapped[date] = mapped_column(Date, default=date.today)


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    identity_hash: Mapped[str] = mapped_column(String(64), index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint(
            "category",
            "identity_hash",
            "window_start",
            name="uq_rate_limit_window",
        ),
    )


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str | None] = mapped_column(String(32), index=True)
    model: Mapped[str | None] = mapped_column(String(128))
    username: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, default=0)
    tool_rounds: Mapped[int] = mapped_column(Integer, default=0)
    error_type: Mapped[str | None] = mapped_column(String(128))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
