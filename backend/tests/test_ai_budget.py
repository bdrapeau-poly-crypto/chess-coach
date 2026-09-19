from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.coach.budget import (
    AiBudgetExceeded,
    anthropic_actual_cost,
    reconcile_anthropic_call,
    reserve_anthropic_call,
)
from app.config import Settings
from app.models import AiCostReservation, AiDailyBudget


def test_anthropic_cost_includes_cache_categories():
    settings = Settings(_env_file=None)

    cost = anthropic_actual_cost(
        settings,
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_read_tokens=1_000_000,
        cache_write_tokens=1_000_000,
    )

    assert cost == pytest.approx(7.35)


def test_reservation_reconciles_to_actual_cost(session):
    settings = Settings(_env_file=None, ai_daily_budget_usd=0.50)
    now = datetime(2026, 9, 19, 12, tzinfo=UTC)

    reservation = reserve_anthropic_call(
        session,
        settings,
        username="player",
        maximum_cost_usd=0.02,
        now=now,
    )
    reconcile_anthropic_call(session, reservation, actual_cost_usd=0.00321)

    row = session.scalar(select(AiCostReservation))
    daily = session.get(AiDailyBudget, now.date())
    assert row.status == "reconciled"
    assert row.actual_microusd == 3210
    assert daily.committed_microusd == 3210


def test_reservation_rejects_projected_daily_overspend(session):
    settings = Settings(_env_file=None, ai_daily_budget_usd=0.01)
    now = datetime(2026, 9, 19, 12, tzinfo=UTC)
    reserve_anthropic_call(
        session,
        settings,
        username="player",
        maximum_cost_usd=0.006,
        now=now,
    )

    with pytest.raises(AiBudgetExceeded, match="Daily AI coach budget"):
        reserve_anthropic_call(
            session,
            settings,
            username="player",
            maximum_cost_usd=0.006,
            now=now,
        )
