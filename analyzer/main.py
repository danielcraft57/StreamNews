import os
import asyncio
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import uvicorn
from database import Database
from rss_analyzer import RSSAnalyzer
from celery_worker import analyze_site_task

app = FastAPI(title="StreamNews Analyzer", version="1.0.0")

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
    await db.init_db()

@app.post("/analyze", response_model=AnalysisResult)
async def analyze_site(request: SiteAnalysisRequest, background_tasks: BackgroundTasks):
    """Lance l'analyse d'un site web pour détecter les flux RSS"""
    try:
        # Validation de l'URL
        if not request.url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="URL invalide")
        
        # Création de l'entrée en base
        site_id = await db.create_site_analysis(request.url, "pending")
        
        # Lancement de l'analyse en arrière-plan
        background_tasks.add_task(analyze_site_task.delay, site_id, request.url, request.max_pages, request.depth)
        
        return AnalysisResult(
            site_id=site_id,
            url=request.url,
            status="pending",
            rss_feeds=[],
            total_pages_analyzed=0
        )
    
    except Exception as e:
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

@app.get("/health")
async def health_check():
    """Vérification de l'état du service"""
    return {"status": "healthy", "service": "analyzer"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) 