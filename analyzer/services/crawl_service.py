"""Service de crawl : orchestration de RSSAnalyzer avec concurrence bornee."""
from __future__ import annotations

import asyncio
import os
from collections import deque
from typing import Awaitable, Callable, List, Optional, Set
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from logging_config import get_logger
from models import CrawlResult, FeedRef
from rss_analyzer import RSSAnalyzer
from utils import normalize_url

logger = get_logger(__name__)

PageHook = Callable[[str, Optional[str], List[dict]], Awaitable[None]]
FeedHook = Callable[[dict], Awaitable[None]]
CancelHook = Callable[[], Awaitable[bool]]
PlanHook = Callable[[int], Awaitable[None]]

_SKIP_EXT = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
    ".css", ".js", ".ico", ".pdf", ".zip", ".mp4", ".mp3",
    ".woff", ".woff2", ".ttf",
)


class CrawlService:
    """
    Pipeline crawl en une passe :
      BFS pages uniques (URL normalisee) -> RSS + liens, sans re-fetcher.
    """

    def __init__(
        self,
        concurrency: Optional[int] = None,
        on_page: Optional[PageHook] = None,
        on_feed: Optional[FeedHook] = None,
        on_plan: Optional[PlanHook] = None,
    ):
        self.concurrency = concurrency or int(os.getenv("CRAWL_CONCURRENCY", "3"))
        self.on_page = on_page
        self.on_feed = on_feed
        self.on_plan = on_plan

    async def run(
        self,
        base_url: str,
        max_pages: int = 50,
        depth: int = 3,
        should_cancel: Optional[CancelHook] = None,
    ) -> CrawlResult:
        analyzer = _HookedAnalyzer(self.on_page, self.on_feed, self.on_plan)
        analyzer.concurrency = self.concurrency
        raw = await analyzer.analyze_site_concurrent(
            base_url, max_pages, depth, should_cancel=should_cancel
        )
        feeds = [FeedRef(**f) if not isinstance(f, FeedRef) else f for f in raw.get("rss_feeds", [])]
        return CrawlResult(
            status=raw.get("status", "completed"),
            rss_feeds=feeds,
            total_pages_analyzed=raw.get("total_pages_analyzed", 0),
            error=raw.get("error"),
        )


class _HookedAnalyzer(RSSAnalyzer):
    def __init__(self, on_page, on_feed, on_plan=None):
        super().__init__()
        self.on_page = on_page
        self.on_feed = on_feed
        self.on_plan = on_plan
        self.concurrency = 3
        self._seen_feeds: Set[str] = set()

    async def _emit_page(self, url: str, title: Optional[str], feeds: List[dict]):
        if self.on_page:
            await self.on_page(url, title, feeds)
        if self.on_feed:
            for feed in feeds:
                key = normalize_url(feed.get("url") or "") or feed.get("url")
                if key and key not in self._seen_feeds:
                    self._seen_feeds.add(key)
                    await self.on_feed(feed)

    async def find_rss_feeds(self, url: str):
        """Compat : fetch + extract + hooks."""
        feeds = await super().find_rss_feeds(url)
        title = getattr(self, "_last_page_title", None)
        await self._emit_page(url, title, feeds)
        return feeds

    def _extract_internal_hrefs(self, base_url: str, page_url: str, soup) -> List[str]:
        out: List[str] = []
        seen: Set[str] = set()
        for link in soup.find_all("a", href=True):
            href = link.get("href")
            full = urljoin(page_url, href)
            parsed = urlparse(full)
            if parsed.scheme not in ("http", "https"):
                continue
            path_l = (parsed.path or "").lower()
            if path_l.endswith(_SKIP_EXT):
                continue
            if not self.is_internal_link(base_url, full):
                continue
            key = normalize_url(full)
            if not key or key in seen:
                continue
            # Ignore home
            if key == normalize_url(base_url):
                continue
            seen.add(key)
            out.append(full)
        return out

    async def _fetch_html(self, url: str):
        """Retourne (final_url, html) ou (None, None)."""
        try:
            async with self.session.get(url, timeout=15, allow_redirects=True) as response:
                if response.status != 200:
                    return None, None
                ctype = (response.headers.get("Content-Type") or "").lower()
                if "html" not in ctype and "text/" not in ctype and ctype:
                    # skip binary
                    if any(x in ctype for x in ("image/", "font/", "application/pdf", "video/", "audio/")):
                        return None, None
                try:
                    html = await response.text(errors="ignore")
                except Exception:
                    return None, None
                final = str(response.url)
                return final, html
        except Exception as exc:
            logger.warning("Fetch echec %s: %s", url, exc)
            return None, None

    async def analyze_site_concurrent(
        self,
        base_url: str,
        max_pages: int = 50,
        depth: int = 3,
        should_cancel: Optional[CancelHook] = None,
    ) -> dict:
        """
        BFS une passe : chaque URL normalisee n'est fetchee qu'une fois.
        RSS + liens internes extraits du meme HTML.
        """
        self.visited_urls.clear()
        all_rss_feeds: List[dict] = []
        pages_analyzed = 0
        seen_keys: Set[str] = set()
        # (url_brute, depth_restant)
        queue: deque = deque([(base_url, depth)])

        async def _cancelled() -> bool:
            if not should_cancel:
                return False
            try:
                return bool(await should_cancel())
            except Exception:
                return False

        # Plan provisoire = plafond ; ajuste si on termine plus tot
        if self.on_plan:
            try:
                await self.on_plan(max_pages)
            except Exception as exc:
                logger.warning("on_plan failed: %s", exc)

        try:
            async with self:
                logger.info(
                    "Crawl BFS %s (max_pages=%s depth=%s concurrency=%s)",
                    base_url,
                    max_pages,
                    depth,
                    self.concurrency,
                )
                sem = asyncio.Semaphore(max(1, self.concurrency))

                while queue and pages_analyzed < max_pages:
                    if await _cancelled():
                        return {
                            "rss_feeds": self.remove_duplicate_rss(all_rss_feeds),
                            "total_pages_analyzed": pages_analyzed,
                            "status": "cancelled",
                        }

                    # Batch parallele borne
                    batch = []
                    while queue and len(batch) < self.concurrency and pages_analyzed + len(batch) < max_pages:
                        url, rem = queue.popleft()
                        key = normalize_url(url) or url
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        batch.append((url, rem, key))

                    if not batch:
                        break

                    async def _process(item):
                        url, rem, key = item
                        async with sem:
                            if await _cancelled():
                                return None
                            final_url, html = await self._fetch_html(url)
                            if not html:
                                return None
                            final_key = normalize_url(final_url) or key
                            # Si redirect vers une URL deja vue, skip
                            if final_key != key and final_key in seen_keys:
                                return None
                            seen_keys.add(final_key)
                            self.visited_urls.add(final_key)

                            soup = BeautifulSoup(html, "html.parser")
                            title_tag = soup.find("title")
                            title = title_tag.get_text().strip() if title_tag else None
                            self._last_page_title = title

                            feeds = await self.extract_rss_from_html(final_url or url, html, soup)
                            hrefs = self._extract_internal_hrefs(base_url, final_url or url, soup) if rem > 0 else []
                            return {
                                "url": final_url or url,
                                "title": title,
                                "feeds": feeds,
                                "hrefs": hrefs,
                                "rem": rem,
                                "key": final_key,
                            }

                    results = await asyncio.gather(
                        *[_process(b) for b in batch],
                        return_exceptions=True,
                    )

                    for res in results:
                        if not res or isinstance(res, Exception):
                            if isinstance(res, Exception):
                                logger.error("Erreur page batch: %s", res)
                            continue
                        pages_analyzed += 1
                        all_rss_feeds.extend(res["feeds"] or [])
                        await self._emit_page(res["url"], res["title"], res["feeds"] or [])

                        if res["rem"] > 0 and pages_analyzed < max_pages:
                            for href in res["hrefs"]:
                                hk = normalize_url(href) or href
                                if hk not in seen_keys:
                                    queue.append((href, res["rem"] - 1))

                        if pages_analyzed >= max_pages:
                            break

                # Vrai total = pages vraiment analysees
                if self.on_plan:
                    try:
                        await self.on_plan(max(1, pages_analyzed))
                    except Exception:
                        pass

                unique = self.remove_duplicate_rss(all_rss_feeds)
                logger.info(
                    "Crawl BFS done %s pages=%s feeds=%s queue_left=%s",
                    base_url,
                    pages_analyzed,
                    len(unique),
                    len(queue),
                )
                return {
                    "rss_feeds": unique,
                    "total_pages_analyzed": pages_analyzed,
                    "status": "completed",
                }
        except Exception as exc:
            logger.error("Erreur crawl %s: %s", base_url, exc)
            return {
                "rss_feeds": self.remove_duplicate_rss(all_rss_feeds),
                "total_pages_analyzed": pages_analyzed,
                "status": "error",
                "error": str(exc),
            }
