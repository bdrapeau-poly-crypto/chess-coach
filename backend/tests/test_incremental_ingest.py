from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.ingestion.chesscom import ArchiveResponse
from app.jobs import ingest as module
from app.models import ArchiveCache, Game, User

PGN = '[White "player"]\n[Black "opponent"]\n[Result "1-0"]\n\n1. e4 e5 1-0'


def stored_game(session):
    user = User(username="player")
    session.add(user)
    session.flush()
    game = Game(
        user_id=user.id,
        external_id="old",
        pgn_hash="unchanged",
        raw_pgn=PGN,
        user_color="white",
        result="win",
        analysis_status="completed",
        accuracy=91.5,
    )
    session.add(game)
    session.commit()
    return game


@pytest.mark.asyncio
@pytest.mark.parametrize("has_new_game", [False, True])
async def test_updates_keep_completed_analysis_and_only_analyze_unfinished(
    session, monkeypatch, has_new_game
):
    existing = stored_game(session)
    payloads = [{"uuid": "old", "pgn": PGN}]
    if has_new_game:
        payloads.append({"uuid": "new", "pgn": PGN})

    @contextmanager
    def database_session():
        yield session

    async def fetch(*args, **kwargs):
        return payloads

    analyze = MagicMock(
        side_effect=lambda db, row, engine: setattr(row, "analysis_status", "completed")
    )
    engine = MagicMock()
    engine.__enter__.return_value = engine
    engine.cache_hits = engine.cache_misses = 0
    factory = MagicMock(return_value=engine)
    monkeypatch.setattr(module, "SessionLocal", database_session)
    monkeypatch.setattr(module, "_fetch_games", fetch)
    monkeypatch.setattr(module, "StockfishAnalyzer", factory)
    monkeypatch.setattr(module, "analyze_game", analyze)
    monkeypatch.setattr(module, "refresh_user_outputs", MagicMock())
    job, _ = module.create_ingest_job(session, "player")
    await module.run_ingest_job(job.id)
    assert job.status == "completed"
    assert job.games_analyzed == int(has_new_game)
    assert analyze.call_count == int(has_new_game)
    assert factory.call_count == int(has_new_game)
    assert existing.accuracy == 91.5 and existing.pgn_hash == "unchanged"
    if has_new_game:
        assert analyze.call_args.args[1].external_id == "new"
        assert (
            session.scalar(select(Game).where(Game.external_id == "new")).analysis_status
            == "completed"
        )


@pytest.mark.asyncio
async def test_unchanged_archive_does_not_backfill_older_history(session, monkeypatch):
    session.add(ArchiveCache(username="player", archive_url="latest", etag="cached"))
    session.commit()
    calls = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def get_archives(self, name):
            return ["old", "latest"]

        async def get_archive(self, url, **kwargs):
            calls.append(url)
            return ArchiveResponse(url, [], "cached", None, not_modified=True)

    monkeypatch.setattr(module, "ChessComClient", Client)
    assert await module._fetch_games(session, "player", 50) == []
    assert calls == ["latest"]
