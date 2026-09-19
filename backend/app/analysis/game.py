from __future__ import annotations

import io
import math

import chess
import chess.pgn
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.analysis.engine import StockfishAnalyzer
from app.analysis.motifs import classify_motif
from app.models import BlunderPosition, Game

BLUNDER_THRESHOLD_CP = 100


def accuracy_from_acpl(acpl: float) -> float:
    """A transparent local score, not Chess.com's proprietary Accuracy metric."""
    return round(max(0.0, min(100.0, 100.0 * math.exp(-acpl / 250.0))), 1)


def analyze_game(session: Session, game_row: Game, analyzer: StockfishAnalyzer) -> None:
    parsed = chess.pgn.read_game(io.StringIO(game_row.raw_pgn))
    if parsed is None or parsed.errors:
        raise ValueError("Stored PGN is not analyzable")
    user_color = chess.WHITE if game_row.user_color == "white" else chess.BLACK
    board = parsed.board()
    losses: list[int] = []
    session.execute(delete(BlunderPosition).where(BlunderPosition.game_id == game_row.id))

    for ply, move in enumerate(parsed.mainline_moves(), start=1):
        mover = board.turn
        fen_before = board.fen()
        before = None
        if mover == user_color:
            before = analyzer.evaluate(session, board, user_color)
        board_after = board.copy(stack=False)
        board_after.push(move)
        if mover == user_color and before:
            after = analyzer.evaluate(session, board_after, user_color)
            loss = max(0, min(100_000, before.score_cp - after.score_cp))
            losses.append(loss)
            if loss >= BLUNDER_THRESHOLD_CP:
                motif = classify_motif(board, move, before.best_move, loss)
                session.add(
                    BlunderPosition(
                        game_id=game_row.id,
                        ply=ply,
                        fen_before=fen_before,
                        fen_after=board_after.fen(),
                        played_move_uci=move.uci(),
                        best_move_uci=before.best_move.uci() if before.best_move else None,
                        centipawn_loss=loss,
                        motif=motif.motif,
                        motif_evidence=motif.evidence,
                    )
                )
        board = board_after

    acpl = sum(losses) / len(losses) if losses else 0.0
    game_row.average_centipawn_loss = round(acpl, 1)
    game_row.accuracy = accuracy_from_acpl(acpl)
    game_row.analysis_status = "completed"
    game_row.analysis_error = None
    session.flush()


def game_already_exists(session: Session, user_id: int, external_id: str) -> bool:
    return (
        session.scalar(
            select(Game.id).where(Game.user_id == user_id, Game.external_id == external_id)
        )
        is not None
    )
