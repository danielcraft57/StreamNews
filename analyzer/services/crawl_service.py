"""Service de crawl : orchestration de RSSAnalyzer avec concurrence bornee."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Awaitable, Callable, List, Optional

from models import CrawlResult, FeedRef
from rss_analyzer import RSSAnalyzer

logger = logging.getLogger(__name__)

PageHook = Callable[[str, Optional[str], List[dict]], Awaitable[None]]
FeedHook = Callable[[dict], Awaitable[None]]


class CrawlService:
    """
    Pipeline crawl:
      home -> discovery liens -> analyse pages en parallele (semaphore)
    """

    def __init__(
        self,
        concurrency: Optional[int] = None,
        on_page: Optional[PageHook] = None,
        on_feed: Optional[FeedHook] = None,
    ):
        self.concurrency = concurrency or int(os.getenv("CRAWL_CONCURRENCY", "3"))
        self.on_page = on_page
        self.on_feed = on_feed

    async def run(self, base_url: str, max_pages: int = 50, depth: int = 3) -> CrawlResult:
        analyzer = _HookedAnalyzer(self.on_page, self.on_feed)
        analyzer.concurrency = self.concurrency
        raw = await analyzer.analyze_site_concurrent(base_url, max_pages, depth)
        feeds = [FeedRef(**f) if not isinstance(f, FeedRef) else f for f in raw.get("rss_feeds", [])]
        return CrawlResult(
            status=raw.get("status", "completed"),
            rss_feeds=feeds,
            total_pages_analyzed=raw.get("total_pages_analyzed", 0),
            error=raw.get("error"),
        )


class _HookedAnalyzer(RSSAnalyzer):
    def __init__(self, on_page, on_feed):
        super().__init__()
        self.on_page = on_page
        self.on_feed = on_feed
        self.concurrency = 3
        self._seen_feeds = set()

    async def find_rss_feeds(self, url: str):
        feeds = await super().find_rss_feeds(url)
        title = getattr(self, "_last_page_title", None)
        if self.on_page:
            await self.on_page(url, title, feeds)
        if self.on_feed:
            for feed in feeds:
                key = feed.get("url")
                if key and key not in self._seen_feeds:
                    self._seen_feeds.add(key)
                    await self.on_feed(feed)
        return feeds

    async def analyze_site_concurrent(self, base_url: str, max_pages: int = 50, depth: int = 3) -> dict:
        self.visited_urls.clear()
        all_rss_feeds: List[dict] = []
        pages_analyzed = 0

        try:
            async with self:
                logger.info("Crawl concurrent %s (concurrency=%s)", base_url, self.concurrency)
                home_rss = await self.find_rss_feeds(base_url)
                all_rss_feeds.extend(home_rss)
                pages_analyzed = 1

                internal_urls = list(await self.get_internal_links(base_url, base_url, depth))
                targets = internal_urls[: max(0, max_pages - 1)]

                sem = asyncio.Semaphore(max(1, self.concurrency))

                async def _one(url: str):
                    async with sem:
                        try:
                            return await self.find_rss_feeds(url)
                        except Exception as exc:
                            logger.error("Erreur page %s: %s", url, exc)
                            return []

                if targets:
                    results = await asyncio.gather(*[_one(u) for u in targets])
                    for page_feeds in results:
                        all_rss_feeds.extend(page_feeds)
                        pages_analyzed += 1

                unique = self.remove_duplicate_rss(all_rss_feeds)
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
