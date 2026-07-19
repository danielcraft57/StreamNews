from typing import List, Dict, Set, Optional
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import feedparser
from urllib.parse import urljoin, urlparse
import re

from logging_config import get_logger

logger = get_logger(__name__)

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
        """Trouve les flux RSS sur une page donnée (fetch HTTP)."""
        try:
            async with self.session.get(url, allow_redirects=True) as response:
                if response.status != 200:
                    return []
                try:
                    content = await response.text(errors="ignore")
                except Exception:
                    return []
                final = str(response.url)
                return await self.extract_rss_from_html(final, content)
        except Exception as e:
            logger.error("Erreur recherche RSS sur %s: %s", url, e)
            return []

    async def extract_rss_from_html(
        self, url: str, content: str, soup=None
    ) -> List[Dict]:
        """Detecte les flux RSS dans un HTML deja telecharge (pas de re-fetch page)."""
        rss_feeds: List[Dict] = []
        try:
            if soup is None:
                soup = BeautifulSoup(content, "html.parser")

            title_tag = soup.find("title")
            page_title = title_tag.get_text().strip() if title_tag else None
            self._last_page_title = page_title

            for link in soup.find_all("link"):
                href = link.get("href")
                rel = link.get("rel", [])
                type_attr = link.get("type", "")
                if href and self.is_rss_link(href, rel, type_attr):
                    rss_url = urljoin(url, href)
                    if await self.validate_rss_feed(rss_url):
                        rss_feeds.append({
                            "url": rss_url,
                            "title": link.get("title", "Flux RSS"),
                            "type": type_attr,
                            "source_page": url,
                        })

            for link in soup.find_all("a", href=True):
                href = link.get("href")
                text = link.get_text().lower()
                if href and self.is_rss_link_by_text(href, text):
                    rss_url = urljoin(url, href)
                    if await self.validate_rss_feed(rss_url):
                        rss_feeds.append({
                            "url": rss_url,
                            "title": link.get_text().strip(),
                            "type": "detected",
                            "source_page": url,
                        })
        except Exception as e:
            logger.error("Erreur extract RSS %s: %s", url, e)
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
        """Valide qu'une URL est bien un flux RSS valide (cache URL normalisee)."""
        from utils import normalize_url

        key = normalize_url(url) or url
        if not hasattr(self, "_feed_cache"):
            self._feed_cache = {}
        if key in self._feed_cache:
            return self._feed_cache[key]

        ok = False
        try:
            async with self.session.get(url, timeout=10, allow_redirects=True) as response:
                if response.status != 200:
                    self._feed_cache[key] = False
                    return False
                content = await response.text(errors="ignore")
                feed = feedparser.parse(content)
                ok = bool(len(feed.entries) > 0 or feed.feed.get("title"))
        except Exception:
            ok = False
        self._feed_cache[key] = ok
        return ok

    async def get_internal_links(
        self,
        base_url: str,
        current_url: str,
        depth: int,
        max_links: int = 200,
    ) -> Set[str]:
        """BFS borne : collectea des liens internes sans exploser en recursion.

        Avant : recursion depth=N sur chaque lien = crawl entier du site (blocage).
        Maintenant : file BFS, stop des qu'on a max_links URLs.
        """
        from collections import deque

        found: Set[str] = set()
        # (url, remaining_depth)
        queue: deque = deque([(current_url, depth)])
        seen_pages: Set[str] = set()

        while queue and len(found) < max_links:
            page_url, remaining = queue.popleft()
            if remaining < 0 or page_url in seen_pages:
                continue
            seen_pages.add(page_url)
            self.visited_urls.add(page_url)

            try:
                async with self.session.get(page_url, timeout=15) as response:
                    if response.status != 200:
                        continue
                    content = await response.text()
            except Exception as e:
                logger.warning("Liens: echec fetch %s: %s", page_url, e)
                continue

            try:
                soup = BeautifulSoup(content, "html.parser")
            except Exception as e:
                logger.warning("Liens: parse HTML %s: %s", page_url, e)
                continue

            for link in soup.find_all("a", href=True):
                if len(found) >= max_links:
                    break
                href = link.get("href")
                full_url = urljoin(page_url, href)
                # Ignore ancres / mailto / javascript
                parsed = urlparse(full_url)
                if parsed.scheme not in ("http", "https"):
                    continue
                full_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                if parsed.query:
                    full_url = f"{full_url}?{parsed.query}"

                if not self.is_internal_link(base_url, full_url):
                    continue
                if full_url == base_url or full_url.rstrip("/") == base_url.rstrip("/"):
                    continue
                # Ignore images / assets (pas des pages HTML)
                path_l = (parsed.path or "").lower()
                if path_l.endswith((
                    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
                    ".css", ".js", ".ico", ".pdf", ".zip", ".mp4", ".mp3",
                    ".woff", ".woff2", ".ttf",
                )):
                    continue

                if full_url not in found:
                    found.add(full_url)
                    if remaining > 1 and full_url not in seen_pages:
                        queue.append((full_url, remaining - 1))

        logger.info(
            "Liens internes: %s trouves (max=%s, pages_visitees=%s, depth=%s) depuis %s",
            len(found),
            max_links,
            len(seen_pages),
            depth,
            current_url,
        )
        return found

    def is_internal_link(self, base_url: str, link_url: str) -> bool:
        """Vérifie si un lien est interne au site (ignore www / casse)."""
        try:
            base_domain = urlparse(base_url).netloc.lower().removeprefix("www.")
            link_domain = urlparse(link_url).netloc.lower().removeprefix("www.")
            return base_domain == link_domain and bool(link_domain)
        except Exception:
            return False

    def remove_duplicate_rss(self, rss_feeds: List[Dict]) -> List[Dict]:
        """Supprime les flux RSS en double (http/https, slash, www...)."""
        from utils import normalize_url

        seen_urls = set()
        unique_feeds = []

        for feed in rss_feeds:
            raw = (feed.get("url") or "").strip()
            if not raw:
                continue
            key = normalize_url(raw) or raw
            if key in seen_urls:
                continue
            seen_urls.add(key)
            cleaned = dict(feed)
            cleaned["url"] = key
            unique_feeds.append(cleaned)

        return unique_feeds
