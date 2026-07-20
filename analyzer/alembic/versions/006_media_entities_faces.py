"""Medias unifies, entities spaCy, persons + faces.

Revision ID: 006
Revises: 005
Create Date: 2026-07-20

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_type():
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _json_object_default():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return sa.text("'{}'")
    return sa.text("'{}'::jsonb")


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    is_sqlite = bind.dialect.name == "sqlite"
    json_t = _json_type()

    if not insp.has_table("article_media"):
        op.create_table(
            "article_media",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("article_id", sa.Integer(), nullable=False),
            sa.Column("media_type", sa.String(length=20), server_default="image", nullable=False),
            sa.Column("url", sa.String(length=2000), nullable=False),
            sa.Column("mime_type", sa.String(length=100), nullable=True),
            sa.Column("title", sa.String(length=500), nullable=True),
            sa.Column("alt", sa.String(length=500), nullable=True),
            sa.Column("source", sa.String(length=50), nullable=True),
            sa.Column("thumbnail_url", sa.String(length=2000), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("width", sa.Integer(), nullable=True),
            sa.Column("height", sa.Integer(), nullable=True),
            sa.Column("is_primary", sa.Boolean(), server_default="0", nullable=False),
            sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
            sa.Column("extra", json_t, server_default=_json_object_default(), nullable=False),
            sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("article_id", "url", name="article_media_article_id_url_key"),
        )
        op.create_index("idx_article_media_article", "article_media", ["article_id"])
        op.create_index(
            "idx_article_media_article_type",
            "article_media",
            ["article_id", "media_type"],
        )

    # Copie article_images -> article_media
    if insp.has_table("article_images"):
        op.execute(
            """
            INSERT INTO article_media
                (article_id, media_type, url, alt, source, is_primary, sort_order, extra)
            SELECT
                article_id, 'image', url, alt, source, is_primary, sort_order,
                '{}'
            FROM article_images
            WHERE NOT EXISTS (
                SELECT 1 FROM article_media m
                WHERE m.article_id = article_images.article_id
                  AND m.url = article_images.url
            )
            """
            if is_sqlite
            else """
            INSERT INTO article_media
                (article_id, media_type, url, alt, source, is_primary, sort_order, extra)
            SELECT
                article_id, 'image', url, alt, source, is_primary, sort_order,
                '{}'::jsonb
            FROM article_images
            WHERE NOT EXISTS (
                SELECT 1 FROM article_media m
                WHERE m.article_id = article_images.article_id
                  AND m.url = article_images.url
            )
            """
        )
        op.drop_table("article_images")

    if not insp.has_table("persons"):
        op.create_table(
            "persons",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("display_name", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
            sa.Column("meta", json_t, server_default=_json_object_default(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if not insp.has_table("article_entities"):
        op.create_table(
            "article_entities",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("article_id", sa.Integer(), nullable=False),
            sa.Column("text", sa.String(length=500), nullable=False),
            sa.Column("label", sa.String(length=100), nullable=False),
            sa.Column("start_char", sa.Integer(), nullable=True),
            sa.Column("end_char", sa.Integer(), nullable=True),
            sa.Column("source", sa.String(length=50), server_default="ner_spacy", nullable=False),
            sa.Column("person_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "article_id",
                "text",
                "label",
                "source",
                name="article_entities_article_text_label_source_key",
            ),
        )
        op.create_index("idx_article_entities_article", "article_entities", ["article_id"])
        op.create_index("idx_article_entities_person", "article_entities", ["person_id"])

    if not insp.has_table("article_faces"):
        blob = sa.LargeBinary() if is_sqlite else postgresql.BYTEA()
        op.create_table(
            "article_faces",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("article_id", sa.Integer(), nullable=False),
            sa.Column("media_id", sa.Integer(), nullable=True),
            sa.Column("person_id", sa.Integer(), nullable=True),
            sa.Column("bbox_x", sa.Float(), nullable=True),
            sa.Column("bbox_y", sa.Float(), nullable=True),
            sa.Column("bbox_w", sa.Float(), nullable=True),
            sa.Column("bbox_h", sa.Float(), nullable=True),
            sa.Column("bbox_unit", sa.String(length=20), server_default="ratio", nullable=False),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("embedding", blob, nullable=True),
            sa.Column("embedding_dim", sa.Integer(), nullable=True),
            sa.Column("tool_name", sa.String(length=100), server_default="face_detect", nullable=False),
            sa.Column("detected_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["media_id"], ["article_media.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_article_faces_article", "article_faces", ["article_id"])
        op.create_index("idx_article_faces_media", "article_faces", ["media_id"])
        op.create_index("idx_article_faces_person", "article_faces", ["person_id"])

    if is_sqlite:
        op.execute("ANALYZE")
    else:
        op.execute("ANALYZE article_media")
        op.execute("ANALYZE article_entities")
        op.execute("ANALYZE article_faces")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    is_sqlite = bind.dialect.name == "sqlite"
    json_t = _json_type()

    if insp.has_table("article_faces"):
        op.drop_table("article_faces")
    if insp.has_table("article_entities"):
        op.drop_table("article_entities")
    if insp.has_table("persons"):
        op.drop_table("persons")

    if not insp.has_table("article_images") and insp.has_table("article_media"):
        op.create_table(
            "article_images",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("article_id", sa.Integer(), nullable=False),
            sa.Column("url", sa.String(length=2000), nullable=False),
            sa.Column("alt", sa.String(length=500), nullable=True),
            sa.Column("source", sa.String(length=50), nullable=True),
            sa.Column("is_primary", sa.Boolean(), server_default="0", nullable=False),
            sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
            sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("article_id", "url", name="article_images_article_id_url_key"),
        )
        op.execute(
            """
            INSERT INTO article_images
                (article_id, url, alt, source, is_primary, sort_order)
            SELECT article_id, url, alt, source, is_primary, sort_order
            FROM article_media
            WHERE media_type = 'image'
            """
        )
        op.drop_table("article_media")
