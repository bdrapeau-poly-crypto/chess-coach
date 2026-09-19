from app.config import ensure_durable_database, get_settings
from app.database import create_schema
from app.jobs.scheduler import refresh_tracked_users


def main() -> None:
    ensure_durable_database(get_settings())
    create_schema()
    refresh_tracked_users()


if __name__ == "__main__":
    main()
