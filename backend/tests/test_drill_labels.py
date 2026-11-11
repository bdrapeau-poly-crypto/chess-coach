import chess

from app.api.routes import drill_position_label


def test_knight_coordinates_become_readable_chess_notation():
    fen = "4k3/8/8/8/8/2N5/8/4K3 w - - 0 1"
    assert drill_position_label(fen, "c3d5") == "Find a better move than Nd5"


def test_label_uses_the_position_before_the_historical_move():
    assert drill_position_label(chess.STARTING_FEN, "e2e4") == "Find a better move than e4"


def test_illegal_historical_move_is_not_presented_as_an_instruction():
    assert drill_position_label(chess.STARTING_FEN, "c3d5") == "Find the best move in this position"


def test_invalid_fen_does_not_crash_the_queue():
    assert drill_position_label("invalid", "c3d5") == "Find the best move in this position"
