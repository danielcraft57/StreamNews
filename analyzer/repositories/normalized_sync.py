"""Dual-write vers tables normalisees (Phase 2)."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


def parse_dt(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


async def has_normalized_tables(conn, *, is_sqlite: bool) -> bool:
    if is_sqlite:
        row = await conn.fetchrow(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='rss_feeds'"
        )
        return bool(row and row.get("name") == "rss_feeds")
    row = await conn.fetchrow(
        "SELECT to_regclass('public.rss_feeds') IS NOT NULL AS ok"
    )
    return bool(row and row.get("ok"))


async def ensure_rss_feed(
    conn,
    *,
    is_sqlite: bool,
    site_id: int,
    url: str,
    title: str = "Flux RSS",
    feed_type: str = "detected",
    source_page_id: Optional[int] = None,
) -> Optional[int]:
    url = (url or "").strip()[:1000]
    if not url:
        return None
    title = (title or "Flux RSS")[:500]
    feed_type = (feed_type or "detected")[:50]

    if is_sqlite:
        await conn.execute(
            """
            INSERT OR IGNORE INTO rss_feeds (site_id, url, title, feed_type, source_page_id)
            VALUES ($1, $2, $3, $4, $5)
            """,
            site_id,
            url,
            title,
            feed_type,
            source_page_id,
        )
        row = await conn.fetchrow(
            "SELECT id FROM rss_feeds WHERE site_id = $1 AND url = $2",
            site_id,
            url,
        )
    else:
        row = await conn.fetchrow(
            """
            INSERT INTO rss_feeds (site_id, url, title, feed_type, source_page_id)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (site_id, url) DO UPDATE SET
                title = EXCLUDED.title,
                feed_type = EXCLUDED.feed_type,
                source_page_id = COALESCE(EXCLUDED.source_page_id, rss_feeds.source_page_id)
            RETURNING id
            """,
            site_id,
            url,
            title,
            feed_type,
            source_page_id,
        )
    return int(row["id"]) if row else None


async def sync_rss_feeds_list(
    conn,
    *,
    is_sqlite: bool,
    site_id: int,
    feeds: List[Dict],
    source_page_id: Optional[int] = None,
) -> None:
    if not isinstance(feeds, list):
        return
    for feed in feeds:
        if not isinstance(feed, dict) or not feed.get("url"):
            continue
        await ensure_rss_feed(
            conn,
            is_sqlite=is_sqlite,
            site_id=site_id,
            url=feed.get("url", ""),
            title=feed.get("title", "Flux RSS"),
            feed_type=feed.get("type", "detected"),
            source_page_id=source_page_id,
        )


def keyword_rows(meta: Dict[str, Any], article_id: int) -> List[Tuple[int, str, str]]:
    rows: List[Tuple[int, str, str]] = []
    seen = set()
    raw = meta.get("keywords")
    if not isinstance(raw, list):
        return rows
    for item in raw:
        if isinstance(item, str):
            kw, src = item.strip(), "meta"
        elif isinstance(item, dict):
            kw = str(item.get("keyword") or item.get("term") or item.get("name") or "").strip()
            src = str(item.get("source") or "meta")
        else:
            continue
        if not kw or len(kw) > 500:
            continue
        key = (kw.lower(), src)
        if key in seen:
            continue
        seen.add(key)
        rows.append((article_id, kw[:500], src[:50]))
    return rows


def media_rows(
    items: Any,
    article_id: int,
    meta: Dict[str, Any],
    *,
    default_type: str = "image",
) -> List[Tuple]:
    if not isinstance(items, list):
        items = []
    primary_url = meta.get("primary_image")
    rows: List[Tuple] = []
    for idx, item in enumerate(items):
        if isinstance(item, str):
            url, alt, source = item, "", "legacy"
            media_type, mime, title, thumb = default_type, None, None, None
            duration_ms = width = height = None
            extra = "{}"
        elif isinstance(item, dict):
            url = item.get("url")
            alt = item.get("alt") or ""
            source = item.get("source") or "legacy"
            media_type = str(item.get("media_type") or item.get("type") or default_type)[:20]
            if media_type not in ("image", "video", "audio"):
                media_type = default_type
            mime = (str(item["mime_type"])[:100] if item.get("mime_type") else None)
            title = (str(item["title"])[:500] if item.get("title") else None)
            thumb = (str(item["thumbnail_url"])[:2000] if item.get("thumbnail_url") else None)
            duration_ms = item.get("duration_ms") if isinstance(item.get("duration_ms"), int) else None
            width = item.get("width") if isinstance(item.get("width"), int) else None
            height = item.get("height") if isinstance(item.get("height"), int) else None
            extra_obj = item.get("extra") if isinstance(item.get("extra"), dict) else {}
            extra = json.dumps(extra_obj) if extra_obj else "{}"
        else:
            continue
        if not url or not str(url).strip():
            continue
        url = str(url).strip()[:2000]
        is_primary = bool(primary_url and str(primary_url).strip() == url) or (
            media_type == "image" and idx == 0 and default_type == "image"
        )
        rows.append(
            (
                article_id,
                media_type,
                url,
                mime,
                title,
                str(alt)[:500] or None,
                str(source)[:50] or None,
                thumb,
                duration_ms,
                width,
                height,
                is_primary,
                idx,
                extra,
            )
        )
    if rows and default_type == "image" and not any(r[11] for r in rows if r[1] == "image"):
        for i, r in enumerate(rows):
            if r[1] == "image":
                rows[i] = (*r[:11], True, *r[12:])
                break
    return rows


def image_rows(images: Any, article_id: int, meta: Dict[str, Any]) -> List[Tuple]:
    return [
        (r[0], r[2], r[5], r[6], r[11], r[12])
        for r in media_rows(images, article_id, meta, default_type="image")
    ]


def meta_norm_row(article_id: int, meta: Dict[str, Any]) -> Tuple:
    known = {
        "canonical",
        "canonical_url",
        "page_url",
        "date_published",
        "schema_type",
        "reading_time_minutes",
        "primary_image",
        "domain",
        "keywords",
        "analysis",
        "analysis_status",
        "analysis_error",
        "analyzed_at",
        "sources",
    }
    extra = {k: v for k, v in meta.items() if k not in known}
    canonical = meta.get("canonical_url") or meta.get("canonical") or meta.get("page_url")
    return (
        article_id,
        (str(canonical)[:2000] if canonical else None),
        parse_dt(meta.get("date_published")),
        (str(meta.get("schema_type"))[:100] if meta.get("schema_type") else None),
        meta.get("reading_time_minutes") if isinstance(meta.get("reading_time_minutes"), int) else None,
        (str(meta.get("primary_image"))[:2000] if meta.get("primary_image") else None),
        (str(meta.get("domain"))[:255] if meta.get("domain") else None),
        json.dumps(extra) if extra else "{}",
    )


async def sync_article_media(
    conn,
    *,
    is_sqlite: bool,
    article_id: int,
    media_items: Any,
    meta: Optional[Dict[str, Any]] = None,
    default_type: str = "image",
) -> None:
    meta = meta if isinstance(meta, dict) else {}
    # Compat migrations < 006 : table article_images encore presente
    if is_sqlite:
        probe = await conn.fetchrow(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='article_media'"
        )
        use_media = bool(probe)
    else:
        probe = await conn.fetchrow(
            "SELECT to_regclass('public.article_media') IS NOT NULL AS ok"
        )
        use_media = bool(probe and probe.get("ok"))

    if not use_media:
        # Legacy article_images (images only)
        for row in image_rows(media_items, article_id, meta):
            if is_sqlite:
                await conn.execute(
                    """
                    INSERT OR IGNORE INTO article_images
                        (article_id, url, alt, source, is_primary, sort_order)
                    SELECT $1, $2, $3, $4, $5, $6
                    WHERE NOT EXISTS (
                        SELECT 1 FROM article_images
                        WHERE article_id = $1 AND url = $2
                    )
                    """,
                    *row,
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO article_images
                        (article_id, url, alt, source, is_primary, sort_order)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (article_id, url) DO NOTHING
                    """,
                    *row,
                )
        return

    for row in media_rows(media_items, article_id, meta, default_type=default_type):
        if is_sqlite:
            await conn.execute(
                """
                INSERT OR IGNORE INTO article_media
                    (article_id, media_type, url, mime_type, title, alt, source,
                     thumbnail_url, duration_ms, width, height, is_primary, sort_order, extra)
                SELECT $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
                WHERE NOT EXISTS (
                    SELECT 1 FROM article_media
                    WHERE article_id = $1 AND url = $3
                )
                """,
                *row,
            )
        else:
            await conn.execute(
                """
                INSERT INTO article_media
                    (article_id, media_type, url, mime_type, title, alt, source,
                     thumbnail_url, duration_ms, width, height, is_primary, sort_order, extra)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::jsonb)
                ON CONFLICT (article_id, url) DO UPDATE SET
                    media_type = EXCLUDED.media_type,
                    mime_type = COALESCE(EXCLUDED.mime_type, article_media.mime_type),
                    title = COALESCE(EXCLUDED.title, article_media.title),
                    alt = COALESCE(EXCLUDED.alt, article_media.alt),
                    source = COALESCE(EXCLUDED.source, article_media.source),
                    thumbnail_url = COALESCE(EXCLUDED.thumbnail_url, article_media.thumbnail_url),
                    is_primary = EXCLUDED.is_primary OR article_media.is_primary
                """,
                *row,
            )


async def sync_article_images(
    conn,
    *,
    is_sqlite: bool,
    article_id: int,
    images: Any,
    meta: Dict[str, Any],
) -> None:
    await sync_article_media(
        conn,
        is_sqlite=is_sqlite,
        article_id=article_id,
        media_items=images,
        meta=meta,
        default_type="image",
    )


def _normalize_label(label: str) -> str:
    try:
        from text_analysis.ner_spacy import normalize_entity_label

        return normalize_entity_label(label)[:100]
    except Exception:
        return (label or "MISC").strip().upper()[:100] or "MISC"


async def ensure_person(conn, *, is_sqlite: bool, display_name: str) -> Optional[int]:
    """Trouve ou cree une personne par nom affiche (insensible a la casse)."""
    name = (display_name or "").strip()
    if not name or len(name) > 500:
        return None
    row = await conn.fetchrow(
        """
        SELECT id FROM persons
        WHERE lower(display_name) = lower($1)
        LIMIT 1
        """,
        name,
    )
    if row:
        return int(row["id"])
    if is_sqlite:
        await conn.execute(
            "INSERT INTO persons (display_name, meta) VALUES ($1, '{}')",
            name[:500],
        )
        row = await conn.fetchrow(
            """
            SELECT id FROM persons
            WHERE lower(display_name) = lower($1)
            ORDER BY id DESC LIMIT 1
            """,
            name,
        )
    else:
        row = await conn.fetchrow(
            """
            INSERT INTO persons (display_name, meta)
            VALUES ($1, '{}'::jsonb)
            RETURNING id
            """,
            name[:500],
        )
    return int(row["id"]) if row else None


async def link_persons_from_entities(
    conn,
    *,
    is_sqlite: bool,
    article_id: int,
) -> int:
    """Lie les entites PERSON a persons, puis les faces du meme media si univoque."""
    rows = await conn.fetch(
        """
        SELECT id, text, label, media_id, person_id
        FROM article_entities
        WHERE article_id = $1
          AND upper(label) IN ('PERSON', 'PER')
          AND person_id IS NULL
        """,
        article_id,
    )
    linked = 0
    for row in rows:
        person_id = await ensure_person(
            conn, is_sqlite=is_sqlite, display_name=row["text"]
        )
        if not person_id:
            continue
        await conn.execute(
            "UPDATE article_entities SET person_id = $1 WHERE id = $2",
            person_id,
            int(row["id"]),
        )
        linked += 1

    # Faces sans person : si exactement une PERSON sur le meme media_id, on rattache
    face_rows = await conn.fetch(
        """
        SELECT id, media_id FROM article_faces
        WHERE article_id = $1 AND person_id IS NULL AND media_id IS NOT NULL
        """,
        article_id,
    )
    for face in face_rows:
        mid = face.get("media_id")
        if mid is None:
            continue
        persons = await conn.fetch(
            """
            SELECT DISTINCT person_id FROM article_entities
            WHERE article_id = $1
              AND media_id = $2
              AND person_id IS NOT NULL
              AND upper(label) IN ('PERSON', 'PER')
            """,
            article_id,
            mid,
        )
        if len(persons) != 1:
            continue
        await conn.execute(
            "UPDATE article_faces SET person_id = $1 WHERE id = $2",
            int(persons[0]["person_id"]),
            int(face["id"]),
        )
        linked += 1
    return linked


async def sync_article_entities(
    conn,
    *,
    is_sqlite: bool,
    article_id: int,
    entities: Any,
    source: str = "ner_spacy",
    link_persons: bool = True,
) -> None:
    if not isinstance(entities, list):
        return
    default_source = (source or "ner_spacy")[:50]
    for ent in entities:
        media_id = None
        if isinstance(ent, str):
            text, label = ent.strip(), "MISC"
            start_char = end_char = None
            ent_source = default_source
        elif isinstance(ent, dict):
            text = str(ent.get("text") or ent.get("name") or "").strip()
            label = _normalize_label(str(ent.get("label") or ent.get("type") or "MISC"))
            start_char = ent.get("start_char") if isinstance(ent.get("start_char"), int) else None
            end_char = ent.get("end_char") if isinstance(ent.get("end_char"), int) else None
            ent_source = str(ent.get("source") or default_source)[:50]
            raw_mid = ent.get("media_id")
            media_id = int(raw_mid) if isinstance(raw_mid, int) else None
        else:
            continue
        if not text or len(text) > 500:
            continue
        if is_sqlite:
            await conn.execute(
                """
                INSERT OR IGNORE INTO article_entities
                    (article_id, text, label, start_char, end_char, source, media_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                article_id,
                text[:500],
                label,
                start_char,
                end_char,
                ent_source,
                media_id,
            )
        else:
            await conn.execute(
                """
                INSERT INTO article_entities
                    (article_id, text, label, start_char, end_char, source, media_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (article_id, text, label, source) DO UPDATE SET
                    start_char = COALESCE(EXCLUDED.start_char, article_entities.start_char),
                    end_char = COALESCE(EXCLUDED.end_char, article_entities.end_char),
                    media_id = COALESCE(EXCLUDED.media_id, article_entities.media_id)
                """,
                article_id,
                text[:500],
                label,
                start_char,
                end_char,
                ent_source,
                media_id,
            )
    if link_persons:
        await link_persons_from_entities(
            conn, is_sqlite=is_sqlite, article_id=article_id
        )


async def sync_article_faces(
    conn,
    *,
    is_sqlite: bool,
    article_id: int,
    faces: Any,
    tool_name: str = "face_detect",
) -> None:
    if not isinstance(faces, list):
        return
    tool = (tool_name or "face_detect")[:100]
    for face in faces:
        if not isinstance(face, dict):
            continue
        bbox = face.get("bbox") if isinstance(face.get("bbox"), dict) else {}
        embedding = face.get("embedding")
        if embedding is not None and not isinstance(embedding, (bytes, bytearray)):
            embedding = None
        await conn.execute(
            """
            INSERT INTO article_faces
                (article_id, media_id, person_id, bbox_x, bbox_y, bbox_w, bbox_h,
                 bbox_unit, confidence, embedding, embedding_dim, tool_name, detected_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
            article_id,
            face.get("media_id"),
            face.get("person_id"),
            bbox.get("x", face.get("bbox_x")),
            bbox.get("y", face.get("bbox_y")),
            bbox.get("w", face.get("bbox_w")),
            bbox.get("h", face.get("bbox_h")),
            str(face.get("bbox_unit") or bbox.get("unit") or "ratio")[:20],
            face.get("confidence"),
            embedding,
            face.get("embedding_dim"),
            tool,
            parse_dt(face.get("detected_at")),
        )


async def sync_article_keywords(
    conn,
    *,
    is_sqlite: bool,
    article_id: int,
    meta: Dict[str, Any],
) -> None:
    for row in keyword_rows(meta, article_id):
        if is_sqlite:
            await conn.execute(
                """
                INSERT OR IGNORE INTO article_keywords (article_id, keyword, source)
                VALUES ($1, $2, $3)
                """,
                *row,
            )
        else:
            await conn.execute(
                """
                INSERT INTO article_keywords (article_id, keyword, source)
                VALUES ($1, $2, $3)
                ON CONFLICT (article_id, keyword, source) DO NOTHING
                """,
                *row,
            )


async def sync_article_meta_norm(
    conn,
    *,
    is_sqlite: bool,
    article_id: int,
    meta: Dict[str, Any],
) -> None:
    norm = meta_norm_row(article_id, meta)
    if is_sqlite:
        await conn.execute(
            """
            INSERT INTO article_meta_norm
                (article_id, canonical_url, date_published, schema_type,
                 reading_time_minutes, primary_image_url, domain, extra)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT(article_id) DO UPDATE SET
                canonical_url = excluded.canonical_url,
                date_published = excluded.date_published,
                schema_type = excluded.schema_type,
                reading_time_minutes = excluded.reading_time_minutes,
                primary_image_url = excluded.primary_image_url,
                domain = excluded.domain,
                extra = excluded.extra
            """,
            *norm,
        )
    else:
        await conn.execute(
            """
            INSERT INTO article_meta_norm
                (article_id, canonical_url, date_published, schema_type,
                 reading_time_minutes, primary_image_url, domain, extra)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            ON CONFLICT (article_id) DO UPDATE SET
                canonical_url = EXCLUDED.canonical_url,
                date_published = EXCLUDED.date_published,
                schema_type = EXCLUDED.schema_type,
                reading_time_minutes = EXCLUDED.reading_time_minutes,
                primary_image_url = EXCLUDED.primary_image_url,
                domain = EXCLUDED.domain,
                extra = EXCLUDED.extra
            """,
            *norm,
        )


async def sync_article_analyses(
    conn,
    *,
    is_sqlite: bool,
    article_id: int,
    analysis: Dict[str, Any],
) -> None:
    if not isinstance(analysis, dict):
        return
    for tool_name, block in analysis.items():
        if not isinstance(block, dict):
            continue
        tool = str(tool_name)[:100]
        status = str(block.get("status") or "unknown")[:50]
        result = {k: v for k, v in block.items() if k != "status"}
        err = block.get("error") or block.get("message")
        analyzed_tool = parse_dt(block.get("analyzed_at"))
        if is_sqlite:
            await conn.execute(
                """
                INSERT INTO article_analyses
                    (article_id, tool_name, status, result, error_message, analyzed_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT(article_id, tool_name) DO UPDATE SET
                    status = excluded.status,
                    result = excluded.result,
                    error_message = excluded.error_message,
                    analyzed_at = excluded.analyzed_at
                """,
                article_id,
                tool,
                status,
                json.dumps(result),
                str(err)[:2000] if err else None,
                analyzed_tool,
            )
        else:
            await conn.execute(
                """
                INSERT INTO article_analyses
                    (article_id, tool_name, status, result, error_message, analyzed_at)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6)
                ON CONFLICT (article_id, tool_name) DO UPDATE SET
                    status = EXCLUDED.status,
                    result = EXCLUDED.result,
                    error_message = EXCLUDED.error_message,
                    analyzed_at = EXCLUDED.analyzed_at
                """,
                article_id,
                tool,
                status,
                json.dumps(result),
                str(err)[:2000] if err else None,
                analyzed_tool,
            )
        # NER spaCy -> table article_entities
        if tool in ("ner_spacy", "spacy") and status == "ok":
            ents = result.get("entities") or block.get("entities")
            await sync_article_entities(
                conn,
                is_sqlite=is_sqlite,
                article_id=article_id,
                entities=ents,
                source="ner_spacy",
            )
        # Faces stub / outil visage
        if tool in ("face_detect", "face_recognition", "insightface") and status == "ok":
            faces = result.get("faces") or block.get("faces")
            await sync_article_faces(
                conn,
                is_sqlite=is_sqlite,
                article_id=article_id,
                faces=faces,
                tool_name=tool,
            )


async def sync_article_after_upsert(
    conn,
    *,
    is_sqlite: bool,
    site_id: int,
    article_id: int,
    feed_url: str,
    images: Any,
    meta: Dict[str, Any],
    videos: Any = None,
    audios: Any = None,
) -> None:
    feed_id = await ensure_rss_feed(
        conn,
        is_sqlite=is_sqlite,
        site_id=site_id,
        url=feed_url,
        title="Flux RSS",
        feed_type="ingest",
    )
    if feed_id:
        await conn.execute(
            "UPDATE articles SET feed_id = $2 WHERE id = $1",
            article_id,
            feed_id,
        )
    await sync_article_images(conn, is_sqlite=is_sqlite, article_id=article_id, images=images, meta=meta)
    if videos:
        await sync_article_media(
            conn, is_sqlite=is_sqlite, article_id=article_id, media_items=videos, meta=meta, default_type="video"
        )
    if audios:
        await sync_article_media(
            conn, is_sqlite=is_sqlite, article_id=article_id, media_items=audios, meta=meta, default_type="audio"
        )
    await sync_article_keywords(conn, is_sqlite=is_sqlite, article_id=article_id, meta=meta)
    if meta:
        await sync_article_meta_norm(conn, is_sqlite=is_sqlite, article_id=article_id, meta=meta)


async def sync_article_after_enrichment(
    conn,
    *,
    is_sqlite: bool,
    article_id: int,
    images: Any,
    meta: Dict[str, Any],
    videos: Any = None,
    audios: Any = None,
) -> None:
    await sync_article_images(conn, is_sqlite=is_sqlite, article_id=article_id, images=images, meta=meta)
    if videos:
        await sync_article_media(
            conn, is_sqlite=is_sqlite, article_id=article_id, media_items=videos, meta=meta, default_type="video"
        )
    if audios:
        await sync_article_media(
            conn, is_sqlite=is_sqlite, article_id=article_id, media_items=audios, meta=meta, default_type="audio"
        )
    await sync_article_keywords(conn, is_sqlite=is_sqlite, article_id=article_id, meta=meta)
    if meta:
        await sync_article_meta_norm(conn, is_sqlite=is_sqlite, article_id=article_id, meta=meta)


async def sync_article_after_analysis(
    conn,
    *,
    is_sqlite: bool,
    article_id: int,
    meta: Dict[str, Any],
    analysis_status: str,
    analysis_error: Optional[str],
    analyzed_at: Optional[str],
) -> None:
    await conn.execute(
        """
        UPDATE articles SET
            analysis_status = $2,
            analysis_error = $3,
            analyzed_at = COALESCE($4, analyzed_at)
        WHERE id = $1
        """,
        article_id,
        analysis_status,
        analysis_error,
        parse_dt(analyzed_at),
    )
    analysis = meta.get("analysis")
    if isinstance(analysis, dict):
        await sync_article_analyses(conn, is_sqlite=is_sqlite, article_id=article_id, analysis=analysis)
