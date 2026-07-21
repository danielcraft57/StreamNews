"""Backfill idempotent : JSON legacy -> tables normalisees (Phase 1).

Apres Phase 4 (drop colonnes JSON), cette fonction est un no-op si les
colonnes n'existent plus.
"""
from __future__ import annotations

from typing import Dict, Tuple

from database import Database
from repositories.normalized_sync import (
    ensure_rss_feed,
    has_normalized_tables,
    image_rows,
    keyword_rows,
    parse_dt,
    sync_article_analyses,
    sync_article_images,
    sync_article_keywords,
    sync_article_meta_norm,
)


async def _table_columns(conn, table: str, *, is_sqlite: bool) -> set[str]:
    if is_sqlite:
        rows = await conn.fetch(f"PRAGMA table_info({table})")
        return {r["name"] for r in rows}
    rows = await conn.fetch(
        """
        SELECT column_name AS name
        FROM information_schema.columns
        WHERE table_name = $1 AND table_schema = 'public'
        """,
        table,
    )
    return {r["name"] for r in rows}


async def backfill_normalized(db: Database) -> Dict[str, int]:
    """Remplit les tables normalisees depuis le JSON existant (idempotent)."""
    stats = {
        "rss_feeds": 0,
        "article_images": 0,
        "article_keywords": 0,
        "article_analyses": 0,
        "article_meta_norm": 0,
        "articles_updated": 0,
        "skipped_no_legacy": 0,
    }
    is_sqlite = db.is_sqlite

    async with db.pool.acquire() as conn:
        if not await has_normalized_tables(conn, is_sqlite=is_sqlite):
            return stats

        site_cols = await _table_columns(conn, "sites", is_sqlite=is_sqlite)
        article_cols = await _table_columns(conn, "articles", is_sqlite=is_sqlite)
        page_cols = await _table_columns(conn, "pages", is_sqlite=is_sqlite)

        # Phase 4 : plus de JSON legacy a migrer
        if "rss_feeds" not in site_cols and "images" not in article_cols:
            stats["skipped_no_legacy"] = 1
            return stats

        feed_id_cache: Dict[Tuple[int, str], int] = {}

        if "rss_feeds" in site_cols:
            sites = await conn.fetch("SELECT id, rss_feeds FROM sites")
            for site in sites:
                feeds = db._parse_json_field(site["rss_feeds"])
                if not isinstance(feeds, list):
                    continue
                for f in feeds:
                    if not isinstance(f, dict) or not f.get("url"):
                        continue
                    fid = await ensure_rss_feed(
                        conn,
                        is_sqlite=is_sqlite,
                        site_id=int(site["id"]),
                        url=f.get("url", ""),
                        title=f.get("title", "Flux RSS"),
                        feed_type=f.get("type", "detected"),
                    )
                    if fid:
                        feed_id_cache[(int(site["id"]), f["url"].strip())] = fid
                        stats["rss_feeds"] += 1

        if "rss_feeds" in page_cols:
            pages = await conn.fetch("SELECT id, site_id, rss_feeds FROM pages")
            for page in pages:
                feeds = db._parse_json_field(page["rss_feeds"])
                if not isinstance(feeds, list):
                    continue
                for f in feeds:
                    if not isinstance(f, dict) or not f.get("url"):
                        continue
                    fid = await ensure_rss_feed(
                        conn,
                        is_sqlite=is_sqlite,
                        site_id=int(page["site_id"]),
                        url=f.get("url", ""),
                        title=f.get("title", "Flux RSS"),
                        feed_type=f.get("type", "detected"),
                        source_page_id=int(page["id"]),
                    )
                    if fid:
                        feed_id_cache[(int(page["site_id"]), f["url"].strip())] = fid
                        stats["rss_feeds"] += 1

        if "images" not in article_cols and "article_meta" not in article_cols:
            return stats

        select_cols = ["id", "site_id", "feed_url"]
        if "images" in article_cols:
            select_cols.append("images")
        if "article_meta" in article_cols:
            select_cols.append("article_meta")
        for c in ("analysis_status", "analysis_error", "analyzed_at"):
            if c in article_cols:
                select_cols.append(c)

        articles = await conn.fetch(
            f"SELECT {', '.join(select_cols)} FROM articles"
        )
        for art in articles:
            article_id = int(art["id"])
            site_id = int(art["site_id"])
            meta_raw = (
                db._parse_json_field(art["article_meta"])
                if "article_meta" in art
                else {}
            )
            meta = meta_raw if isinstance(meta_raw, dict) else {}
            images_raw = db._parse_json_field(art["images"]) if "images" in art else []
            images = images_raw if isinstance(images_raw, list) else []

            feed_url = (art["feed_url"] or "").strip()
            feed_id = feed_id_cache.get((site_id, feed_url))
            if feed_id is None and feed_url:
                feed_id = await ensure_rss_feed(
                    conn,
                    is_sqlite=is_sqlite,
                    site_id=site_id,
                    url=feed_url,
                    title="Flux RSS",
                    feed_type="ingest",
                )
                if feed_id:
                    feed_id_cache[(site_id, feed_url)] = feed_id
                    stats["rss_feeds"] += 1

            analysis_status = art.get("analysis_status") or meta.get("analysis_status")
            analysis_error = art.get("analysis_error") or meta.get("analysis_error")
            analyzed_at = art.get("analyzed_at") or meta.get("analyzed_at")

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
                    parse_dt(analyzed_at),
                )
                stats["articles_updated"] += 1

            await sync_article_images(
                conn, is_sqlite=is_sqlite, article_id=article_id, images=images, meta=meta
            )
            stats["article_images"] += len(image_rows(images, article_id, meta))

            await sync_article_keywords(conn, is_sqlite=is_sqlite, article_id=article_id, meta=meta)
            stats["article_keywords"] += len(keyword_rows(meta, article_id))

            analysis = meta.get("analysis")
            if isinstance(analysis, dict):
                await sync_article_analyses(
                    conn, is_sqlite=is_sqlite, article_id=article_id, analysis=analysis
                )
                stats["article_analyses"] += len(analysis)

            await sync_article_meta_norm(conn, is_sqlite=is_sqlite, article_id=article_id, meta=meta)
            stats["article_meta_norm"] += 1

    return stats
