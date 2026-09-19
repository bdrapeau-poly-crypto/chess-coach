from __future__ import annotations

from dataclasses import dataclass

import chess

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20_000,
}


@dataclass(frozen=True)
class MotifResult:
    motif: str
    evidence: dict


def _valuable_attacks(board: chess.Board, attacker: chess.Color) -> list[str]:
    targets: list[str] = []
    for square, piece in board.piece_map().items():
        if piece.color == attacker or piece.piece_type == chess.KING:
            continue
        if board.is_attacked_by(attacker, square) and PIECE_VALUES[piece.piece_type] >= 300:
            targets.append(chess.square_name(square))
    return targets


def classify_motif(
    board_before: chess.Board,
    played_move: chess.Move,
    best_move: chess.Move | None,
    centipawn_loss: int,
) -> MotifResult:
    mover = board_before.turn
    moved_piece = board_before.piece_at(played_move.from_square)
    captured_piece = board_before.piece_at(played_move.to_square)
    after = board_before.copy(stack=False)
    after.push(played_move)

    if after.is_checkmate():
        return MotifResult("mate_allowed", {"result": "checkmate"})

    opponent = not mover
    attacked = _valuable_attacks(after, opponent)
    if moved_piece and after.is_attacked_by(opponent, played_move.to_square):
        defenders = len(after.attackers(mover, played_move.to_square))
        attackers = len(after.attackers(opponent, played_move.to_square))
        if PIECE_VALUES[moved_piece.piece_type] >= 300 and attackers > defenders:
            return MotifResult(
                "hanging_piece",
                {
                    "piece": moved_piece.symbol().upper(),
                    "square": chess.square_name(played_move.to_square),
                    "attackers": attackers,
                    "defenders": defenders,
                },
            )

    if len(attacked) >= 2:
        return MotifResult("fork_allowed", {"attacked_squares": attacked})

    if best_move and board_before.is_capture(best_move) and not captured_piece:
        target = board_before.piece_at(best_move.to_square)
        return MotifResult(
            "missed_capture",
            {
                "best_move": best_move.uci(),
                "target": target.symbol().upper() if target else None,
            },
        )

    if centipawn_loss >= 500:
        return MotifResult("major_blunder", {"centipawn_loss": centipawn_loss})
    if centipawn_loss >= 250:
        return MotifResult("tactical_oversight", {"centipawn_loss": centipawn_loss})
    return MotifResult("inaccuracy", {"centipawn_loss": centipawn_loss})
