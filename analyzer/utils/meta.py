"""Extraction titre / favicon / meta d'une page HTML (home)."""
from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from utils.urls import normalize_url


def _meta_content(soup: BeautifulSoup, *keys: str) -> Optional[str]:
    for key in keys:
        tag = soup.find("meta", attrs={"name": key}) or soup.find(
            "meta", attrs={"property": key}
        )
        if tag and tag.get("content"):
            val = str(tag["content"]).strip()
            if val:
                return val
    return None


def _favicon_href(soup: BeautifulSoup, page_url: str) -> Optional[str]:
    candidates = []
    for link in soup.find_all("link"):
        rel = link.get("rel") or []
        if isinstance(rel, str):
            rel = [rel]
        rel_l = " ".join(r.lower() for r in rel)
        href = link.get("href")
        if not href:
            continue
        if any(x in rel_l for x in ("icon", "shortcut icon", "apple-touch-icon")):
            candidates.append((rel_l, href, link.get("sizes") or ""))

    def score(item):
        rel_l, href, sizes = item
        s = 0
        if "apple-touch-icon" in rel_l:
            s += 5
        if "shortcut" in rel_l:
            s += 3
        if "icon" in rel_l:
            s += 2
        if "32x32" in sizes:
            s += 2
        if href.lower().endswith(".svg"):
            s += 1
        return -s

    candidates.sort(key=score)
    if candidates:
        return urljoin(page_url, candidates[0][1])

    # Fallback classique
    return urljoin(page_url, "/favicon.ico")


def extract_site_meta(page_url: str, html: str, soup: Optional[BeautifulSoup] = None) -> Dict[str, Any]:
    """Retourne title, favicon_url, description et quelques Open Graph."""
    if soup is None:
        soup = BeautifulSoup(html or "", "html.parser")

    title = None
    if soup.title and soup.title.string:
        title = soup.title.get_text(strip=True)
    title = _meta_content(soup, "og:title", "twitter:title") or title

    description = _meta_content(
        soup, "description", "og:description", "twitter:description"
    )
    og_image = _meta_content(soup, "og:image", "twitter:image")
    og_site_name = _meta_content(soup, "og:site_name")
    theme_color = _meta_content(soup, "theme-color")
    favicon = _favicon_href(soup, page_url)

    if og_image:
        og_image = urljoin(page_url, og_image)
    if favicon:
        favicon = normalize_url(favicon) or favicon

    return {
        "title": (title or "")[:500] or None,
        "favicon_url": (favicon or "")[:1000] or None,
        "description": (description or "")[:2000] or None,
        "og_image": (og_image or "")[:1000] or None,
        "og_site_name": (og_site_name or "")[:300] or None,
        "theme_color": (theme_color or "")[:32] or None,
    }
