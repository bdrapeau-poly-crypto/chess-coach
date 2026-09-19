import pytest

from app.analysis.game import accuracy_from_acpl


@pytest.mark.parametrize(
    ("lower_acpl", "higher_acpl"),
    [(0, 1), (10, 25), (50, 100), (100, 250), (250, 1000)],
)
def test_accuracy_decreases_as_acpl_increases(lower_acpl, higher_acpl):
    assert accuracy_from_acpl(lower_acpl) >= accuracy_from_acpl(higher_acpl)


@pytest.mark.parametrize("acpl", [-100, 0, 125, 1000, 1_000_000])
def test_accuracy_always_stays_in_public_range(acpl):
    assert 0 <= accuracy_from_acpl(acpl) <= 100


@pytest.mark.parametrize(
    ("loss", "expected"),
    [
        (0, "inaccuracy"),
        (249, "inaccuracy"),
        (250, "tactical_oversight"),
        (499, "tactical_oversight"),
        (500, "major_blunder"),
    ],
)
def test_motif_severity_thresholds(loss, expected):
    import chess

    from app.analysis.motifs import classify_motif

    result = classify_motif(chess.Board(), chess.Move.from_uci("e2e4"), None, loss)
    assert result.motif == expected
