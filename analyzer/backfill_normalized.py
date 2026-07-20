"""Backfill idempotent : JSON legacy -> tables normalisees (Phase 1)."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from database import Database


def _parse_dt(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _keyword_rows(meta: Dict[str, Any], article_id: int) -> List[Tuple[int, str, str]]:
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


def _image_rows(images: Any, article_id: int, meta: Dict[str, Any]) -> List[Tuple]:
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


def _meta_norm_row(article_id: int, meta: Dict[str, Any]) -> Tuple:
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
        _parse_dt(meta.get("date_published")),
        (str(meta.get("schema_type"))[:100] if meta.get("schema_type") else None),
        meta.get("reading_time_minutes") if isinstance(meta.get("reading_time_minutes"), int) else None,
        (str(meta.get("primary_image"))[:2000] if meta.get("primary_image") else None),
        (str(meta.get("domain"))[:255] if meta.get("domain") else None),
        json.dumps(extra) if extra else "{}",
    )


async def _ensure_rss_feed(
    conn,
    *,
    site_id: int,
    url: str,
    title: str,
    feed_type: str,
    source_page_id: Optional[int],
    is_sqlite: bool,
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


async def backfill_normalized(db: Database) -> Dict[str, int]:
    """Remplit les tables normalisees depuis le JSON existant (idempotent)."""
    stats = {
        "rss_feeds": 0,
        "article_images": 0,
        "article_keywords": 0,
        "article_analyses": 0,
        "article_meta_norm": 0,
        "articles_updated": 0,
    }
    is_sqlite = db.is_sqlite
    feed_id_cache: Dict[Tuple[int, str], int] = {}

    async with db.pool.acquire() as conn:
        if is_sqlite:
            probe = await conn.fetchrow(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='rss_feeds'"
            )
        else:
            probe = await conn.fetchrow(
                "SELECT to_regclass('rss_feeds') IS NOT NULL AS name FROM (SELECT 1) t"
            )
        if not probe:
            return stats

        sites = await conn.fetch("SELECT id, rss_feeds FROM sites")
        for site in sites:
            feeds = db._parse_json_field(site["rss_feeds"])
            if not isinstance(feeds, list):
                continue
            for f in feeds:
                if not isinstance(f, dict) or not f.get("url"):
                    continue
                fid = await _ensure_rss_feed(
                    conn,
                    site_id=int(site["id"]),
                    url=f.get("url", ""),
                    title=f.get("title", "Flux RSS"),
                    feed_type=f.get("type", "detected"),
                    source_page_id=None,
                    is_sqlite=is_sqlite,
                )
                if fid:
                    feed_id_cache[(int(site["id"]), f["url"].strip())] = fid
                    stats["rss_feeds"] += 1

        pages = await conn.fetch("SELECT id, site_id, rss_feeds FROM pages")
        for page in pages:
            feeds = db._parse_json_field(page["rss_feeds"])
            if not isinstance(feeds, list):
                continue
            for f in feeds:
                if not isinstance(f, dict) or not f.get("url"):
                    continue
                fid = await _ensure_rss_feed(
                    conn,
                    site_id=int(page["site_id"]),
                    url=f.get("url", ""),
                    title=f.get("title", "Flux RSS"),
                    feed_type=f.get("type", "detected"),
                    source_page_id=int(page["id"]),
                    is_sqlite=is_sqlite,
                )
                if fid:
                    feed_id_cache[(int(page["site_id"]), f["url"].strip())] = fid
                    stats["rss_feeds"] += 1

        articles = await conn.fetch(
            """
            SELECT id, site_id, feed_url, images, article_meta,
                   analysis_status, analysis_error, analyzed_at
            FROM articles
            """
        )
        for art in articles:
            article_id = int(art["id"])
            site_id = int(art["site_id"])
            meta_raw = db._parse_json_field(art["article_meta"])
            meta = meta_raw if isinstance(meta_raw, dict) else {}
            images_raw = db._parse_json_field(art["images"])
            images = images_raw if isinstance(images_raw, list) else []

            feed_url = (art["feed_url"] or "").strip()
            feed_id = feed_id_cache.get((site_id, feed_url))
            if feed_id is None and feed_url:
                feed_id = await _ensure_rss_feed(
                    conn,
                    site_id=site_id,
                    url=feed_url,
                    title="Flux RSS",
                    feed_type="ingest",
                    source_page_id=None,
                    is_sqlite=is_sqlite,
                )
                if feed_id:
                    feed_id_cache[(site_id, feed_url)] = feed_id
                    stats["rss_feeds"] += 1

            analysis_status = art["analysis_status"] or meta.get("analysis_status")
            analysis_error = art["analysis_error"] or meta.get("analysis_error")
            analyzed_at = art["analyzed_at"] or meta.get("analyzed_at")

            if feed_id or analysis_status or analysis_error or analyzed_at:
                await conn.execute(
                    """
                    UPDATE articles SET
                        feed_id = COALESCE($2, feed_id),
                        analysis_status = COALESCE($3, analysis_status),
                        analysis_error = COALESCE($4, analysis_error),
                        analyzed_at = COALESCE($5, analyzed_at)
                    WHERE id = $1
                    """,
                    article_id,
                    feed_id,
                    analysis_status,
                    analysis_error,
                    _parse_dt(analyzed_at),
                )
                stats["articles_updated"] += 1

            for row in _image_rows(images, article_id, meta):
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
                stats["article_images"] += 1

            for row in _keyword_rows(meta, article_id):
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
                stats["article_keywords"] += 1

            analysis = meta.get("analysis")
            if isinstance(analysis, dict):
                for tool_name, block in analysis.items():
                    if not isinstance(block, dict):
                        continue
                    tool = str(tool_name)[:100]
                    status = str(block.get("status") or "unknown")[:50]
                    result = {k: v for k, v in block.items() if k != "status"}
                    err = block.get("error") or block.get("message")
                    analyzed_tool = _parse_dt(block.get("analyzed_at"))
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
                    stats["article_analyses"] += 1

            norm = _meta_norm_row(article_id, meta)
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
            stats["article_meta_norm"] += 1

    return stats
