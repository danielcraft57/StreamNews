"""radar_ideas table — snapshots d'opportunites calculees.

Revision ID: 009
Revises: 008
Create Date: 2026-07-22
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("radar_ideas"):
        return
    op.create_table(
        "radar_ideas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("theme", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("intent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("article_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("window_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("sample_titles", sa.Text(), nullable=True),
        sa.Column("sample_snippets", sa.Text(), nullable=True),
        sa.Column("evidence_ids", sa.Text(), nullable=True),
        sa.Column("intents", sa.Text(), nullable=True),
        sa.Column("computed_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("idx_radar_window_score", "radar_ideas", ["window_days", "score"])
    op.create_index("idx_radar_theme", "radar_ideas", ["theme"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("radar_ideas"):
        return
    op.drop_index("idx_radar_theme", table_name="radar_ideas")
    op.drop_index("idx_radar_window_score", table_name="radar_ideas")
    op.drop_table("radar_ideas")
