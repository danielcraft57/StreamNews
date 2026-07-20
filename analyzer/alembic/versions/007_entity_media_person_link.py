"""article_entities.media_id + index persons name.

Revision ID: 007
Revises: 006
Create Date: 2026-07-20
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _cols(insp, table: str) -> set[str]:
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    is_sqlite = bind.dialect.name == "sqlite"

    if insp.has_table("article_entities") and "media_id" not in _cols(insp, "article_entities"):
        if is_sqlite:
            with op.batch_alter_table("article_entities") as batch:
                batch.add_column(sa.Column("media_id", sa.Integer(), nullable=True))
                batch.create_foreign_key(
                    "article_entities_media_id_fkey",
                    "article_media",
                    ["media_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
        else:
            op.add_column(
                "article_entities",
                sa.Column("media_id", sa.Integer(), nullable=True),
            )
            op.create_foreign_key(
                "article_entities_media_id_fkey",
                "article_entities",
                "article_media",
                ["media_id"],
                ["id"],
                ondelete="SET NULL",
            )
        op.create_index(
            "idx_article_entities_media",
            "article_entities",
            ["media_id"],
        )

    if insp.has_table("persons"):
        # Index pour lookup par nom (lien NER <-> persons)
        if is_sqlite:
            op.execute(
                "CREATE INDEX IF NOT EXISTS idx_persons_display_name "
                "ON persons (display_name)"
            )
        else:
            op.execute(
                "CREATE INDEX IF NOT EXISTS idx_persons_display_name "
                "ON persons (display_name)"
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    is_sqlite = bind.dialect.name == "sqlite"
    if insp.has_table("article_entities") and "media_id" in _cols(insp, "article_entities"):
        op.drop_index("idx_article_entities_media", table_name="article_entities")
        if is_sqlite:
            with op.batch_alter_table("article_entities") as batch:
                batch.drop_constraint("article_entities_media_id_fkey", type_="foreignkey")
                batch.drop_column("media_id")
        else:
            op.drop_constraint("article_entities_media_id_fkey", "article_entities", type_="foreignkey")
            op.drop_column("article_entities", "media_id")
    op.execute("DROP INDEX IF EXISTS idx_persons_display_name")
