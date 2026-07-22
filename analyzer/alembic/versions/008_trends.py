"""trends table — snapshots de tendances calculees.

Revision ID: 008
Revises: 007
Create Date: 2026-07-22
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("trends"):
        return
    op.create_table(
        "trends",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("term", sa.String(length=500), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False, server_default="keyword"),
        sa.Column("label", sa.String(length=50), nullable=True),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("article_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("window_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("site_id", sa.Integer(), nullable=True),
        sa.Column("computed_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("sample_titles", sa.Text(), nullable=True),
    )
    op.create_index("idx_trends_window_score", "trends", ["window_days", "score"])
    op.create_index("idx_trends_term", "trends", ["term"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("trends"):
        return
    op.drop_index("idx_trends_term", table_name="trends")
    op.drop_index("idx_trends_window_score", table_name="trends")
    op.drop_table("trends")
