"""Repository articles : lectures normalisees -> entites Pydantic."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from models.entities import (
    ArticleAnalysisRecord,
    ArticleEntityRecord,
    ArticleFaceRecord,
    ArticleKeywordRecord,
    ArticleMediaRecord,
    ArticleMetaNormRecord,
    ArticleRecord,
)
from repositories.normalized_sync import has_normalized_tables


def _parse_json(value: Any, default: Any):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode()
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


def _as_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _row_base(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": int(row["id"]),
        "site_id": int(row["site_id"]),
        "feed_id": int(row["feed_id"]) if row.get("feed_id") is not None else None,
        "feed_url": row.get("feed_url") or "",
        "title": row.get("title"),
        "link": row["link"],
        "summary": row.get("summary"),
        "author": row.get("author"),
        "published_at": _as_dt(row.get("published_at")),
        "guid": row.get("guid"),
        "content_html": row.get("content_html"),
        "content_text": row.get("content_text"),
        "enrich_status": row.get("enrich_status"),
        "enrich_error": row.get("enrich_error"),
        "enriched_at": _as_dt(row.get("enriched_at")),
        "analysis_status": row.get("analysis_status"),
        "analysis_error": row.get("analysis_error"),
        "analyzed_at": _as_dt(row.get("analyzed_at")),
        "fetched_at": _as_dt(row.get("fetched_at")),
    }


async def _load_relations(
    conn,
    article_ids: List[int],
    *,
    with_analyses: bool,
    with_content: bool = True,
) -> Dict[int, Dict[str, Any]]:
    """Charge images/keywords/analyses/meta pour un lot d'ids."""
    empty = {
        aid: {
            "media": [],
            "images": [],
            "keywords": [],
            "entities": [],
            "faces": [],
            "analyses": [],
            "meta_norm": None,
        }
        for aid in article_ids
    }
    if not article_ids:
        return empty

    placeholders = ", ".join(f"${i + 1}" for i in range(len(article_ids)))

    img_rows = await conn.fetch(
        f"""
        SELECT id, article_id, media_type, url, mime_type, title, alt, source,
               thumbnail_url, duration_ms, width, height, is_primary, sort_order, extra
        FROM article_media
        WHERE article_id IN ({placeholders})
        ORDER BY sort_order ASC, id ASC
        """,
        *article_ids,
    )
    for row in img_rows:
        aid = int(row["article_id"])
        extra = _parse_json(row.get("extra"), {})
        if not isinstance(extra, dict):
            extra = {}
        empty[aid]["media"].append(
            ArticleMediaRecord(
                id=int(row["id"]),
                article_id=aid,
                media_type=row.get("media_type") or "image",
                url=row["url"],
                mime_type=row.get("mime_type"),
                title=row.get("title"),
                alt=row.get("alt"),
                source=row.get("source"),
                thumbnail_url=row.get("thumbnail_url"),
                duration_ms=row.get("duration_ms"),
                width=row.get("width"),
                height=row.get("height"),
                is_primary=bool(row["is_primary"]),
                sort_order=int(row["sort_order"] or 0),
                extra=extra,
            )
        )
        if (row.get("media_type") or "image") == "image":
            empty[aid]["images"].append(empty[aid]["media"][-1])

    kw_rows = await conn.fetch(
        f"""
        SELECT id, article_id, keyword, source
        FROM article_keywords
        WHERE article_id IN ({placeholders})
        ORDER BY id ASC
        """,
        *article_ids,
    )
    for row in kw_rows:
        aid = int(row["article_id"])
        empty[aid]["keywords"].append(
            ArticleKeywordRecord(
                id=int(row["id"]),
                article_id=aid,
                keyword=row["keyword"],
                source=row["source"] or "unknown",
            )
        )

    try:
        ent_rows = await conn.fetch(
            f"""
            SELECT id, article_id, text, label, start_char, end_char, source, person_id, media_id
            FROM article_entities
            WHERE article_id IN ({placeholders})
            ORDER BY id ASC
            """,
            *article_ids,
        )
        for row in ent_rows:
            aid = int(row["article_id"])
            empty[aid]["entities"].append(
                ArticleEntityRecord(
                    id=int(row["id"]),
                    article_id=aid,
                    text=row["text"],
                    label=row["label"],
                    start_char=row.get("start_char"),
                    end_char=row.get("end_char"),
                    source=row.get("source") or "ner_spacy",
                    person_id=int(row["person_id"]) if row.get("person_id") is not None else None,
                    media_id=int(row["media_id"]) if row.get("media_id") is not None else None,
                )
            )
    except Exception:
        pass

    try:
        face_rows = await conn.fetch(
            f"""
            SELECT id, article_id, media_id, person_id, bbox_x, bbox_y, bbox_w, bbox_h,
                   bbox_unit, confidence, embedding_dim, tool_name, detected_at
            FROM article_faces
            WHERE article_id IN ({placeholders})
            ORDER BY id ASC
            """,
            *article_ids,
        )
        for row in face_rows:
            aid = int(row["article_id"])
            empty[aid]["faces"].append(
                ArticleFaceRecord(
                    id=int(row["id"]),
                    article_id=aid,
                    media_id=int(row["media_id"]) if row.get("media_id") is not None else None,
                    person_id=int(row["person_id"]) if row.get("person_id") is not None else None,
                    bbox_x=row.get("bbox_x"),
                    bbox_y=row.get("bbox_y"),
                    bbox_w=row.get("bbox_w"),
                    bbox_h=row.get("bbox_h"),
                    bbox_unit=row.get("bbox_unit") or "ratio",
                    confidence=row.get("confidence"),
                    embedding_dim=row.get("embedding_dim"),
                    tool_name=row.get("tool_name") or "face_detect",
                    detected_at=_as_dt(row.get("detected_at")),
                )
            )
    except Exception:
        pass

    norm_rows = await conn.fetch(
        f"SELECT * FROM article_meta_norm WHERE article_id IN ({placeholders})",
        *article_ids,
    )
    for row in norm_rows:
        aid = int(row["article_id"])
        extra = _parse_json(row.get("extra"), {})
        if not isinstance(extra, dict):
            extra = {}
        empty[aid]["meta_norm"] = ArticleMetaNormRecord(
            article_id=aid,
            canonical_url=row.get("canonical_url"),
            date_published=_as_dt(row.get("date_published")),
            schema_type=row.get("schema_type"),
            reading_time_minutes=row.get("reading_time_minutes"),
            primary_image_url=row.get("primary_image_url"),
            domain=row.get("domain"),
            extra=extra,
        )

    if with_analyses:
        an_rows = await conn.fetch(
            f"""
            SELECT id, article_id, tool_name, status, result, error_message, analyzed_at
            FROM article_analyses
            WHERE article_id IN ({placeholders})
            """,
            *article_ids,
        )
        for row in an_rows:
            aid = int(row["article_id"])
            result = _parse_json(row.get("result"), {})
            if not isinstance(result, dict):
                result = {}
            empty[aid]["analyses"].append(
                ArticleAnalysisRecord(
                    id=int(row["id"]),
                    article_id=aid,
                    tool_name=row["tool_name"],
                    status=row["status"],
                    result=result,
                    error_message=row.get("error_message"),
                    analyzed_at=_as_dt(row.get("analyzed_at")),
                )
            )

    return empty


class ArticlesRepository:
    def __init__(self, pool, *, is_sqlite: bool):
        self.pool = pool
        self.is_sqlite = is_sqlite

    async def get_by_id(self, article_id: int) -> Optional[ArticleRecord]:
        async with self.pool.acquire() as conn:
            if not await has_normalized_tables(conn, is_sqlite=self.is_sqlite):
                return None
            row = await conn.fetchrow("SELECT * FROM articles WHERE id = $1", article_id)
            if not row:
                return None
            data = dict(row)
            rel = await _load_relations(conn, [article_id], with_analyses=True)
            base = _row_base(data)
            base.update(rel[article_id])
            return ArticleRecord(**base)

    async def list_by_site(
        self, site_id: int, *, limit: int = 100, with_body: bool = False
    ) -> List[ArticleRecord]:
        order = (
            "ORDER BY published_at DESC, fetched_at DESC"
            if self.is_sqlite
            else "ORDER BY published_at DESC NULLS LAST, fetched_at DESC"
        )
        cols = (
            "id, site_id, feed_id, feed_url, title, link, summary, author, "
            "published_at, guid, fetched_at, enrich_status, enrich_error, enriched_at, "
            "analysis_status, analysis_error, analyzed_at"
        )
        if with_body:
            cols += ", content_html, content_text"

        async with self.pool.acquire() as conn:
            if not await has_normalized_tables(conn, is_sqlite=self.is_sqlite):
                return []
            rows = await conn.fetch(
                f"""
                SELECT {cols}
                FROM articles
                WHERE site_id = $1
                {order}
                LIMIT $2
                """,
                site_id,
                limit,
            )
            if not rows:
                return []
            ids = [int(r["id"]) for r in rows]
            rel = await _load_relations(conn, ids, with_analyses=with_body)
            out: List[ArticleRecord] = []
            for row in rows:
                base = _row_base(dict(row))
                base.update(rel[int(row["id"])])
                out.append(ArticleRecord(**base))
            return out

    async def search(
        self,
        query: str,
        *,
        site_id: Optional[int] = None,
        limit: int = 40,
    ) -> List[ArticleRecord]:
        """Recherche texte simple (titre / resume / contenu)."""
        q = (query or "").strip()
        if len(q) < 2:
            return []
        limit = max(1, min(int(limit or 40), 100))
        like = f"%{q}%"
        order = (
            "ORDER BY published_at DESC, fetched_at DESC"
            if self.is_sqlite
            else "ORDER BY published_at DESC NULLS LAST, fetched_at DESC"
        )
        cols = (
            "id, site_id, feed_id, feed_url, title, link, summary, author, "
            "published_at, guid, fetched_at, enrich_status, enrich_error, enriched_at, "
            "analysis_status, analysis_error, analyzed_at"
        )
        async with self.pool.acquire() as conn:
            if not await has_normalized_tables(conn, is_sqlite=self.is_sqlite):
                return []
            if site_id:
                rows = await conn.fetch(
                    f"""
                    SELECT {cols}
                    FROM articles
                    WHERE site_id = $1
                      AND (
                        title LIKE $2 COLLATE NOCASE
                        OR IFNULL(summary, '') LIKE $2 COLLATE NOCASE
                        OR IFNULL(content_text, '') LIKE $2 COLLATE NOCASE
                        OR IFNULL(author, '') LIKE $2 COLLATE NOCASE
                      )
                    {order}
                    LIMIT $3
                    """
                    if self.is_sqlite
                    else f"""
                    SELECT {cols}
                    FROM articles
                    WHERE site_id = $1
                      AND (
                        title ILIKE $2
                        OR COALESCE(summary, '') ILIKE $2
                        OR COALESCE(content_text, '') ILIKE $2
                        OR COALESCE(author, '') ILIKE $2
                      )
                    {order}
                    LIMIT $3
                    """,
                    site_id,
                    like,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    f"""
                    SELECT {cols}
                    FROM articles
                    WHERE (
                        title LIKE $1 COLLATE NOCASE
                        OR IFNULL(summary, '') LIKE $1 COLLATE NOCASE
                        OR IFNULL(content_text, '') LIKE $1 COLLATE NOCASE
                        OR IFNULL(author, '') LIKE $1 COLLATE NOCASE
                      )
                    {order}
                    LIMIT $2
                    """
                    if self.is_sqlite
                    else f"""
                    SELECT {cols}
                    FROM articles
                    WHERE (
                        title ILIKE $1
                        OR COALESCE(summary, '') ILIKE $1
                        OR COALESCE(content_text, '') ILIKE $1
                        OR COALESCE(author, '') ILIKE $1
                      )
                    {order}
                    LIMIT $2
                    """,
                    like,
                    limit,
                )
            if not rows:
                return []
            ids = [int(r["id"]) for r in rows]
            rel = await _load_relations(conn, ids, with_analyses=False)
            out: List[ArticleRecord] = []
            for row in rows:
                base = _row_base(dict(row))
                base.update(rel[int(row["id"])])
                out.append(ArticleRecord(**base))
            return out
