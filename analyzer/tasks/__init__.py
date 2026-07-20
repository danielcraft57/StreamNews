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
from logging_config import get_logger, setup_logging
from models import PipelineSummary
from services.crawl_service import CrawlService
from services.enrich_service import enrich_article_url
from services.ingest_service import IngestService

# Worker : s'assurer que logs/worker.log est configure
if not logging.getLogger().handlers:
    setup_logging(service=os.getenv("STREAMNEWS_SERVICE", "worker"))

logger = get_logger(__name__)


def _send_ws(message: dict) -> None:
    try:
        web_url = os.getenv("WEB_URL", "http://localhost:3000")
        requests.post(f"{web_url}/api/websocket", json=message, timeout=5)
        logger.debug("WS push type=%s site_id=%s", message.get("type"), message.get("site_id"))
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

    pages_done = 0
    # total provisoire = plafond ; remplace apres discovery par le vrai plan
    planned_total = {"n": max(1, max_pages)}

    async def on_page(page_url, title, feeds):
        nonlocal pages_done
        pages_done += 1
        await db.add_page_analysis(site_id, page_url, title, feeds)
        _send_ws(
            {
                "type": "page_analyzed",
                "site_id": site_id,
                "url": page_url,
                "title": title,
                "pages_analyzed": pages_done,
                "total_pages": planned_total["n"],
            }
        )
        logger.debug("page_analyzed site_id=%s n=%s/%s url=%s", site_id, pages_done, planned_total["n"], page_url)

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
        logger.info("rss_found site_id=%s url=%s", site_id, feed.get("url"))

    async def on_plan(total: int):
        planned_total["n"] = max(1, int(total))
        _send_ws(
            {
                "type": "progress_update",
                "site_id": site_id,
                "current": pages_done,
                "total": planned_total["n"],
                "message": f"Plan: {planned_total['n']} page(s) a analyser",
            }
        )
        logger.info("Crawl plan site_id=%s total=%s", site_id, planned_total["n"])

    async def should_cancel() -> bool:
        return await db.is_cancel_requested(site_id)

    service = CrawlService(on_page=on_page, on_feed=on_feed, on_plan=on_plan)
    logger.info("Crawl start site_id=%s url=%s max_pages=%s depth=%s", site_id, url, max_pages, depth)
    _send_ws(
        {
            "type": "progress_update",
            "site_id": site_id,
            "current": 0,
            "total": None,
            "message": "Discovery des liens...",
        }
    )
    result = await service.run(
        url, max_pages=max_pages, depth=depth, should_cancel=should_cancel
    )
    logger.info(
        "Crawl end site_id=%s status=%s pages=%s feeds=%s",
        site_id,
        result.status,
        result.total_pages_analyzed,
        len(result.rss_feeds),
    )
    if result.site_meta:
        await db.update_site_meta(site_id, result.site_meta)
        _send_ws(
            {
                "type": "site_meta",
                "site_id": site_id,
                "title": result.site_meta.get("title"),
                "favicon_url": result.site_meta.get("favicon_url"),
                "description": result.site_meta.get("description"),
            }
        )
    feeds = [f.model_dump() for f in result.rss_feeds]
    # Fusionne RSS/Atom (et http/https) qui portent les memes articles
    from utils import collapse_equivalent_feeds

    feeds = collapse_equivalent_feeds(feeds)
    status = result.status
    if await should_cancel():
        status = "cancelled"
    # merge_feeds=True : ajoute aux feeds deja en base (relance meme domaine)
    await db.update_site_status(
        site_id, status, feeds, result.total_pages_analyzed, merge_feeds=True
    )
    # Pour l'ingest : recharger la liste fusionnee
    site = await db.get_site(site_id)
    merged = (site or {}).get("rss_feeds") or feeds
    return {
        "status": status,
        "rss_feeds": merged,
        "total_pages_analyzed": result.total_pages_analyzed,
        "error": result.error,
    }


@celery_app.task(bind=True, name="streamnews.crawl_site")
def crawl_site_task(self, site_id: int, url: str, max_pages: int = 50, depth: int = 3):
    """Etape 1 : crawl + detection feeds, puis fan-out ingest."""
    logger.info(
        "crawl_site start site_id=%s url=%s max_pages=%s depth=%s task=%s",
        site_id,
        url,
        max_pages,
        depth,
        getattr(self.request, "id", None),
    )
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

    if crawl.get("status") == "cancelled":
        _send_ws(
            {
                "type": "analysis_cancelled",
                "site_id": site_id,
                "url": url,
                "total_pages": crawl.get("total_pages_analyzed", 0),
            }
        )
        return {"site_id": site_id, "status": "cancelled"}

    if crawl.get("status") == "error":
        err = crawl.get("error") or "Erreur pendant le crawl"
        logger.error("crawl status=error site_id=%s err=%s", site_id, err)
        _send_ws({"type": "analysis_error", "site_id": site_id, "url": url, "error": err})
        # On tente quand meme un ingest des feeds trouves sur la home si presents
        feeds = crawl.get("rss_feeds") or []
        from utils import collapse_equivalent_feeds
        feeds = collapse_equivalent_feeds(feeds)
        if feeds:
            # persiste les feeds trouves
            async def _save():
                db = Database()
                await db.init_db()
                await db.update_site_status(
                    site_id, "error", feeds, crawl.get("total_pages_analyzed", 0)
                )
            try:
                _run(_save())
            except Exception:
                pass
        return {"site_id": site_id, "status": "error", "error": err}

    feeds = crawl.get("rss_feeds") or []
    from utils import collapse_equivalent_feeds

    # Securite : re-collapse au cas ou la liste vient d'un ancien crawl
    feeds = collapse_equivalent_feeds(feeds)
    unique_urls = [f["url"] for f in feeds if f.get("url")]
    logger.info(
        "crawl_site done site_id=%s status=%s pages=%s feeds=%s",
        site_id,
        crawl.get("status"),
        crawl.get("total_pages_analyzed"),
        len(unique_urls),
    )

    _send_ws(
        {
            "type": "progress_update",
            "site_id": site_id,
            "current": crawl.get("total_pages_analyzed", 0),
            "total": crawl.get("total_pages_analyzed", 0),
            "message": f"Crawl terminé ({crawl.get('total_pages_analyzed', 0)} pages) — import de {len(unique_urls)} flux...",
        }
    )

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


@celery_app.task(name="streamnews.enrich_article")
def enrich_article_task(article_id: int, force: bool = False) -> dict:
    """Fetch la page article et stocke contenu + meta + images."""

    async def _run_enrich():
        db = Database()
        await db.init_db()
        article = await db.get_article(article_id)
        if not article:
            return {"article_id": article_id, "status": "missing"}
        if article.get("enrich_status") == "ok" and not force:
            return {
                "article_id": article_id,
                "status": "ok",
                "skipped": True,
                "site_id": article.get("site_id"),
            }

        await db.set_article_enrich_pending(article_id)
        link = article.get("link") or ""
        try:
            data = await enrich_article_url(link)
            # Ne remplace le titre RSS que si on a quelque chose de plus riche
            new_title = data.get("title")
            if new_title and article.get("title") and new_title == article.get("title"):
                new_title = None
            await db.update_article_enrichment(
                article_id,
                content_html=data.get("content_html") or "",
                content_text=data.get("content_text") or "",
                images=data.get("images") or [],
                article_meta=data.get("article_meta") or {},
                enrich_status="ok",
                enrich_error=None,
                title=new_title,
                author=data.get("author"),
            )
            _send_ws(
                {
                    "type": "article_enriched",
                    "article_id": article_id,
                    "site_id": article.get("site_id"),
                    "status": "ok",
                    "title": data.get("title") or article.get("title"),
                    "images_count": len(data.get("images") or []),
                }
            )
            return {
                "article_id": article_id,
                "status": "ok",
                "site_id": article.get("site_id"),
            }
        except Exception as exc:
            logger.warning("enrich_article failed id=%s: %s", article_id, exc)
            await db.update_article_enrichment(
                article_id,
                enrich_status="error",
                enrich_error=str(exc)[:1000],
            )
            _send_ws(
                {
                    "type": "article_enriched",
                    "article_id": article_id,
                    "site_id": article.get("site_id"),
                    "status": "error",
                    "error": str(exc)[:300],
                }
            )
            return {
                "article_id": article_id,
                "status": "error",
                "error": str(exc),
                "site_id": article.get("site_id"),
            }

    return _run(_run_enrich())


@celery_app.task(name="streamnews.enrich_site_articles")
def enrich_site_articles_task(site_id: int, limit: int = 50) -> dict:
    """Enqueue l'enrichissement des articles d'un site (sans contenu ok)."""

    async def _list():
        db = Database()
        await db.init_db()
        return await db.list_articles_needing_enrichment(site_id, limit=limit)

    articles = _run(_list())
    queued = 0
    for art in articles:
        enrich_article_task.delay(art["id"], False)
        queued += 1
    logger.info("enrich_site_articles site_id=%s queued=%s", site_id, queued)
    return {"site_id": site_id, "queued": queued}


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
