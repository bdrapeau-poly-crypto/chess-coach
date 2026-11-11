import chess


def move_notation(fen: str, uci: str | None) -> str | None:
    if not uci:
        return None
    try:
        board = chess.Board(fen)
        return board.san(board.parse_uci(uci))
    except ValueError:
        return None
