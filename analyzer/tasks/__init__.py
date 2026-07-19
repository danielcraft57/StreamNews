"""
Pipeline d'analyse (pattern Pipeline + Fan-out/Fan-in) :

  crawl_site  --(feeds)-->  group(ingest_feed x N)  --chord-->  finalize_analysis

Les workers Pi peuvent consommer `crawl` et/ou `ingest` en parallele.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Dict, List, Optional

import requests
from celery import chord, group

from celery_app import celery_app
from database import Database
from models import PipelineSummary
from services.crawl_service import CrawlService
from services.ingest_service import IngestService

logger = logging.getLogger(__name__)


def _send_ws(message: dict) -> None:
    try:
        web_url = os.getenv("WEB_URL", "http://localhost:3000")
        requests.post(f"{web_url}/api/websocket", json=message, timeout=5)
    except Exception as exc:
        logger.warning("WS push failed: %s", exc)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _crawl_and_persist(site_id: int, url: str, max_pages: int, depth: int) -> dict:
    db = Database()
    await db.init_db()
    await db.update_site_status(site_id, "analyzing")

    async def on_page(page_url, title, feeds):
        await db.add_page_analysis(site_id, page_url, title, feeds)
        _send_ws(
            {
                "type": "page_analyzed",
                "site_id": site_id,
                "url": page_url,
                "title": title,
                "pages_analyzed": None,
            }
        )

    async def on_feed(feed: dict):
        _send_ws(
            {
                "type": "rss_found",
                "site_id": site_id,
                "rss_url": feed.get("url"),
                "title": feed.get("title"),
                "source_page": feed.get("source_page"),
            }
        )

    service = CrawlService(on_page=on_page, on_feed=on_feed)
    result = await service.run(url, max_pages=max_pages, depth=depth)
    feeds = [f.model_dump() for f in result.rss_feeds]
    await db.update_site_status(
        site_id, result.status, feeds, result.total_pages_analyzed
    )
    return {
        "status": result.status,
        "rss_feeds": feeds,
        "total_pages_analyzed": result.total_pages_analyzed,
        "error": result.error,
    }


@celery_app.task(bind=True, name="streamnews.crawl_site")
def crawl_site_task(self, site_id: int, url: str, max_pages: int = 50, depth: int = 3):
    """Etape 1 : crawl + detection feeds, puis fan-out ingest."""
    _send_ws(
        {
            "type": "analysis_started",
            "site_id": site_id,
            "url": url,
            "max_pages": max_pages,
            "total_pages": max_pages,
        }
    )

    try:
        crawl = _run(_crawl_and_persist(site_id, url, max_pages, depth))
    except Exception as exc:
        logger.exception("crawl failed site_id=%s", site_id)
        try:
            _run(_mark_error(site_id))
        except Exception:
            pass
        _send_ws({"type": "analysis_error", "site_id": site_id, "url": url, "error": str(exc)})
        return {"site_id": site_id, "status": "error", "error": str(exc)}

    feeds = crawl.get("rss_feeds") or []
    unique_urls = []
    seen = set()
    for f in feeds:
        u = (f.get("url") or "").strip()
        if u and u not in seen:
            seen.add(u)
            unique_urls.append(u)

    _send_ws(
        {
            "type": "articles_ingest_started",
            "site_id": site_id,
            "feeds_count": len(unique_urls),
        }
    )

    if not unique_urls:
        return finalize_analysis_task(
            [],
            site_id,
            url,
            crawl.get("status", "completed"),
            crawl.get("total_pages_analyzed", 0),
            len(feeds),
        )

    header = group(ingest_feed_task.s(site_id, feed_url) for feed_url in unique_urls)
    callback = finalize_analysis_task.s(
        site_id,
        url,
        crawl.get("status", "completed"),
        crawl.get("total_pages_analyzed", 0),
        len(feeds),
    )
    chord(header)(callback)
    return {
        "site_id": site_id,
        "status": "ingest_scheduled",
        "feeds": len(unique_urls),
    }


async def _mark_error(site_id: int):
    db = Database()
    await db.init_db()
    await db.update_site_status(site_id, "error")


@celery_app.task(name="streamnews.ingest_feed")
def ingest_feed_task(site_id: int, feed_url: str) -> int:
    """Etape 2 (parallelisable) : parse un flux et upsert articles."""
    service = IngestService()
    articles = service.parse_feed(feed_url)

    async def _persist():
        db = Database()
        await db.init_db()
        n = 0
        for art in articles:
            await db.upsert_article(
                site_id=site_id,
                feed_url=art.feed_url,
                title=art.title,
                link=art.link,
                summary=art.summary,
                author=art.author,
                published_at=art.published_at,
                guid=art.guid,
            )
            n += 1
        return n

    try:
        count = _run(_persist())
        logger.info("ingest feed %s -> %s articles", feed_url, count)
        return count
    except Exception as exc:
        logger.warning("ingest_feed failed %s: %s", feed_url, exc)
        return 0


@celery_app.task(name="streamnews.finalize_analysis")
def finalize_analysis_task(
    ingest_counts: Optional[List[int]],
    site_id: int,
    url: str,
    status: str,
    pages_analyzed: int,
    rss_count: int,
):
    """Etape 3 (fan-in) : notifie l'UI."""
    articles_count = sum(ingest_counts or [])
    summary = PipelineSummary(
        site_id=site_id,
        url=url,
        status=status,
        rss_count=rss_count,
        articles_count=articles_count,
        pages_analyzed=pages_analyzed,
    )
    _send_ws(
        {
            "type": "analysis_completed",
            "site_id": site_id,
            "url": url,
            "rss_count": rss_count,
            "articles_count": articles_count,
            "total_pages": pages_analyzed,
            "status": status,
        }
    )
    return summary.model_dump()


# --- Compat API existante ---

@celery_app.task(bind=True, name="celery_worker.analyze_site_task")
def analyze_site_task(self, site_id: int, url: str, max_pages: int = 50, depth: int = 3):
    """Alias conserve pour main.py / anciennes taches en queue."""
    return crawl_site_task(site_id, url, max_pages, depth)


@celery_app.task(name="celery_worker.cleanup_old_analyses")
def cleanup_old_analyses(days: int = 30):
    db = Database()

    async def _clean():
        await db.init_db()
        return await db.cleanup_old_analyses(days)

    try:
        deleted = _run(_clean())
        return {"status": "success", "deleted_sites": deleted, "days": days}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
