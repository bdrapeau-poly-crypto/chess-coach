from sqlalchemy import select

from app.models import BlunderPosition, Game, StyleProfile, User, WeaknessProfile
from app.profiling.profiles import refresh_weakness_profile, style_matches


def build_user_with_game(session):
    user = User(username="player")
    session.add(user)
    session.flush()
    game = Game(
        user_id=user.id,
        external_id="g1",
        pgn_hash="hash",
        raw_pgn="pgn",
        user_color="white",
        result="win",
        analysis_status="completed",
        accuracy=80,
        average_centipawn_loss=55,
    )
    session.add(game)
    session.flush()
    return user, game


def test_refresh_weakness_profile_aggregates(session):
    user, game = build_user_with_game(session)
    session.add_all(
        [
            BlunderPosition(
                game_id=game.id,
                ply=1,
                fen_before="fen1",
                fen_after="fen2",
                played_move_uci="e2e4",
                centipawn_loss=200,
                motif="fork_allowed",
            ),
            BlunderPosition(
                game_id=game.id,
                ply=3,
                fen_before="fen3",
                fen_after="fen4",
                played_move_uci="g1f3",
                centipawn_loss=400,
                motif="fork_allowed",
            ),
        ]
    )
    session.flush()
    refresh_weakness_profile(session, user.id)
    profile = session.scalar(select(WeaknessProfile))
    assert profile.frequency == 2
    assert profile.average_severity == 300


def test_style_matches_are_ranked(session):
    user, _ = build_user_with_game(session)
    session.add_all(
        [
            StyleProfile(
                gm_name="Close GM",
                source="test",
                aggression=100,
                tactical=30,
                positional=90,
                endgame=80,
                risk=10,
            ),
            StyleProfile(
                gm_name="Far GM",
                source="test",
                aggression=0,
                tactical=100,
                positional=0,
                endgame=0,
                risk=100,
            ),
        ]
    )
    session.commit()
    matches = style_matches(session, user.id)
    assert matches[0]["similarity"] >= matches[1]["similarity"]
