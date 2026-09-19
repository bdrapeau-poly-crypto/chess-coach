from sqlalchemy import func, select

from app.models import BlunderPosition, Game, StyleProfile, User, WeaknessProfile
from app.profiling.profiles import (
    STYLE_FIELDS,
    compute_style_vector,
    get_user,
    refresh_style_profile,
    refresh_weakness_profile,
    style_matches,
)


def add_user(session, username="style-player"):
    user = User(username=username)
    session.add(user)
    session.flush()
    return user


def add_game(session, user, *, result="win", acpl=50, status="completed", external_id="g"):
    game = Game(
        user_id=user.id,
        external_id=external_id,
        pgn_hash=f"hash-{external_id}",
        raw_pgn="pgn",
        user_color="white",
        result=result,
        analysis_status=status,
        accuracy=75,
        average_centipawn_loss=acpl,
    )
    session.add(game)
    session.flush()
    return game


def test_empty_player_gets_neutral_style(session):
    user = add_user(session)
    assert compute_style_vector(session, user.id).aggression == 50


def test_winning_game_produces_expected_style_components(session):
    user = add_user(session)
    add_game(session, user, result="win", acpl=50)
    vector = compute_style_vector(session, user.id)
    assert (vector.aggression, vector.endgame, vector.risk) == (100, 80, 25)


def test_losing_game_has_baseline_endgame_score(session):
    user = add_user(session)
    add_game(session, user, result="loss")
    assert compute_style_vector(session, user.id).endgame == 40


def test_draw_reduces_decisiveness(session):
    user = add_user(session)
    add_game(session, user, result="draw")
    assert compute_style_vector(session, user.id).aggression == 0


def test_refresh_style_creates_profile(session):
    user = add_user(session)
    add_game(session, user)
    profile = refresh_style_profile(session, user.id)
    assert profile.user_id == user.id
    assert profile.source == "computed"


def test_refresh_style_updates_without_duplicate(session):
    user = add_user(session)
    game = add_game(session, user)
    first = refresh_style_profile(session, user.id)
    game.average_centipawn_loss = 200
    second = refresh_style_profile(session, user.id)
    assert first.id == second.id
    assert session.scalar(select(func.count(StyleProfile.id))) == 1


def test_style_sample_counts_only_completed_games(session):
    user = add_user(session)
    add_game(session, user, external_id="done")
    add_game(session, user, status="failed", external_id="failed")
    assert refresh_style_profile(session, user.id).sample_size == 1


def test_style_matches_can_be_empty(session):
    user = add_user(session)
    add_game(session, user)
    assert style_matches(session, user.id) == []


def test_identical_style_reference_scores_one_hundred(session):
    user = add_user(session)
    add_game(session, user, result="win", acpl=50)
    session.add(
        StyleProfile(
            gm_name="Exact GM",
            source="test",
            aggression=100,
            tactical=30,
            positional=75,
            endgame=80,
            risk=25,
        )
    )
    session.commit()
    assert style_matches(session, user.id)[0]["similarity"] == 100


def test_style_match_preserves_reference_source(session):
    user = add_user(session)
    add_game(session, user)
    session.add(
        StyleProfile(
            gm_name="Sourced GM",
            source="verified-corpus",
            aggression=50,
            tactical=50,
            positional=50,
            endgame=50,
            risk=50,
        )
    )
    session.commit()
    assert style_matches(session, user.id)[0]["source"] == "verified-corpus"


def test_get_user_is_case_insensitive(session):
    user = add_user(session, "lowercase")
    session.commit()
    assert get_user(session, "LOWERCASE").id == user.id


def test_get_user_returns_none_for_missing(session):
    assert get_user(session, "missing") is None


def test_refresh_weakness_removes_stale_rows(session):
    user = add_user(session)
    session.add(WeaknessProfile(user_id=user.id, motif="stale", frequency=9, average_severity=999))
    session.commit()
    refresh_weakness_profile(session, user.id)
    assert session.scalar(select(func.count(WeaknessProfile.id))) == 0


def test_refresh_weakness_keeps_motifs_separate(session):
    user = add_user(session)
    game = add_game(session, user)
    session.add_all(
        [
            BlunderPosition(
                game_id=game.id,
                ply=1,
                fen_before="fen1",
                fen_after="fen2",
                played_move_uci="e2e4",
                centipawn_loss=150,
                motif="fork",
            ),
            BlunderPosition(
                game_id=game.id,
                ply=2,
                fen_before="fen3",
                fen_after="fen4",
                played_move_uci="e7e5",
                centipawn_loss=250,
                motif="pin",
            ),
        ]
    )
    session.flush()
    refresh_weakness_profile(session, user.id)
    assert {row.motif for row in session.scalars(select(WeaknessProfile))} == {"fork", "pin"}


def test_computed_style_values_are_bounded(session):
    user = add_user(session)
    add_game(session, user, result="loss", acpl=10_000)
    vector = compute_style_vector(session, user.id)
    assert all(0 <= getattr(vector, field) <= 100 for field in STYLE_FIELDS)
