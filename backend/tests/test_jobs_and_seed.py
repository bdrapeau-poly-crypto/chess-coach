from sqlalchemy import func, select

from app.jobs.ingest import create_ingest_job, refresh_user_outputs
from app.models import BlunderPosition, DrillCard, Game, JobStatus, StyleProfile, User
from app.seed import GM_PROFILES, seed_demo_data


def test_ingest_job_deduplicates_active_username(session):
    first, created = create_ingest_job(session, "ExampleUser")
    second, created_again = create_ingest_job(session, "exampleuser")
    assert created is True
    assert created_again is False
    assert second.id == first.id


def test_completed_job_allows_new_ingest(session):
    first, _ = create_ingest_job(session, "exampleuser")
    first.status = JobStatus.COMPLETED
    session.commit()
    second, created = create_ingest_job(session, "exampleuser")
    assert created is True
    assert second.id != first.id


def test_seed_is_idempotent(session):
    assert seed_demo_data(session) is True
    assert seed_demo_data(session) is False
    assert session.scalar(select(func.count(User.id))) == 1
    gm_count = session.scalar(
        select(func.count(StyleProfile.id)).where(StyleProfile.gm_name.is_not(None))
    )
    assert gm_count == len(GM_PROFILES)
    assert session.scalar(select(func.count(Game.id))) == 4
    assert session.scalar(select(func.count(DrillCard.id))) > 0


def test_seed_profiles_are_labeled_illustrative(session):
    seed_demo_data(session)
    profiles = session.scalars(select(StyleProfile).where(StyleProfile.gm_name.is_not(None))).all()
    assert profiles
    assert {profile.source for profile in profiles} == {"illustrative-seed-v1"}


def test_ingest_outputs_prepare_drills_without_ai_coach(session):
    user = User(username="autoload")
    session.add(user)
    session.flush()
    game = Game(
        user_id=user.id,
        external_id="autoload-game",
        pgn_hash="autoload-hash",
        raw_pgn="pgn",
        user_color="white",
        result="loss",
        analysis_status="completed",
    )
    session.add(game)
    session.flush()
    session.add(
        BlunderPosition(
            game_id=game.id,
            ply=1,
            fen_before="8/8/8/8/8/8/4K3/7k w - - 0 1",
            fen_after="8/8/8/8/8/4K3/8/7k b - - 1 1",
            played_move_uci="e2e3",
            best_move_uci="e2f2",
            centipawn_loss=300,
            motif="fork",
        )
    )
    session.flush()

    assert refresh_user_outputs(session, user.id) == 1
    assert refresh_user_outputs(session, user.id) == 0
    assert session.scalar(select(func.count(DrillCard.id))) == 1
