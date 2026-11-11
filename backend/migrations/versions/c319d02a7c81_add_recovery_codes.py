"""Add hashed single-use account recovery codes."""

import sqlalchemy as sa
from alembic import op

revision = "c319d02a7c81"
down_revision = "b412fc5e901a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_recovery_codes",
        sa.Column("code_hash", sa.String(64), primary_key=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("player_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_player_recovery_codes_account_id", "player_recovery_codes", ["account_id"])


def downgrade() -> None:
    op.drop_table("player_recovery_codes")
