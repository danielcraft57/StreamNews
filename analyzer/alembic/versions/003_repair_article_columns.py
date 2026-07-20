"""Reparation colonnes articles (002 partielle sur BDD existantes).

Revision ID: 003
Revises: 002
Create Date: 2026-07-20

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from schema_migrate_helpers import (
    cleanup_sqlite_alembic_temp_tables,
    ensure_article_extension_columns,
    ensure_article_indexes,
)

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    cleanup_sqlite_alembic_temp_tables()
    is_sqlite = op.get_bind().dialect.name == "sqlite"
    ensure_article_extension_columns(is_sqlite)
    ensure_article_indexes(is_sqlite)


def downgrade() -> None:
    pass
