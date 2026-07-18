import asyncio
import aiohttp
from bs4 import BeautifulSoup
import feedparser
from urllib.parse import urljoin, urlparse
import re
from typing import List, Dict, Set, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RSSAnalyzer:
    def __init__(self):
        self.session = None
        self.visited_urls = set()
        self._last_page_title = None
        self.rss_patterns = [
            r'application/rss\+xml',
            r'application/atom\+xml',
            r'application/xml',
            r'text/xml'
        ]
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def analyze_site(self, base_url: str, max_pages: int = 50, depth: int = 3) -> Dict:
        """Analyse complète d'un site web pour détecter les flux RSS"""
        self.visited_urls.clear()
        all_rss_feeds = []
        pages_analyzed = 0
        
        try:
            async with self:
                # Analyse de la page d'accueil
                logger.info(f"Début de l'analyse de {base_url}")
                
                # Recherche des flux RSS sur la page d'accueil
                home_rss = await self.find_rss_feeds(base_url)
                all_rss_feeds.extend(home_rss)
                
                # Crawl des pages internes
                internal_urls = list(await self.get_internal_links(base_url, base_url, depth))
                
                for url in internal_urls[:max(0, max_pages - 1)]:  # -1 car on a déjà analysé la page d'accueil
                    if pages_analyzed >= max_pages:
                        break
                        
                    try:
                        page_rss = await self.find_rss_feeds(url)
                        all_rss_feeds.extend(page_rss)
                        pages_analyzed += 1
                        
                        if pages_analyzed % 10 == 0:
                            logger.info(f"Pages analysées: {pages_analyzed}")
                            
                    except Exception as e:
                        logger.error(f"Erreur lors de l'analyse de {url}: {e}")
                        continue
                
                # Suppression des doublons
                unique_rss = self.remove_duplicate_rss(all_rss_feeds)
                
                return {
                    'rss_feeds': unique_rss,
                    'total_pages_analyzed': pages_analyzed + 1,  # +1 pour la page d'accueil
                    'status': 'completed'
                }
                
        except Exception as e:
            logger.error(f"Erreur lors de l'analyse du site {base_url}: {e}")
            return {
                'rss_feeds': all_rss_feeds,
                'total_pages_analyzed': pages_analyzed,
                'status': 'error',
                'error': str(e)
            }

    async def find_rss_feeds(self, url: str) -> List[Dict]:
        """Trouve les flux RSS sur une page donnée"""
        rss_feeds = []
        
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    return rss_feeds
                    
                content = await response.text()
                soup = BeautifulSoup(content, 'html.parser')

                title_tag = soup.find('title')
                page_title = title_tag.get_text().strip() if title_tag else None
                self._last_page_title = page_title
                
                # Recherche des liens RSS dans les balises link
                for link in soup.find_all('link'):
                    href = link.get('href')
                    rel = link.get('rel', [])
                    type_attr = link.get('type', '')
                    
                    if href and self.is_rss_link(href, rel, type_attr):
                        rss_url = urljoin(url, href)
                        title = link.get('title', 'Flux RSS')
                        
                        # Validation du flux RSS
                        if await self.validate_rss_feed(rss_url):
                            rss_feeds.append({
                                'url': rss_url,
                                'title': title,
                                'type': type_attr,
                                'source_page': url
                            })
                
                # Recherche de liens RSS dans le contenu
                for link in soup.find_all('a', href=True):
                    href = link.get('href')
                    text = link.get_text().lower()
                    
                    if href and self.is_rss_link_by_text(href, text):
                        rss_url = urljoin(url, href)
                        
                        if await self.validate_rss_feed(rss_url):
                            rss_feeds.append({
                                'url': rss_url,
                                'title': link.get_text().strip(),
                                'type': 'detected',
                                'source_page': url
                            })
                
                # Recherche de patterns RSS dans le HTML
                rss_patterns = [
                    r'feed\.xml',
                    r'rss\.xml',
                    r'atom\.xml',
                    r'\.rss$',
                    r'\.xml$'
                ]
                
                for pattern in rss_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    for match in matches:
                        # Construction de l'URL RSS
                        if match.startswith('http'):
                            rss_url = match
                        else:
                            rss_url = urljoin(url, match)
                        
                        if await self.validate_rss_feed(rss_url):
                            rss_feeds.append({
                                'url': rss_url,
                                'title': f'Flux RSS détecté ({match})',
                                'type': 'pattern',
                                'source_page': url
                            })
                            
        except Exception as e:
            logger.error(f"Erreur lors de la recherche de flux RSS sur {url}: {e}")
            
        return rss_feeds

    def is_rss_link(self, href: str, rel: List[str], type_attr: str) -> bool:
        """Vérifie si un lien est un flux RSS"""
        if not href:
            return False
            
        # Vérification du type MIME
        if any(pattern in type_attr.lower() for pattern in self.rss_patterns):
            return True
            
        # Vérification de l'attribut rel
        if 'alternate' in rel and type_attr:
            return True
            
        # Vérification de l'URL
        href_lower = href.lower()
        rss_indicators = ['rss', 'feed', 'atom', '.xml']
        return any(indicator in href_lower for indicator in rss_indicators)

    def is_rss_link_by_text(self, href: str, text: str) -> bool:
        """Vérifie si un lien est un flux RSS basé sur le texte"""
        if not href:
            return False
            
        text_indicators = ['rss', 'feed', 'flux', 'syndication']
        return any(indicator in text for indicator in text_indicators)

    async def validate_rss_feed(self, url: str) -> bool:
        """Valide qu'une URL est bien un flux RSS valide"""
        try:
            async with self.session.get(url, timeout=10) as response:
                if response.status != 200:
                    return False
                    
                content = await response.text()
                
                # Tentative de parsing avec feedparser
                feed = feedparser.parse(content)
                return len(feed.entries) > 0 or feed.feed.get('title')
                
        except Exception:
            return False

    async def get_internal_links(self, base_url: str, current_url: str, depth: int) -> Set[str]:
        """Récupère les liens internes d'un site"""
        if depth <= 0 or current_url in self.visited_urls:
            return set()
            
        self.visited_urls.add(current_url)
        internal_links = set()
        
        try:
            async with self.session.get(current_url) as response:
                if response.status != 200:
                    return internal_links
                    
                content = await response.text()
                soup = BeautifulSoup(content, 'html.parser')
                
                for link in soup.find_all('a', href=True):
                    href = link.get('href')
                    full_url = urljoin(current_url, href)
                    
                    # Vérification que c'est un lien interne
                    if self.is_internal_link(base_url, full_url):
                        internal_links.add(full_url)
                        
                        # Récursion pour les liens plus profonds
                        if depth > 1:
                            sub_links = await self.get_internal_links(base_url, full_url, depth - 1)
                            internal_links.update(sub_links)
                            
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des liens internes de {current_url}: {e}")
            
        return internal_links

    def is_internal_link(self, base_url: str, link_url: str) -> bool:
        """Vérifie si un lien est interne au site"""
        try:
            base_domain = urlparse(base_url).netloc
            link_domain = urlparse(link_url).netloc
            return base_domain == link_domain
        except:
            return False

    def remove_duplicate_rss(self, rss_feeds: List[Dict]) -> List[Dict]:
        """Supprime les flux RSS en double"""
        seen_urls = set()
        unique_feeds = []
        
        for feed in rss_feeds:
            if feed['url'] not in seen_urls:
                seen_urls.add(feed['url'])
                unique_feeds.append(feed)
                
        return unique_feeds 