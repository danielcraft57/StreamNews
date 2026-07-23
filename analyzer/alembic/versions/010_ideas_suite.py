"""Watchlist, brief, collections, idea_notes.

Revision ID: 010
Revises: 009
Create Date: 2026-07-23
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("watch_keywords"):
        op.create_table(
            "watch_keywords",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("keyword", sa.String(length=200), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index("idx_watch_keywords_kw", "watch_keywords", ["keyword"], unique=True)

    if not insp.has_table("watch_alerts"):
        op.create_table(
            "watch_alerts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("keyword", sa.String(length=200), nullable=False),
            sa.Column("score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("delta", sa.Float(), nullable=False, server_default="0"),
            sa.Column("current_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("previous_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("window_days", sa.Integer(), nullable=False, server_default="7"),
            sa.Column("sample_titles", sa.Text(), nullable=True),
            sa.Column("computed_at", sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index("idx_watch_alerts_score", "watch_alerts", ["window_days", "score"])

    if not insp.has_table("weekly_briefs"):
        op.create_table(
            "weekly_briefs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("week_start", sa.String(length=20), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("computed_at", sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index("idx_weekly_briefs_week", "weekly_briefs", ["week_start"], unique=True)

    if not insp.has_table("collections"):
        op.create_table(
            "collections",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("slug", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index("idx_collections_slug", "collections", ["slug"], unique=True)

    if not insp.has_table("collection_sites"):
        op.create_table(
            "collection_sites",
            sa.Column("collection_id", sa.Integer(), nullable=False),
            sa.Column("site_id", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("collection_id", "site_id"),
        )

    if not insp.has_table("idea_notes"):
        op.create_table(
            "idea_notes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("theme", sa.String(length=80), nullable=True),
            sa.Column("problem", sa.Text(), nullable=True),
            sa.Column("evidence", sa.Text(), nullable=True),
            sa.Column("mvp_plan", sa.Text(), nullable=True),
            sa.Column("source_refs", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="draft"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table in (
        "idea_notes",
        "collection_sites",
        "collections",
        "weekly_briefs",
        "watch_alerts",
        "watch_keywords",
    ):
        if insp.has_table(table):
            op.drop_table(table)
