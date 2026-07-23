"""Radar score_breakdown + indexes Postgres-friendly.

Revision ID: 012
Revises: 011
Create Date: 2026-07-23
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if insp.has_table("radar_ideas"):
        cols = {c["name"] for c in insp.get_columns("radar_ideas")}
        if "score_breakdown" not in cols:
            op.add_column("radar_ideas", sa.Column("score_breakdown", sa.Text(), nullable=True))

    # Index utiles en prod (no-op si deja la)
    if insp.has_table("trends"):
        existing = {ix["name"] for ix in insp.get_indexes("trends")}
        if "idx_trends_window_site_score" not in existing:
            op.create_index(
                "idx_trends_window_site_score",
                "trends",
                ["window_days", "site_id", "score"],
            )

    if insp.has_table("collection_sites"):
        existing = {ix["name"] for ix in insp.get_indexes("collection_sites")}
        if "idx_collection_sites_site" not in existing:
            op.create_index(
                "idx_collection_sites_site",
                "collection_sites",
                ["site_id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("collection_sites"):
        existing = {ix["name"] for ix in insp.get_indexes("collection_sites")}
        if "idx_collection_sites_site" in existing:
            op.drop_index("idx_collection_sites_site", table_name="collection_sites")
    if insp.has_table("trends"):
        existing = {ix["name"] for ix in insp.get_indexes("trends")}
        if "idx_trends_window_site_score" in existing:
            op.drop_index("idx_trends_window_site_score", table_name="trends")
    if insp.has_table("radar_ideas"):
        cols = {c["name"] for c in insp.get_columns("radar_ideas")}
        if "score_breakdown" in cols:
            op.drop_column("radar_ideas", "score_breakdown")
