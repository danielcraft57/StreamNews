"""Daily briefs table.

Revision ID: 011
Revises: 010
Create Date: 2026-07-23
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("daily_briefs"):
        op.create_table(
            "daily_briefs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("day", sa.String(length=20), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("computed_at", sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index("idx_daily_briefs_day", "daily_briefs", ["day"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("daily_briefs"):
        op.drop_index("idx_daily_briefs_day", table_name="daily_briefs")
        op.drop_table("daily_briefs")
