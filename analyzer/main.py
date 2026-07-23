import os
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import requests

from logging_config import setup_logging

# Avant tout import Celery (sinon worker.log ecrase analyzer.log)
logger = setup_logging(service="analyzer")

from database import Database
from rss_analyzer import RSSAnalyzer
from celery_worker import (
    analyze_site_task,
    analyze_article_task,
    analyze_site_articles_task,
    enrich_article_task,
    enrich_site_articles_task,
    refresh_all_feeds_task,
)
from services.text_analysis_service import available_analyzers
from celery_app import celery_app

app = FastAPI(title="StreamNews Analyzer", version="0.2.0")

# Initialisation de la base de données
db = Database()
analyzer = RSSAnalyzer()

class SiteAnalysisRequest(BaseModel):
    url: str
    max_pages: int = 50
    depth: int = 3

class AnalysisResult(BaseModel):
    site_id: int
    url: str
    status: str
    rss_feeds: list
    total_pages_analyzed: int

@app.on_event("startup")
async def startup_event():
    logger.info("Startup analyzer: init DB")
    await db.init_db()
    logger.info("Startup analyzer: DB OK")

@app.post("/analyze", response_model=AnalysisResult)
async def analyze_site(request: SiteAnalysisRequest):
    """Lance l'analyse d'un site web pour détecter les flux RSS"""
    try:
        # Validation de l'URL
        if not request.url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="URL invalide")

        upsert = await db.upsert_site_for_analysis(request.url, "pending")
        site_id = upsert["site_id"]

        # Relance sur le meme domaine : stoppe l'ancienne tache si encore active
        old_task = upsert.get("old_task_id")
        if upsert.get("reused") and old_task and upsert.get("old_status") in (
            "pending", "analyzing", "ingest_scheduled", "cancelling",
        ):
            try:
                celery_app.control.revoke(old_task, terminate=True, signal="SIGTERM")
                logger.info(
                    "Revoke ancienne tache %s pour domaine %s",
                    old_task,
                    upsert.get("domain"),
                )
            except Exception as exc:
                logger.warning("revoke old task failed: %s", exc)

        logger.info(
            "Analyze queued site_id=%s reused=%s domain=%s url=%s max_pages=%s depth=%s",
            site_id,
            upsert.get("reused"),
            upsert.get("domain"),
            request.url,
            request.max_pages,
            request.depth,
        )

        async_result = analyze_site_task.delay(
            site_id, request.url, request.max_pages, request.depth
        )
        await db.set_celery_task_id(site_id, async_result.id)
        logger.info("Celery task_id=%s site_id=%s", async_result.id, site_id)

        site = await db.get_site(site_id)
        return AnalysisResult(
            site_id=site_id,
            url=request.url,
            status="pending",
            rss_feeds=(site or {}).get("rss_feeds") or [],
            total_pages_analyzed=(site or {}).get("total_pages_analyzed") or 0,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("analyze failed url=%s", request.url)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sites")
async def get_sites():
    """Récupère la liste des sites analysés"""
    try:
        sites = await db.get_all_sites()
        return {"sites": sites}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sites/{site_id}")
async def get_site(site_id: int):
    """Récupère les détails d'un site analysé"""
    try:
        site = await db.get_site(site_id)
        if not site:
            raise HTTPException(status_code=404, detail="Site non trouvé")
        return site
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/sites/{site_id}")
async def delete_site(site_id: int):
    """Supprime un site + pages + articles (feeds JSON inclus)."""
    try:
        result = await db.delete_site(site_id)
        if not result:
            raise HTTPException(status_code=404, detail="Site non trouvé")
        return {"status": "deleted", **result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/sites/{site_id}/stop")
async def stop_site_analysis(site_id: int):
    """Arrete une analyse en cours (revoke Celery + statut cancelled)."""
    try:
        site = await db.get_site(site_id)
        if not site:
            raise HTTPException(status_code=404, detail="Site non trouvé")

        if site.get("status") in ("completed", "error", "cancelled"):
            return {
                "status": site.get("status"),
                "site_id": site_id,
                "message": "Rien a arreter",
            }

        await db.update_site_status(site_id, "cancelled")
        logger.info("Stop analysis site_id=%s task_id=%s", site_id, site.get("celery_task_id"))

        task_id = site.get("celery_task_id")
        if task_id:
            try:
                celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
            except Exception as exc:
                logger.warning("revoke failed site_id=%s: %s", site_id, exc)

        try:
            web_url = os.getenv("WEB_URL", "http://localhost:3000")
            requests.post(
                f"{web_url}/api/websocket",
                json={
                    "type": "analysis_cancelled",
                    "site_id": site_id,
                    "url": site.get("url"),
                },
                timeout=5,
            )
        except Exception:
            pass

        return {"status": "cancelled", "site_id": site_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sites/{site_id}/pages")
async def get_site_pages(site_id: int):
    """Récupère les pages analysées d'un site"""
    try:
        site = await db.get_site(site_id)
        if not site:
            raise HTTPException(status_code=404, detail="Site non trouvé")
        pages = await db.get_site_pages(site_id)
        return {"site_id": site_id, "pages": pages}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sites/{site_id}/articles")
async def get_site_articles(site_id: int, limit: int = 100):
    """Récupère les articles extraits des flux RSS d'un site"""
    try:
        site = await db.get_site(site_id)
        if not site:
            raise HTTPException(status_code=404, detail="Site non trouvé")
        limit = max(1, min(limit, 500))
        articles = await db.get_site_articles(site_id, limit=limit)
        return {"site_id": site_id, "articles": articles, "count": len(articles)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/articles/search")
async def search_articles(q: str = "", site_id: int | None = None, limit: int = 40):
    """Recherche full-text simple dans les articles importes."""
    try:
        query = (q or "").strip()
        if len(query) < 2:
            return {"query": query, "articles": [], "count": 0}
        limit = max(1, min(limit, 100))
        articles = await db.search_articles(query, site_id=site_id, limit=limit)
        return {"query": query, "articles": articles, "count": len(articles)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/trends")
async def get_trends(
    days: int = 30,
    site_id: int | None = None,
    kind: str = "all",
    limit: int = 40,
    refresh: bool = False,
    collection_id: int | None = None,
):
    """Tendances calculees (mots-cles, entites, YAKE) stockees en BDD."""
    try:
        from services.trends_service import TrendsService

        svc = TrendsService(db)
        days = max(1, min(days, 365))
        site_ids = None
        if collection_id:
            from services.collections_service import CollectionsService

            site_ids = await CollectionsService(db).get_site_ids(collection_id)

        if refresh or site_ids is not None:
            data = await svc.refresh(
                window_days=days, site_id=site_id, site_ids=site_ids, limit=limit
            )
        else:
            data = await svc.list_stored(
                window_days=days, site_id=site_id, kind=kind, limit=limit
            )
            if not data["trends"]:
                data = await svc.refresh(
                    window_days=days, site_id=site_id, site_ids=site_ids, limit=limit
                )

        if kind and kind != "all":
            data["trends"] = [t for t in data["trends"] if t.get("kind") == kind]
            data["count"] = len(data["trends"])
            data["kind"] = kind
        else:
            data["kind"] = "all"
        data["collection_id"] = collection_id
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/trends/refresh")
async def refresh_trends(
    days: int = 30,
    site_id: int | None = None,
    limit: int = 50,
    collection_id: int | None = None,
):
    """Recalcule et persiste les tendances."""
    try:
        from services.trends_service import TrendsService

        site_ids = None
        if collection_id:
            from services.collections_service import CollectionsService

            site_ids = await CollectionsService(db).get_site_ids(collection_id)
        data = await TrendsService(db).refresh(
            window_days=days, site_id=site_id, site_ids=site_ids, limit=limit
        )
        data["collection_id"] = collection_id
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/radar")
async def get_radar(
    days: int = 30,
    theme: str = "all",
    limit: int = 40,
    refresh: bool = False,
    collection_id: int | None = None,
):
    """Radar idees : opportunites SaaS/IT depuis intent + themes."""
    try:
        from services.idea_radar_service import IdeaRadarService

        site_ids = None
        if collection_id:
            from services.collections_service import CollectionsService

            site_ids = await CollectionsService(db).get_site_ids(collection_id)

        svc = IdeaRadarService(db)
        days = max(1, min(days, 365))
        if refresh or site_ids is not None:
            data = await svc.refresh(window_days=days, limit=limit, site_ids=site_ids)
            if theme and theme != "all":
                data["ideas"] = [i for i in data["ideas"] if i.get("theme") == theme]
                data["count"] = len(data["ideas"])
                data["theme"] = theme
            else:
                data["theme"] = "all"
            data["collection_id"] = collection_id
            return data

        data = await svc.list_stored(window_days=days, theme=theme, limit=limit)
        if not data["ideas"]:
            refreshed = await svc.refresh(window_days=days, limit=limit, site_ids=site_ids)
            if theme and theme != "all":
                refreshed["ideas"] = [
                    i for i in refreshed["ideas"] if i.get("theme") == theme
                ]
                refreshed["count"] = len(refreshed["ideas"])
                refreshed["theme"] = theme
            else:
                refreshed["theme"] = "all"
            refreshed["collection_id"] = collection_id
            return refreshed
        data["collection_id"] = collection_id
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/radar/refresh")
async def refresh_radar(
    days: int = 30,
    limit: int = 40,
    collection_id: int | None = None,
):
    """Recalcule et persiste le radar idees."""
    try:
        from services.idea_radar_service import IdeaRadarService

        site_ids = None
        if collection_id:
            from services.collections_service import CollectionsService

            site_ids = await CollectionsService(db).get_site_ids(collection_id)
        svc = IdeaRadarService(db)
        return await svc.refresh(window_days=days, limit=limit, site_ids=site_ids)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/watchlist/keywords")
async def watchlist_keywords():
    try:
        from services.watchlist_service import WatchlistService

        kws = await WatchlistService(db).list_keywords()
        return {"keywords": kws, "count": len(kws)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/watchlist/keywords")
async def watchlist_add_keyword(payload: dict):
    try:
        from services.watchlist_service import WatchlistService

        return await WatchlistService(db).add_keyword(payload.get("keyword") or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/watchlist/keywords/{keyword_id}")
async def watchlist_delete_keyword(keyword_id: int):
    try:
        from services.watchlist_service import WatchlistService

        await WatchlistService(db).delete_keyword(keyword_id)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/watchlist/alerts")
async def watchlist_alerts(days: int = 7, limit: int = 40, refresh: bool = False):
    try:
        from services.watchlist_service import WatchlistService

        svc = WatchlistService(db)
        if refresh:
            return await svc.refresh(window_days=days)
        return await svc.list_alerts(window_days=days, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/watchlist/refresh")
async def watchlist_refresh(days: int = 7):
    try:
        from services.watchlist_service import WatchlistService

        return await WatchlistService(db).refresh(window_days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/brief/weekly")
async def brief_weekly(week: str | None = None, refresh: bool = False):
    try:
        from services.brief_service import BriefService

        svc = BriefService(db)
        if refresh:
            return await svc.refresh(week_start=week)
        return await svc.get(week_start=week)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/brief/weekly/refresh")
async def brief_weekly_refresh(week: str | None = None):
    try:
        from services.brief_service import BriefService

        return await BriefService(db).refresh(week_start=week)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/brief/daily")
async def brief_daily(day: str | None = None, refresh: bool = False, auto: bool = True):
    try:
        from services.brief_service import BriefService

        svc = BriefService(db)
        if refresh:
            return await svc.refresh_daily(day=day)
        return await svc.get_daily(day=day, auto=auto)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/brief/daily/refresh")
async def brief_daily_refresh(day: str | None = None):
    try:
        from services.brief_service import BriefService

        return await BriefService(db).refresh_daily(day=day)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/collections")
async def list_collections():
    try:
        from services.collections_service import CollectionsService

        cols = await CollectionsService(db).list_collections()
        return {"collections": cols, "count": len(cols)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/collections/{collection_id}")
async def get_collection(collection_id: int):
    try:
        from services.collections_service import CollectionsService

        col = await CollectionsService(db).get_collection(collection_id)
        if not col:
            raise HTTPException(status_code=404, detail="Collection introuvable")
        return col
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/collections/{collection_id}/sites")
async def collection_add_site(collection_id: int, payload: dict):
    try:
        from services.collections_service import CollectionsService

        site_id = int(payload.get("site_id") or 0)
        if not site_id:
            raise HTTPException(status_code=400, detail="site_id requis")
        return await CollectionsService(db).add_site(collection_id, site_id)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/collections/{collection_id}/sites/{site_id}")
async def collection_remove_site(collection_id: int, site_id: int):
    try:
        from services.collections_service import CollectionsService

        return await CollectionsService(db).remove_site(collection_id, site_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ideas")
async def list_ideas(limit: int = 50):
    try:
        from services.idea_notes_service import IdeaNotesService

        notes = await IdeaNotesService(db).list_notes(limit=limit)
        return {"ideas": notes, "count": len(notes)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ideas")
async def create_idea(payload: dict):
    try:
        from services.idea_notes_service import IdeaNotesService

        return await IdeaNotesService(db).create(payload or {})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ideas/from-radar")
async def create_idea_from_radar(payload: dict):
    try:
        from services.idea_notes_service import IdeaNotesService

        return await IdeaNotesService(db).from_radar(payload or {})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ideas/{note_id}")
async def get_idea(note_id: int):
    try:
        from services.idea_notes_service import IdeaNotesService

        note = await IdeaNotesService(db).get(note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Fiche introuvable")
        return note
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/ideas/{note_id}")
async def patch_idea(note_id: int, payload: dict):
    try:
        from services.idea_notes_service import IdeaNotesService

        note = await IdeaNotesService(db).update(note_id, payload or {})
        if not note:
            raise HTTPException(status_code=404, detail="Fiche introuvable")
        return note
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/ideas/{note_id}")
async def delete_idea(note_id: int):
    try:
        from services.idea_notes_service import IdeaNotesService

        await IdeaNotesService(db).delete(note_id)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ideas/{note_id}/markdown")
async def idea_markdown(note_id: int):
    try:
        from services.idea_notes_service import IdeaNotesService, render_idea_markdown

        note = await IdeaNotesService(db).get(note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Fiche introuvable")
        return {"id": note_id, "markdown": render_idea_markdown(note), "title": note.get("title")}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sites/{site_id}/ingest-articles")
async def ingest_site_articles(site_id: int):
    """Re-parse les flux deja detectes et (re)importe les articles."""
    try:
        site = await db.get_site(site_id)
        if not site:
            raise HTTPException(status_code=404, detail="Site non trouvé")
        feeds = site.get("rss_feeds") or []
        if not feeds:
            return {"site_id": site_id, "articles_count": 0, "message": "Aucun flux RSS"}
        count = await db.ingest_rss_articles(site_id, feeds)
        return {"site_id": site_id, "articles_count": count}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/feeds/refresh-all")
async def feeds_refresh_all():
    """Enqueue le rechargement de tous les flux (meme tache que le cron beat)."""
    try:
        async_result = refresh_all_feeds_task.delay()
        return {
            "status": "queued",
            "task_id": async_result.id,
            "message": "Rechargement des flux en file d'attente",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/articles/{article_id}")
async def get_article(article_id: int):
    """Detail d'un article (contenu enrichi inclus)."""
    try:
        article = await db.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article non trouvé")
        return article
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/articles/{article_id}/enrich")
async def enrich_article(article_id: int, force: bool = False):
    """Enqueue l'enrichissement d'un article (contenu + meta + images)."""
    try:
        article = await db.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article non trouvé")

        if article.get("enrich_status") == "ok" and not force:
            return {
                "article_id": article_id,
                "site_id": article.get("site_id"),
                "status": "ok",
                "queued": False,
                "message": "Deja enrichi",
            }

        await db.set_article_enrich_pending(article_id)
        async_result = enrich_article_task.delay(article_id, force)
        logger.info(
            "Enrich queued article_id=%s task=%s force=%s",
            article_id,
            async_result.id,
            force,
        )
        return {
            "article_id": article_id,
            "site_id": article.get("site_id"),
            "status": "pending",
            "queued": True,
            "task_id": async_result.id,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/sites/{site_id}/enrich-articles")
async def enrich_site_articles(site_id: int, limit: int = 50):
    """Enqueue l'enrichissement des articles d'un site (max `limit`)."""
    try:
        site = await db.get_site(site_id)
        if not site:
            raise HTTPException(status_code=404, detail="Site non trouvé")
        limit = max(1, min(limit, 200))
        async_result = enrich_site_articles_task.delay(site_id, limit)
        logger.info(
            "Enrich site queued site_id=%s limit=%s task=%s",
            site_id,
            limit,
            async_result.id,
        )
        return {
            "site_id": site_id,
            "status": "queued",
            "limit": limit,
            "task_id": async_result.id,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/text-analysis/analyzers")
async def list_text_analyzers():
    """Liste les outils d'analyse texte et leur disponibilite."""
    return {"analyzers": available_analyzers()}

@app.post("/articles/{article_id}/analyze")
async def analyze_article(
    article_id: int,
    force: bool = False,
    tools: Optional[str] = None,
):
    """Enqueue l'analyse texte d'un article (tous les outils ou une liste comma-separee)."""
    try:
        article = await db.get_article(article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article non trouvé")

        if article.get("enrich_status") != "ok":
            raise HTTPException(
                status_code=400,
                detail="Article non enrichi (lancer enrich d'abord)",
            )

        meta = article.get("article_meta") or {}
        tool_list = [t.strip() for t in tools.split(",") if t.strip()] if tools else None
        status = article.get("analysis_status") or meta.get("analysis_status")
        if status == "ok" and not force and not tool_list:
            return {
                "article_id": article_id,
                "site_id": article.get("site_id"),
                "status": "ok",
                "queued": False,
                "message": "Deja analyse",
            }

        await db.set_article_analysis_pending(article_id)
        async_result = analyze_article_task.delay(article_id, force, tool_list)
        return {
            "article_id": article_id,
            "site_id": article.get("site_id"),
            "status": "pending",
            "queued": True,
            "task_id": async_result.id,
            "tools": tool_list,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/sites/{site_id}/analyze-articles")
async def analyze_site_articles(site_id: int, limit: int = 50):
    """Enqueue l'analyse texte des articles enrichis d'un site."""
    try:
        site = await db.get_site(site_id)
        if not site:
            raise HTTPException(status_code=404, detail="Site non trouvé")
        limit = max(1, min(limit, 200))
        async_result = analyze_site_articles_task.delay(site_id, limit)
        return {
            "site_id": site_id,
            "status": "queued",
            "limit": limit,
            "task_id": async_result.id,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Vérification de l'état du service"""
    return {"status": "healthy", "service": "analyzer"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) 