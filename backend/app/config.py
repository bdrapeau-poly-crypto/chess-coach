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
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
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
