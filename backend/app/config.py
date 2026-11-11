from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Chess Coach API"
    environment: str = "development"
    database_url: str = "sqlite:///./chess_coach.db"
    ai_provider: str = "openai"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.3-codex"
    openai_reasoning_effort: str = "medium"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-haiku-4-5"
    ai_daily_budget_usd: float = 0.50
    anthropic_input_usd_per_mtok: float = 1.0
    anthropic_cache_write_usd_per_mtok: float = 1.25
    anthropic_cache_read_usd_per_mtok: float = 0.10
    anthropic_output_usd_per_mtok: float = 5.0
    ai_cost_reserve_multiplier: float = 1.25
    stockfish_path: str | None = None
    stockfish_depth: int = 12
    stockfish_hash_mb: int = 128
    max_games_per_ingest: int = 50
    tracked_usernames: Annotated[list[str], NoDecode] = []
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    seed_demo_data: bool = True
    allow_ephemeral_database: bool = False
    run_scheduler: bool = False
    run_job_worker: bool = True
    job_poll_seconds: float = 1.0
    coach_history_limit: int = 12
    coach_max_tool_rounds: int = 5
    public_player_access: bool = True
    auth_required: bool = False
    app_access_key: str | None = None
    session_secret: str | None = None
    session_ttl_hours: int = 24
    trust_proxy_headers: bool = False
    auth_attempts_per_hour: int = 10
    ingest_requests_per_hour: int = 6
    coach_requests_per_hour: int = 30
    drill_mutations_per_hour: int = 120

    @field_validator("tracked_usernames", "cors_origins", mode="before")
    @classmethod
    def split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


def ensure_durable_database(settings: Settings) -> None:
    if (
        settings.environment.lower() == "production"
        and settings.database_url.startswith("sqlite")
        and not settings.allow_ephemeral_database
    ):
        raise RuntimeError(
            "Production SQLite is ephemeral. Configure DATABASE_URL or explicitly set "
            "ALLOW_EPHEMERAL_DATABASE=true for a disposable demo."
        )


def ensure_security_configuration(settings: Settings) -> None:
    if settings.environment.lower() == "production" and not settings.auth_required:
        raise RuntimeError("Production requires administrator authentication")
    if not settings.auth_required:
        return
    if not settings.app_access_key or len(settings.app_access_key) < 16:
        raise RuntimeError(
            "APP_ACCESS_KEY must contain at least 16 characters when auth is enabled"
        )
    if not settings.session_secret or len(settings.session_secret) < 32:
        raise RuntimeError(
            "SESSION_SECRET must contain at least 32 characters when auth is enabled"
        )


def normalized_database_url(url: str) -> str:
    """Select psycopg 3 when providers supply a generic PostgreSQL URL."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url
