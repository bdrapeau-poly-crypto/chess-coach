from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AiCostReservation, AiDailyBudget


class AiBudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class BudgetReservation:
    id: str
    reserved_microusd: int


def _microusd(value: float) -> int:
    return max(0, math.ceil(value * 1_000_000))


def estimate_anthropic_call_cost(
    settings: Settings, *, estimated_input_tokens: int, max_output_tokens: int
) -> float:
    input_rate = max(
        settings.anthropic_input_usd_per_mtok,
        settings.anthropic_cache_write_usd_per_mtok,
    )
    base = (
        max(0, estimated_input_tokens) * input_rate
        + max(0, max_output_tokens) * settings.anthropic_output_usd_per_mtok
    ) / 1_000_000
    return base * settings.ai_cost_reserve_multiplier


def anthropic_actual_cost(
    settings: Settings,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int,
) -> float:
    return (
        max(0, input_tokens) * settings.anthropic_input_usd_per_mtok
        + max(0, output_tokens) * settings.anthropic_output_usd_per_mtok
        + max(0, cache_read_tokens) * settings.anthropic_cache_read_usd_per_mtok
        + max(0, cache_write_tokens) * settings.anthropic_cache_write_usd_per_mtok
    ) / 1_000_000


def _locked_daily_row(session: Session, day: date) -> AiDailyBudget:
    row = session.scalar(select(AiDailyBudget).where(AiDailyBudget.day == day).with_for_update())
    if row is not None:
        return row
    try:
        with session.begin_nested():
            session.add(AiDailyBudget(day=day, committed_microusd=0))
            session.flush()
    except IntegrityError:
        pass
    row = session.scalar(select(AiDailyBudget).where(AiDailyBudget.day == day).with_for_update())
    if row is None:
        raise RuntimeError("AI budget ledger row could not be created")
    return row


def reserve_anthropic_call(
    session: Session,
    settings: Settings,
    *,
    username: str,
    maximum_cost_usd: float,
    now: datetime | None = None,
) -> BudgetReservation:
    current = now or datetime.now(UTC)
    reserved = _microusd(maximum_cost_usd)
    limit = _microusd(settings.ai_daily_budget_usd)
    if reserved <= 0 or limit <= 0:
        raise AiBudgetExceeded("AI coach spending is disabled by the daily budget")
    row = _locked_daily_row(session, current.date())
    if row.committed_microusd + reserved > limit:
        session.rollback()
        raise AiBudgetExceeded(
            f"Daily AI coach budget of ${settings.ai_daily_budget_usd:.2f} has been reached"
        )
    reservation = AiCostReservation(
        id=f"ai-{uuid.uuid4().hex}",
        day=current.date(),
        provider="anthropic",
        model=settings.anthropic_model,
        username=username,
        status="reserved",
        reserved_microusd=reserved,
    )
    row.committed_microusd += reserved
    session.add(reservation)
    session.commit()
    return BudgetReservation(reservation.id, reserved)


def reconcile_anthropic_call(
    session: Session,
    reservation: BudgetReservation,
    *,
    actual_cost_usd: float,
) -> None:
    row = session.scalar(
        select(AiCostReservation)
        .where(AiCostReservation.id == reservation.id)
        .with_for_update()
    )
    if row is None or row.status != "reserved":
        session.rollback()
        raise RuntimeError("AI cost reservation is missing or already reconciled")
    daily = session.scalar(
        select(AiDailyBudget).where(AiDailyBudget.day == row.day).with_for_update()
    )
    if daily is None:
        session.rollback()
        raise RuntimeError("AI daily budget ledger is missing")
    actual = _microusd(actual_cost_usd)
    daily.committed_microusd += actual - row.reserved_microusd
    row.actual_microusd = actual
    row.status = "reconciled"
    session.commit()
