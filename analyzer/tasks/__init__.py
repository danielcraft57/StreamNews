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
from services.text_analysis_service import analyze_article_content

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


def _article_media_list(article: dict) -> List[dict]:
    media = article.get("media") or []
    if media:
        return [m for m in media if isinstance(m, dict)]
    out: List[dict] = []
    for key in ("images", "videos", "audios"):
        chunk = article.get(key) or []
        if isinstance(chunk, list):
            out.extend(m for m in chunk if isinstance(m, dict))
    return out


def _media_captions_for_ner(article: dict) -> Optional[List[dict]]:
    """Alt/title des medias pour enrichir le NER (lien texte <-> image)."""
    captions: List[dict] = []
    for m in _article_media_list(article):
        title = (m.get("title") or "").strip()
        alt = (m.get("alt") or "").strip()
        if not title and not alt:
            continue
        captions.append(
            {
                "media_id": m.get("id") if isinstance(m.get("id"), int) else None,
                "title": title or None,
                "alt": alt or None,
            }
        )
    return captions or None


def _media_items_for_faces(article: dict) -> Optional[List[dict]]:
    """Images (url + id) pour face_detect optionnel."""
    items: List[dict] = []
    sources = article.get("images") or []
    if not sources:
        sources = [
            m
            for m in _article_media_list(article)
            if (m.get("media_type") or "image").lower() in ("image", "img", "")
        ]
    for m in sources:
        if not isinstance(m, dict):
            continue
        url = (m.get("url") or "").strip()
        if not url:
            continue
        items.append(
            {
                "url": url,
                "media_id": m.get("id") if isinstance(m.get("id"), int) else None,
                "media_type": "image",
            }
        )
    return items or None


def _run(coro):
    """Execute une coroutine Celery puis ferme proprement la event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            # Laisser aiosqlite / aiohttp finir leurs callbacks thread-safe
            loop.run_until_complete(asyncio.sleep(0.05))
        except Exception:
            pass
        try:
            loop.run_until_complete(asyncio.sleep(0))
        except Exception:
            pass
        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
        for task in pending:
            task.cancel()
        if pending:
            try:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
        asyncio.set_event_loop(None)


async def _with_db(fn):
    """Init DB, execute fn(db), ferme toujours le pool SQLite."""
    db = Database()
    await db.init_db()
    try:
        return await fn(db)
    finally:
        await db.close()


async def _crawl_and_persist(site_id: int, url: str, max_pages: int, depth: int) -> dict:
    async def _work(db: Database):
        await db.update_site_status(site_id, "analyzing")

        pages_done = 0
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
            logger.debug(
                "page_analyzed site_id=%s n=%s/%s url=%s",
                site_id, pages_done, planned_total["n"], page_url,
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
        from utils import collapse_equivalent_feeds

        feeds = collapse_equivalent_feeds(feeds)
        status = result.status
        if await should_cancel():
            status = "cancelled"
        # Pas de "completed" tant que l'import RSS n'a pas fini (sinon UI aha trop tot).
        if status == "completed" and feeds:
            status = "ingesting"
        await db.update_site_status(
            site_id, status, feeds, result.total_pages_analyzed, merge_feeds=True
        )
        site = await db.get_site(site_id)
        merged = (site or {}).get("rss_feeds") or feeds
        return {
            "status": status,
            "rss_feeds": merged,
            "total_pages_analyzed": result.total_pages_analyzed,
            "error": result.error,
        }

    return await _with_db(_work)


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
                async def _work(db: Database):
                    await db.update_site_status(
                        site_id, "error", feeds, crawl.get("total_pages_analyzed", 0)
                    )

                await _with_db(_work)
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
    async def _work(db: Database):
        await db.update_site_status(site_id, "error")

    await _with_db(_work)


@celery_app.task(name="streamnews.ingest_feed")
def ingest_feed_task(site_id: int, feed_url: str) -> int:
    """Etape 2 (parallelisable) : parse un flux et upsert articles."""
    service = IngestService()
    articles = service.parse_feed(feed_url)

    async def _persist():
        async def _work(db: Database):
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
                    images=art.images or None,
                    videos=getattr(art, "videos", None) or None,
                    audios=getattr(art, "audios", None) or None,
                    article_meta=art.article_meta or None,
                )
                n += 1
            return n

        return await _with_db(_work)

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
    """Etape 3 (fan-in) : marque le site termine + notifie l'UI."""
    articles_count = sum(ingest_counts or [])
    final_status = "completed" if status in (None, "", "ingesting", "analyzing", "completed") else status

    async def _mark_done():
        async def _work(db: Database):
            await db.update_site_status(site_id, final_status, total_pages=pages_analyzed)

        await _with_db(_work)

    try:
        _run(_mark_done())
    except Exception as exc:
        logger.warning("finalize mark status failed site_id=%s: %s", site_id, exc)

    summary = PipelineSummary(
        site_id=site_id,
        url=url,
        status=final_status,
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
            "status": final_status,
        }
    )
    return summary.model_dump()


@celery_app.task(name="streamnews.enrich_article")
def enrich_article_task(article_id: int, force: bool = False) -> dict:
    """Fetch la page article et stocke contenu + meta + images."""

    async def _run_enrich():
        async def _work(db: Database):
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
                new_title = data.get("title")
                if new_title and article.get("title") and new_title == article.get("title"):
                    new_title = None
                existing_meta = article.get("article_meta") or {}
                new_meta = data.get("article_meta") or {}
                merged_meta = {**existing_meta, **new_meta}
                merged_meta["sources"] = list(dict.fromkeys(
                    (existing_meta.get("sources") or []) + (new_meta.get("sources") or [])
                ))
                merged_meta["keywords"] = db._merge_article_meta_dict(
                    existing_meta, new_meta
                ).get("keywords") or existing_meta.get("keywords") or new_meta.get("keywords")
                merged_images = db._merge_image_lists(
                    article.get("images"), data.get("images") or []
                )
                await db.update_article_enrichment(
                    article_id,
                    content_html=data.get("content_html") or "",
                    content_text=data.get("content_text") or "",
                    images=merged_images,
                    videos=data.get("videos") or [],
                    audios=data.get("audios") or [],
                    article_meta=merged_meta,
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

        return await _with_db(_work)

    return _run(_run_enrich())


@celery_app.task(name="streamnews.enrich_site_articles")
def enrich_site_articles_task(site_id: int, limit: int = 50) -> dict:
    """Enqueue l'enrichissement des articles d'un site (sans contenu ok)."""

    async def _list():
        async def _work(db: Database):
            return await db.list_articles_needing_enrichment(site_id, limit=limit)

        return await _with_db(_work)

    articles = _run(_list())
    queued = 0
    for art in articles:
        enrich_article_task.delay(art["id"], False)
        queued += 1
    logger.info("enrich_site_articles site_id=%s queued=%s", site_id, queued)
    return {"site_id": site_id, "queued": queued}


@celery_app.task(name="streamnews.analyze_article")
def analyze_article_task(
    article_id: int,
    force: bool = False,
    tools: Optional[List[str]] = None,
) -> dict:
    """Analyse texte d'un article (outils independants)."""

    async def _run_analyze():
        async def _work(db: Database):
            article = await db.get_article(article_id)
            if not article:
                return {"article_id": article_id, "status": "missing"}

            meta = article.get("article_meta") or {}
            status = article.get("analysis_status") or meta.get("analysis_status")
            if status == "ok" and not force and not tools:
                return {
                    "article_id": article_id,
                    "status": "ok",
                    "skipped": True,
                    "site_id": article.get("site_id"),
                }

            if article.get("enrich_status") != "ok":
                return {
                    "article_id": article_id,
                    "status": "error",
                    "error": "article non enrichi",
                    "site_id": article.get("site_id"),
                }

            await db.set_article_analysis_pending(article_id)
            try:
                existing_analysis = (meta.get("analysis") or {}) if isinstance(meta, dict) else {}
                lang_hint = None
                lang_block = existing_analysis.get("lang_detect") or {}
                if isinstance(lang_block, dict) and lang_block.get("lang"):
                    lang_hint = lang_block["lang"]

                media_captions = _media_captions_for_ner(article)
                media_items = _media_items_for_faces(article)
                payload = analyze_article_content(
                    article.get("content_text"),
                    article.get("content_html"),
                    only=tools,
                    lang_hint=lang_hint,
                    existing_analysis=existing_analysis,
                    media_captions=media_captions,
                    media_items=media_items,
                )
                await db.update_article_analysis(
                    article_id,
                    analysis=payload.get("analysis"),
                    analysis_status=payload.get("analysis_status", "error"),
                    analysis_error=payload.get("analysis_error"),
                    analyzed_at=payload.get("analyzed_at"),
                )
                _send_ws(
                    {
                        "type": "article_analyzed",
                        "article_id": article_id,
                        "site_id": article.get("site_id"),
                        "status": payload.get("analysis_status"),
                    }
                )
                return {
                    "article_id": article_id,
                    "status": payload.get("analysis_status"),
                    "site_id": article.get("site_id"),
                    "tools": list((payload.get("analysis") or {}).keys()),
                }
            except Exception as exc:
                logger.warning("analyze_article failed id=%s: %s", article_id, exc)
                await db.update_article_analysis(
                    article_id,
                    analysis_status="error",
                    analysis_error=str(exc)[:1000],
                )
                return {
                    "article_id": article_id,
                    "status": "error",
                    "error": str(exc),
                    "site_id": article.get("site_id"),
                }

        return await _with_db(_work)

    return _run(_run_analyze())


@celery_app.task(name="streamnews.analyze_site_articles")
def analyze_site_articles_task(site_id: int, limit: int = 50) -> dict:
    """Enqueue l'analyse texte des articles enrichis d'un site."""

    async def _list():
        async def _work(db: Database):
            return await db.list_articles_needing_analysis(site_id, limit=limit)

        return await _with_db(_work)

    articles = _run(_list())
    queued = 0
    for art in articles:
        analyze_article_task.delay(art["id"], False)
        queued += 1
    logger.info("analyze_site_articles site_id=%s queued=%s", site_id, queued)
    return {"site_id": site_id, "queued": queued}


# --- Compat API existante ---

@celery_app.task(bind=True, name="celery_worker.analyze_site_task")
def analyze_site_task(self, site_id: int, url: str, max_pages: int = 50, depth: int = 3):
    """Alias conserve pour main.py / anciennes taches en queue."""
    return crawl_site_task(site_id, url, max_pages, depth)


@celery_app.task(name="celery_worker.cleanup_old_analyses")
def cleanup_old_analyses(days: int = 30):
    async def _clean():
        async def _work(db: Database):
            return await db.cleanup_old_analyses(days)

        return await _with_db(_work)

    try:
        deleted = _run(_clean())
        return {"status": "success", "deleted_sites": deleted, "days": days}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
