from datetime import UTC, datetime

import pytest

from app.models import DrillCard
from app.practice.leitner import BOX_INTERVALS, schedule_attempt


@pytest.mark.parametrize("box", [1, 2, 3, 4, 5])
def test_correct_attempt_advances_or_caps(box):
    now = datetime(2026, 9, 19, tzinfo=UTC)
    card = DrillCard(user_id=1, position_id=1, theme="fork", box=box)
    next_box, due = schedule_attempt(card, True, now)
    assert next_box == min(5, box + 1)
    assert due == now + BOX_INTERVALS[next_box]


@pytest.mark.parametrize("box", [1, 2, 3, 4, 5])
def test_incorrect_attempt_returns_to_box_one(box):
    now = datetime(2026, 9, 19, tzinfo=UTC)
    card = DrillCard(user_id=1, position_id=1, theme="fork", box=box)
    next_box, due = schedule_attempt(card, False, now)
    assert next_box == 1
    assert due == now + BOX_INTERVALS[1]
