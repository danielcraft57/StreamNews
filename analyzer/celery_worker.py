import os
import asyncio
import json
import requests
from celery import Celery
from database import Database
from rss_analyzer import RSSAnalyzer
from typing import List, Dict

# Configuration Celery
celery_app = Celery('streamnews_analyzer')
celery_app.conf.update(
    broker_url=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    result_backend=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
)

def send_websocket_message(message):
    """Envoie un message via WebSocket au service web"""
    try:
        web_url = os.getenv('WEB_URL', 'http://localhost:3000')
        requests.post(f'{web_url}/api/websocket', json=message, timeout=5)
    except Exception as e:
        print(f"Erreur lors de l'envoi du message WebSocket: {e}")

@celery_app.task(bind=True)
def analyze_site_task(self, site_id: int, url: str, max_pages: int = 50, depth: int = 3):
    """Tâche Celery pour analyser un site web avec streaming en temps réel"""
    db = Database()
    
    try:
        # Initialisation de la base de données
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Mise à jour du statut et notification
        loop.run_until_complete(db.init_db())
        loop.run_until_complete(db.update_site_status(site_id, "analyzing"))
        
        # Message de début d'analyse
        send_websocket_message({
            'type': 'analysis_started',
            'site_id': site_id,
            'url': url,
            'max_pages': max_pages,
            'total_pages': max_pages
        })
        
        # Création d'un analyseur personnalisé avec callbacks
        class StreamingRSSAnalyzer(RSSAnalyzer):
            def __init__(self, site_id):
                super().__init__()
                self.site_id = site_id
                self.pages_analyzed = 0
                self.rss_feeds_found = []
            
            async def find_rss_feeds(self, url: str) -> List[Dict]:
                """Override pour envoyer des messages en temps réel"""
                rss_feeds = await super().find_rss_feeds(url)
                
                # Notification de page analysée
                self.pages_analyzed += 1
                send_websocket_message({
                    'type': 'page_analyzed',
                    'site_id': self.site_id,
                    'url': url,
                    'pages_analyzed': self.pages_analyzed,
                    'total_pages': max_pages
                })
                
                # Notification des flux RSS trouvés
                for feed in rss_feeds:
                    if feed not in self.rss_feeds_found:
                        self.rss_feeds_found.append(feed)
                        send_websocket_message({
                            'type': 'rss_found',
                            'site_id': self.site_id,
                            'rss_url': feed['url'],
                            'title': feed['title'],
                            'source_page': feed['source_page']
                        })
                
                return rss_feeds
        
        # Analyse du site avec streaming
        analyzer = StreamingRSSAnalyzer(site_id)
        result = loop.run_until_complete(analyzer.analyze_site(url, max_pages, depth))
        
        # Mise à jour des résultats en base
        loop.run_until_complete(db.update_site_status(
            site_id, 
            result['status'], 
            result['rss_feeds'], 
            result['total_pages_analyzed']
        ))
        
        # Message de fin d'analyse
        send_websocket_message({
            'type': 'analysis_completed',
            'site_id': site_id,
            'url': url,
            'rss_count': len(result['rss_feeds']),
            'total_pages': result['total_pages_analyzed'],
            'status': result['status']
        })
        
        loop.close()
        
        return {
            'site_id': site_id,
            'status': 'success',
            'rss_feeds_count': len(result['rss_feeds']),
            'pages_analyzed': result['total_pages_analyzed']
        }
        
    except Exception as e:
        # Mise à jour du statut en cas d'erreur
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(db.init_db())
            loop.run_until_complete(db.update_site_status(site_id, "error"))
            loop.close()
        except:
            pass
        
        # Message d'erreur
        send_websocket_message({
            'type': 'analysis_error',
            'site_id': site_id,
            'url': url,
            'error': str(e)
        })
            
        return {
            'site_id': site_id,
            'status': 'error',
            'error': str(e)
        }

@celery_app.task
def cleanup_old_analyses():
    """Nettoyage des anciennes analyses"""
    db = Database()
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(db.init_db())
        
        # Suppression des analyses de plus de 30 jours
        # (à implémenter dans la classe Database)
        
        loop.close()
        return {'status': 'success', 'message': 'Nettoyage terminé'}
        
    except Exception as e:
        return {'status': 'error', 'error': str(e)} 