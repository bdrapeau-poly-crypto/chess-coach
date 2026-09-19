import chess
import pytest

from app.analysis.engine import resolve_stockfish_path
from app.analysis.game import accuracy_from_acpl
from app.analysis.motifs import classify_motif


@pytest.mark.parametrize(
    ("acpl", "lower", "upper"),
    [(0, 99.9, 100.0), (50, 80.0, 90.0), (250, 36.0, 37.0), (10_000, 0.0, 0.1)],
)
def test_accuracy_is_bounded_and_monotonic_sample(acpl, lower, upper):
    value = accuracy_from_acpl(acpl)
    assert lower <= value <= upper


def test_resolve_stockfish_honors_executable(tmp_path):
    binary = tmp_path / "stockfish"
    binary.write_text("binary")
    binary.chmod(0o755)
    assert resolve_stockfish_path(str(binary)) == str(binary.resolve())


def test_resolve_stockfish_rejects_non_executable(tmp_path, monkeypatch):
    binary = tmp_path / "stockfish"
    binary.write_text("binary")
    binary.chmod(0o644)
    monkeypatch.setattr("app.analysis.engine.shutil.which", lambda _: None)
    monkeypatch.setattr("app.analysis.engine.COMMON_STOCKFISH_PATHS", ())
    assert resolve_stockfish_path(str(binary)) is None


def test_major_blunder_fallback():
    board = chess.Board()
    result = classify_motif(board, chess.Move.from_uci("e2e4"), None, 600)
    assert result.motif == "major_blunder"


def test_missed_capture_is_classified():
    board = chess.Board("4k3/8/8/8/8/8/3q4/3QK3 w - - 0 1")
    played = chess.Move.from_uci("e1f1")
    best = chess.Move.from_uci("d1d2")
    result = classify_motif(board, played, best, 400)
    assert result.motif == "missed_capture"
    assert result.evidence["best_move"] == "d1d2"
