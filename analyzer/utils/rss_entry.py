"""Extraction media / meta depuis une entree feedparser."""
from __future__ import annotations

import re
from html import unescape
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup


def _abs_url(base: str, raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    url = urljoin(base, str(raw).strip())
    if url.startswith(("http://", "https://")):
        return url
    return None


def entry_link(entry: dict) -> str:
    return (entry.get("link") or entry.get("id") or "").strip()


def entry_summary(entry: dict, max_len: int = 4000) -> Optional[str]:
    raw = (
        entry.get("summary")
        or entry.get("description")
        or entry.get("content")
        or ""
    )
    if isinstance(raw, list):
        parts = []
        for block in raw:
            if isinstance(block, dict):
                parts.append(block.get("value") or "")
            else:
                parts.append(str(block))
        raw = "\n".join(parts)
    if not raw:
        for key in ("content", "summary_detail"):
            detail = entry.get(key)
            if isinstance(detail, dict) and detail.get("value"):
                raw = detail["value"]
                break
    text = unescape(str(raw)).strip()
    if not text:
        return None
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "lxml").get_text(" ", strip=True)
    if len(text) > max_len:
        text = text[:max_len] + "…"
    return text or None


def entry_author(entry: dict) -> Optional[str]:
    author = entry.get("author")
    if author:
        return str(author).strip() or None
    for tag in entry.get("tags") or []:
        if getattr(tag, "term", None) and getattr(tag, "scheme", "") == "urn:ebxml:names:author":
            return str(tag.term).strip()
    creator = entry.get("author_detail") or {}
    if isinstance(creator, dict) and creator.get("name"):
        return str(creator["name"]).strip()
    return None


def entry_keywords(entry: dict) -> List[str]:
    out: List[str] = []
    seen = set()
    for tag in entry.get("tags") or []:
        term = getattr(tag, "term", None) or (tag.get("term") if isinstance(tag, dict) else None)
        if not term:
            continue
        label = str(term).strip()
        key = label.lower()
        if label and key not in seen:
            seen.add(key)
            out.append(label)
    for raw in (entry.get("category"),):
        if raw and str(raw).strip():
            label = str(raw).strip()
            key = label.lower()
            if key not in seen:
                seen.add(key)
                out.append(label)
    return out[:20]


def entry_images(entry: dict, limit: int = 8) -> List[Dict[str, str]]:
    """Images RSS : media:content, thumbnail, enclosures, img dans le resume."""
    base = entry_link(entry) or ""
    out: List[Dict[str, str]] = []
    seen = set()

    def add(url: Optional[str], alt: str = "", source: str = "rss") -> None:
        abs_url = _abs_url(base, url)
        if not abs_url or abs_url in seen:
            return
        seen.add(abs_url)
        out.append({"url": abs_url, "alt": (alt or "")[:300], "source": source})

    for media in entry.get("media_content") or []:
        if not isinstance(media, dict):
            continue
        medium = (media.get("medium") or "").lower()
        mtype = (media.get("type") or "").lower()
        if medium == "image" or mtype.startswith("image/"):
            add(media.get("url"), source="rss-media")

    for thumb in entry.get("media_thumbnail") or []:
        if isinstance(thumb, dict):
            add(thumb.get("url"), source="rss-thumb")

    for enc in entry.get("enclosures") or []:
        if not isinstance(enc, dict):
            continue
        if (enc.get("type") or "").lower().startswith("image/"):
            add(enc.get("href") or enc.get("url"), source="rss-enclosure")

    summary_html = entry.get("summary") or entry.get("description") or ""
    if summary_html and "<img" in str(summary_html).lower():
        soup = BeautifulSoup(str(summary_html), "lxml")
        for img in soup.find_all("img"):
            add(img.get("src"), alt=img.get("alt") or "", source="rss-summary")

    return out[:limit]


def entry_article_meta(entry: dict) -> Dict[str, Any]:
    meta: Dict[str, Any] = {"sources": ["rss"]}
    keywords = entry_keywords(entry)
    if keywords:
        meta["keywords"] = keywords
    if entry.get("source") and isinstance(entry["source"], dict):
        title = entry["source"].get("title")
        if title:
            meta["feed_title"] = str(title).strip()
    return meta
