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


def image_rows(images: Any, article_id: int, meta: Dict[str, Any]) -> List[Tuple]:
    if not isinstance(images, list):
        images = []
    primary_url = meta.get("primary_image")
    rows = []
    for idx, img in enumerate(images):
        if isinstance(img, str):
            url, alt, source = img, "", "legacy"
        elif isinstance(img, dict):
            url = img.get("url")
            alt = img.get("alt") or ""
            source = img.get("source") or "legacy"
        else:
            continue
        if not url or not str(url).strip():
            continue
        url = str(url).strip()[:2000]
        is_primary = bool(primary_url and str(primary_url).strip() == url) or idx == 0
        rows.append((article_id, url, str(alt)[:500] or None, str(source)[:50] or None, is_primary, idx))
    if rows and not any(r[4] for r in rows):
        rows[0] = (rows[0][0], rows[0][1], rows[0][2], rows[0][3], True, rows[0][5])
    return rows


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


async def sync_article_images(
    conn,
    *,
    is_sqlite: bool,
    article_id: int,
    images: Any,
    meta: Dict[str, Any],
) -> None:
    for row in image_rows(images, article_id, meta):
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


async def sync_article_after_upsert(
    conn,
    *,
    is_sqlite: bool,
    site_id: int,
    article_id: int,
    feed_url: str,
    images: Any,
    meta: Dict[str, Any],
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
) -> None:
    await sync_article_images(conn, is_sqlite=is_sqlite, article_id=article_id, images=images, meta=meta)
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
