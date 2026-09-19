"""add durable AI cost ledger

Revision ID: 8a91c30f2d47
Revises: 01bac4104c53
Create Date: 2026-09-19 06:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8a91c30f2d47"
down_revision: str | None = "01bac4104c53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_daily_budgets",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("committed_microusd", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("day"),
    )
    op.create_table(
        "ai_cost_reservations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reserved_microusd", sa.Integer(), nullable=False),
        sa.Column("actual_microusd", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ai_cost_reservations_day"), "ai_cost_reservations", ["day"], unique=False
    )
    op.create_index(
        op.f("ix_ai_cost_reservations_status"),
        "ai_cost_reservations",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_cost_reservations_username"),
        "ai_cost_reservations",
        ["username"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_cost_reservations_username"), table_name="ai_cost_reservations")
    op.drop_index(op.f("ix_ai_cost_reservations_status"), table_name="ai_cost_reservations")
    op.drop_index(op.f("ix_ai_cost_reservations_day"), table_name="ai_cost_reservations")
    op.drop_table("ai_cost_reservations")
    op.drop_table("ai_daily_budgets")
