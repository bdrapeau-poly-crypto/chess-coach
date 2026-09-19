from __future__ import annotations

import os

from sqlalchemy import create_engine, inspect, text

from app.config import normalized_database_url

REQUIRED_TABLES = {
    "alembic_version",
    "archive_cache",
    "blunder_positions",
    "drill_attempts",
    "drill_cards",
    "engine_cache",
    "games",
    "ingest_jobs",
    "rate_limit_buckets",
    "style_profiles",
    "usage_events",
    "users",
    "weakness_profiles",
}


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    engine = create_engine(normalized_database_url(database_url), pool_pre_ping=True)
    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        missing = sorted(REQUIRED_TABLES - tables)
        if missing:
            raise RuntimeError(f"Restored branch is missing tables: {', '.join(missing)}")

        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        user_count = int(connection.scalar(text("SELECT count(*) FROM users")) or 0)

    if not revision:
        raise RuntimeError("Restored branch has no Alembic revision")
    if user_count < 1:
        raise RuntimeError("Restored branch contains no users")

    print(f"Restore verified: revision={revision}, users={user_count}, tables={len(tables)}")


if __name__ == "__main__":
    main()
