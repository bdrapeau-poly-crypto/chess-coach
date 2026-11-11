"""Add player accounts and revocable sessions without altering game analysis."""

import sqlalchemy as sa
from alembic import op

revision = "b412fc5e901a"
down_revision = "8a91c30f2d47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("login_name", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("workspace_username", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "player_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("player_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_player_sessions_account_id", "player_sessions", ["account_id"])
    op.create_index("ix_player_sessions_expires_at", "player_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_table("player_sessions")
    op.drop_table("player_accounts")
