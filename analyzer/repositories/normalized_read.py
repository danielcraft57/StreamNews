"""Lectures depuis tables normalisees (Phase 3) - source de verite relationnelle."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

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


def _iso(value: Any) -> Any:
    if value is not None and hasattr(value, "isoformat"):
        return value.isoformat()
    return value


async def load_article_images(conn, article_id: int) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT url, alt, source, is_primary, sort_order, media_type
        FROM article_media
        WHERE article_id = $1 AND media_type = 'image'
        ORDER BY sort_order ASC, id ASC
        """,
        article_id,
    )
    out = []
    for row in rows:
        out.append(
            {
                "url": row["url"],
                "alt": row["alt"] or "",
                "source": row["source"] or "legacy",
                "is_primary": bool(row["is_primary"]),
                "media_type": "image",
            }
        )
    return out


async def load_article_media(conn, article_id: int) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT media_type, url, mime_type, title, alt, source, thumbnail_url,
               duration_ms, width, height, is_primary, sort_order
        FROM article_media
        WHERE article_id = $1
        ORDER BY sort_order ASC, id ASC
        """,
        article_id,
    )
    return [dict(r) for r in rows]


async def load_article_keywords(conn, article_id: int) -> List[Dict[str, str]]:
    rows = await conn.fetch(
        """
        SELECT keyword, source FROM article_keywords
        WHERE article_id = $1
        ORDER BY id ASC
        """,
        article_id,
    )
    return [{"keyword": r["keyword"], "source": r["source"]} for r in rows]


async def load_article_analyses(conn, article_id: int) -> Dict[str, Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT tool_name, status, result, error_message, analyzed_at
        FROM article_analyses
        WHERE article_id = $1
        """,
        article_id,
    )
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        block = _parse_json(row["result"], {})
        if not isinstance(block, dict):
            block = {}
        block = dict(block)
        block["status"] = row["status"]
        if row["error_message"]:
            block["error"] = row["error_message"]
        if row["analyzed_at"]:
            block["analyzed_at"] = _iso(row["analyzed_at"])
        out[row["tool_name"]] = block
    return out


async def load_article_meta_norm(conn, article_id: int) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        "SELECT * FROM article_meta_norm WHERE article_id = $1",
        article_id,
    )
    if not row:
        return None
    return dict(row)


def rebuild_article_meta(
    *,
    meta_norm: Optional[Dict[str, Any]],
    keywords: List[Dict[str, str]],
    analyses: Dict[str, Dict[str, Any]],
    analysis_status: Optional[str],
    analysis_error: Optional[str],
    analyzed_at: Any,
    legacy_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Reconstruit article_meta pour l'API a partir des tables (pas le blob)."""
    meta: Dict[str, Any] = {}
    legacy = legacy_meta if isinstance(legacy_meta, dict) else {}

    if meta_norm:
        if meta_norm.get("canonical_url"):
            meta["canonical_url"] = meta_norm["canonical_url"]
        if meta_norm.get("date_published"):
            meta["date_published"] = _iso(meta_norm["date_published"])
        if meta_norm.get("schema_type"):
            meta["schema_type"] = meta_norm["schema_type"]
        if meta_norm.get("reading_time_minutes") is not None:
            meta["reading_time_minutes"] = meta_norm["reading_time_minutes"]
        if meta_norm.get("primary_image_url"):
            meta["primary_image"] = meta_norm["primary_image_url"]
        if meta_norm.get("domain"):
            meta["domain"] = meta_norm["domain"]
        extra = _parse_json(meta_norm.get("extra"), {})
        if isinstance(extra, dict):
            meta.update(extra)
    else:
        # Fallback legacy uniquement si pas encore backfille
        for key in (
            "canonical_url",
            "canonical",
            "page_url",
            "date_published",
            "schema_type",
            "reading_time_minutes",
            "primary_image",
            "domain",
            "sources",
            "og_image",
            "favicon",
        ):
            if key in legacy and legacy[key] is not None:
                meta[key] = legacy[key]

    if keywords:
        meta["keywords"] = [k["keyword"] for k in keywords]
        meta["keywords_detail"] = keywords
    elif isinstance(legacy.get("keywords"), list):
        meta["keywords"] = legacy["keywords"]

    if analyses:
        meta["analysis"] = analyses
    elif isinstance(legacy.get("analysis"), dict):
        meta["analysis"] = legacy["analysis"]

    status = analysis_status or legacy.get("analysis_status")
    if status:
        meta["analysis_status"] = status
    err = analysis_error if analysis_error is not None else legacy.get("analysis_error")
    if err:
        meta["analysis_error"] = err
    at = _iso(analyzed_at) or legacy.get("analyzed_at")
    if at:
        meta["analyzed_at"] = at

    return meta


async def hydrate_article(conn, article: Dict[str, Any], *, is_sqlite: bool) -> Dict[str, Any]:
    """Remplace images / article_meta JSON par les tables normalisees si dispo."""
    if not await has_normalized_tables(conn, is_sqlite=is_sqlite):
        return article

    article_id = int(article["id"])
    images = await load_article_images(conn, article_id)
    keywords = await load_article_keywords(conn, article_id)
    analyses = await load_article_analyses(conn, article_id)
    meta_norm = await load_article_meta_norm(conn, article_id)
    legacy_meta = article.get("article_meta")
    if not isinstance(legacy_meta, dict):
        legacy_meta = _parse_json(legacy_meta, {})

    if images:
        article["images"] = images
    elif not isinstance(article.get("images"), list):
        article["images"] = []

    article["article_meta"] = rebuild_article_meta(
        meta_norm=meta_norm,
        keywords=keywords,
        analyses=analyses,
        analysis_status=article.get("analysis_status"),
        analysis_error=article.get("analysis_error"),
        analyzed_at=article.get("analyzed_at"),
        legacy_meta=legacy_meta if isinstance(legacy_meta, dict) else {},
    )
    return article


async def load_site_rss_feeds(conn, site_id: int) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT url, title, feed_type, source_page_id
        FROM rss_feeds
        WHERE site_id = $1
        ORDER BY id ASC
        """,
        site_id,
    )
    return [
        {
            "url": r["url"],
            "title": r["title"] or "Flux RSS",
            "type": r["feed_type"] or "detected",
            "source_page_id": r["source_page_id"],
        }
        for r in rows
    ]


async def hydrate_articles_batch(
    conn,
    articles: List[Dict[str, Any]],
    *,
    is_sqlite: bool,
    with_analyses: bool = False,
) -> List[Dict[str, Any]]:
    """Hydrate une liste d'articles (1 requete par table, pas N+1)."""
    if not articles:
        return articles
    if not await has_normalized_tables(conn, is_sqlite=is_sqlite):
        return articles

    ids = [int(a["id"]) for a in articles]
    placeholders = ", ".join(f"${i + 1}" for i in range(len(ids)))

    img_rows = await conn.fetch(
        f"""
        SELECT article_id, url, alt, source, is_primary, sort_order, media_type
        FROM article_media
        WHERE article_id IN ({placeholders})
        ORDER BY sort_order ASC, id ASC
        """,
        *ids,
    )
    images_by: Dict[int, List[Dict[str, Any]]] = {}
    media_by: Dict[int, List[Dict[str, Any]]] = {}
    for row in img_rows:
        aid = int(row["article_id"])
        item = {
            "url": row["url"],
            "alt": row["alt"] or "",
            "source": row["source"] or "legacy",
            "is_primary": bool(row["is_primary"]),
            "media_type": row.get("media_type") or "image",
        }
        media_by.setdefault(aid, []).append(item)
        if item["media_type"] == "image":
            images_by.setdefault(aid, []).append(item)

    kw_rows = await conn.fetch(
        f"""
        SELECT article_id, keyword, source FROM article_keywords
        WHERE article_id IN ({placeholders})
        ORDER BY id ASC
        """,
        *ids,
    )
    kw_by: Dict[int, List[Dict[str, str]]] = {}
    for row in kw_rows:
        aid = int(row["article_id"])
        kw_by.setdefault(aid, []).append(
            {"keyword": row["keyword"], "source": row["source"]}
        )

    norm_rows = await conn.fetch(
        f"SELECT * FROM article_meta_norm WHERE article_id IN ({placeholders})",
        *ids,
    )
    norm_by = {int(r["article_id"]): dict(r) for r in norm_rows}

    analyses_by: Dict[int, Dict[str, Dict[str, Any]]] = {}
    if with_analyses:
        an_rows = await conn.fetch(
            f"""
            SELECT article_id, tool_name, status, result, error_message, analyzed_at
            FROM article_analyses
            WHERE article_id IN ({placeholders})
            """,
            *ids,
        )
        for row in an_rows:
            aid = int(row["article_id"])
            block = _parse_json(row["result"], {})
            if not isinstance(block, dict):
                block = {}
            block = dict(block)
            block["status"] = row["status"]
            if row["error_message"]:
                block["error"] = row["error_message"]
            if row["analyzed_at"]:
                block["analyzed_at"] = _iso(row["analyzed_at"])
            analyses_by.setdefault(aid, {})[row["tool_name"]] = block

    for article in articles:
        aid = int(article["id"])
        legacy_meta = article.get("article_meta")
        if not isinstance(legacy_meta, dict):
            legacy_meta = _parse_json(legacy_meta, {})

        imgs = images_by.get(aid)
        if imgs:
            article["images"] = imgs
        elif not isinstance(article.get("images"), list):
            article["images"] = []
        article["media"] = media_by.get(aid, article.get("images") or [])
        article["videos"] = [m for m in article["media"] if m.get("media_type") == "video"]
        article["audios"] = [m for m in article["media"] if m.get("media_type") == "audio"]

        article["article_meta"] = rebuild_article_meta(
            meta_norm=norm_by.get(aid),
            keywords=kw_by.get(aid, []),
            analyses=analyses_by.get(aid, {}),
            analysis_status=article.get("analysis_status"),
            analysis_error=article.get("analysis_error"),
            analyzed_at=article.get("analyzed_at"),
            legacy_meta=legacy_meta if isinstance(legacy_meta, dict) else {},
        )
    return articles


async def load_page_rss_feeds(conn, page_id: int) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT url, title, feed_type
        FROM rss_feeds
        WHERE source_page_id = $1
        ORDER BY id ASC
        """,
        page_id,
    )
    return [
        {
            "url": r["url"],
            "title": r["title"] or "Flux RSS",
            "type": r["feed_type"] or "detected",
        }
        for r in rows
    ]


async def hydrate_pages_batch(
    conn, pages: List[Dict[str, Any]], *, is_sqlite: bool
) -> List[Dict[str, Any]]:
    if not pages:
        return pages
    if not await has_normalized_tables(conn, is_sqlite=is_sqlite):
        return pages
    ids = [int(p["id"]) for p in pages]
    placeholders = ", ".join(f"${i + 1}" for i in range(len(ids)))
    rows = await conn.fetch(
        f"""
        SELECT source_page_id, url, title, feed_type
        FROM rss_feeds
        WHERE source_page_id IN ({placeholders})
        ORDER BY id ASC
        """,
        *ids,
    )
    by_page: Dict[int, List[Dict[str, Any]]] = {}
    for row in rows:
        pid = int(row["source_page_id"])
        by_page.setdefault(pid, []).append(
            {
                "url": row["url"],
                "title": row["title"] or "Flux RSS",
                "type": row["feed_type"] or "detected",
            }
        )
    for page in pages:
        page["rss_feeds"] = by_page.get(int(page["id"]), [])
    return pages


async def hydrate_site(conn, site: Dict[str, Any], *, is_sqlite: bool) -> Dict[str, Any]:
    if not await has_normalized_tables(conn, is_sqlite=is_sqlite):
        return site
    feeds = await load_site_rss_feeds(conn, int(site["id"]))
    if feeds:
        site["rss_feeds"] = feeds
    return site
