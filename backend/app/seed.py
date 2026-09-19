from __future__ import annotations

import hashlib
import io

import chess.pgn
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BlunderPosition, Game, SeedVersion, StyleProfile, User
from app.practice.leitner import queue_from_blunders
from app.profiling.profiles import refresh_style_profile, refresh_weakness_profile

SEED_NAME = "demo-v2"
GM_PROFILES = (
    ("Garry Kasparov", 88, 90, 72, 65, 82),
    ("Magnus Carlsen", 68, 76, 94, 98, 55),
    ("Judit Polgar", 92, 94, 66, 62, 88),
    ("Anatoly Karpov", 52, 58, 98, 91, 35),
    ("Mikhail Tal", 100, 100, 55, 48, 100),
)

DEMO_GAMES = (
    {
        "external_id": "demo-barnes-mate",
        "opening": "Barnes Opening",
        "accuracy": 34.2,
        "acpl": 267.0,
        "blunder": (3, "e2e4", 100_000, "mate_allowed"),
        "pgn": """[Event "Illustrative Demo"]
[Site "Local fixture"]
[Date "2026.09.19"]
[Round "1"]
[White "Demo"]
[Black "TacticalTrainer"]
[Result "0-1"]
[ECO "A00"]
[Opening "Barnes Opening"]

1. f3 e5 2. g4 Qh4# 0-1
""",
    },
    {
        "external_id": "demo-damiano",
        "opening": "Damiano Defense",
        "accuracy": 58.7,
        "acpl": 133.0,
        "blunder": (4, "b8c6", 360, "king_safety"),
        "pgn": """[Event "Illustrative Demo"]
[Site "Local fixture"]
[Date "2026.09.19"]
[Round "2"]
[White "TacticalTrainer"]
[Black "Demo"]
[Result "1-0"]
[ECO "C40"]
[Opening "Damiano Defense"]

1. e4 e5 2. Nf3 f6 3. Nxe5 fxe5 4. Qh5+ g6 5. Qxe5+ Qe7 1-0
""",
    },
    {
        "external_id": "demo-scholars-mate",
        "opening": "Bishop's Opening",
        "accuracy": 96.1,
        "acpl": 10.0,
        "blunder": None,
        "pgn": """[Event "Illustrative Demo"]
[Site "Local fixture"]
[Date "2026.09.19"]
[Round "3"]
[White "Demo"]
[Black "TacticalTrainer"]
[Result "1-0"]
[ECO "C23"]
[Opening "Bishop's Opening"]

1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0
""",
    },
    {
        "external_id": "demo-zukertort-draw",
        "opening": "Zukertort Opening",
        "accuracy": 88.0,
        "acpl": 31.0,
        "blunder": None,
        "pgn": """[Event "Illustrative Demo"]
[Site "Local fixture"]
[Date "2026.09.19"]
[Round "4"]
[White "Demo"]
[Black "TacticalTrainer"]
[Result "1/2-1/2"]
[ECO "A04"]
[Opening "Zukertort Opening"]

1. Nf3 Nf6 2. Ng1 Ng8 3. Nf3 Nf6 4. Ng1 Ng8 1/2-1/2
""",
    },
)


def _seed_demo_games(session: Session, demo: User) -> None:
    for fixture in DEMO_GAMES:
        existing = session.scalar(
            select(Game).where(
                Game.user_id == demo.id,
                Game.external_id == fixture["external_id"],
            )
        )
        if existing:
            continue
        parsed = chess.pgn.read_game(io.StringIO(fixture["pgn"]))
        if parsed is None or parsed.errors:
            raise ValueError(f"Invalid demo PGN: {fixture['external_id']}")
        color = "white" if parsed.headers["White"].lower() == "demo" else "black"
        result_token = parsed.headers["Result"]
        won = (result_token == "1-0" and color == "white") or (
            result_token == "0-1" and color == "black"
        )
        result = "draw" if result_token == "1/2-1/2" else "win" if won else "loss"
        game = Game(
            user_id=demo.id,
            external_id=fixture["external_id"],
            pgn_hash=hashlib.sha256(fixture["pgn"].encode()).hexdigest(),
            raw_pgn=fixture["pgn"],
            user_color=color,
            result=result,
            opponent="TacticalTrainer",
            eco=parsed.headers.get("ECO"),
            opening_name=fixture["opening"],
            analysis_status="completed",
            accuracy=fixture["accuracy"],
            average_centipawn_loss=fixture["acpl"],
        )
        session.add(game)
        session.flush()
        if fixture["blunder"]:
            ply, best_move, severity, motif = fixture["blunder"]
            board = parsed.board()
            played_move = None
            for index, move in enumerate(parsed.mainline_moves(), start=1):
                if index == ply:
                    played_move = move
                    fen_before = board.fen()
                    board.push(move)
                    fen_after = board.fen()
                    break
                board.push(move)
            if played_move is None:
                raise ValueError(f"Missing demo ply: {fixture['external_id']}")
            session.add(
                BlunderPosition(
                    game_id=game.id,
                    ply=ply,
                    fen_before=fen_before,
                    fen_after=fen_after,
                    played_move_uci=played_move.uci(),
                    best_move_uci=best_move,
                    centipawn_loss=severity,
                    motif=motif,
                    motif_evidence={"source": "illustrative-demo-fixture"},
                )
            )


def seed_demo_data(session: Session) -> bool:
    if session.get(SeedVersion, SEED_NAME):
        return False
    demo = session.scalar(select(User).where(User.username == "demo"))
    if demo is None:
        demo = User(username="demo", display_name="Demo Player", is_demo=True)
        session.add(demo)
        session.flush()
    for name, aggression, tactical, positional, endgame, risk in GM_PROFILES:
        existing = session.scalar(select(StyleProfile).where(StyleProfile.gm_name == name))
        if existing is None:
            session.add(
                StyleProfile(
                    gm_name=name,
                    source="illustrative-seed-v1",
                    aggression=aggression,
                    tactical=tactical,
                    positional=positional,
                    endgame=endgame,
                    risk=risk,
                    sample_size=0,
                )
            )
    _seed_demo_games(session, demo)
    refresh_weakness_profile(session, demo.id)
    refresh_style_profile(session, demo.id)
    queue_from_blunders(session, demo.id)
    session.add(SeedVersion(name=SEED_NAME))
    session.commit()
    return True
