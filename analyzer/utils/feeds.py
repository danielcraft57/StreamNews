"""Dedup de flux RSS/Atom au contenu equivalent (meme articles, formats differents)."""
from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional, Set, Tuple

import feedparser

from logging_config import get_logger
from utils.urls import normalize_identifier, normalize_url

logger = get_logger(__name__)

# Jaccard : 85% d'articles en commun = meme flux (RSS vs Atom typique)
DEFAULT_OVERLAP = 0.85
FINGERPRINT_ENTRIES = 25


def entry_ids_from_parsed(parsed, limit: int = FINGERPRINT_ENTRIES) -> Set[str]:
    ids: Set[str] = set()
    for entry in (parsed.entries or [])[:limit]:
        key = normalize_identifier(entry.get("id") or entry.get("guid"))
        if not key:
            key = normalize_url(entry.get("link") or "")
        if key:
            ids.add(key)
    return ids


def fingerprint_feed(feed_url: str, limit: int = FINGERPRINT_ENTRIES) -> Set[str]:
    """Ensemble d'identifiants d'articles pour comparer deux flux."""
    url = normalize_url(feed_url) or feed_url
    if not url:
        return set()
    try:
        parsed = feedparser.parse(url)
    except Exception as exc:
        logger.warning("fingerprint failed %s: %s", url, exc)
        return set()
    return entry_ids_from_parsed(parsed, limit=limit)


def overlap_ratio(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return (inter / union) if union else 0.0


def _feed_rank(feed: Dict) -> Tuple:
    """Plus petit = mieux. Prefer RSS a Atom, URL courte, pas comments."""
    url = (feed.get("url") or "").lower()
    typ = (feed.get("type") or "").lower()
    title = (feed.get("title") or "").lower()
    is_atom = "atom" in typ or "/atom" in url or "atom feed" in title
    is_comments = (
        "comment" in title
        or "comment" in url
        or "/comments/" in url
        or "sample-page/feed" in url
    )
    return (
        1 if is_comments else 0,
        1 if is_atom else 0,
        len(url),
        url,
    )


def collapse_equivalent_feeds(
    feeds: Iterable[Dict],
    overlap_threshold: float = DEFAULT_OVERLAP,
    fingerprints: Optional[Dict[str, Set[str]]] = None,
) -> List[Dict]:
    """
    Garde un seul feed par groupe de contenu equivalent (ex: RSS + Atom).

    fingerprints: cache optionnel {url_normalisee: set(ids)} pour eviter
    de re-fetcher si deja parse.
    """
    cache = fingerprints if fingerprints is not None else {}
    candidates: List[Dict] = []
    seen_url: Set[str] = set()

    for feed in feeds or []:
        raw = (feed.get("url") or "").strip()
        if not raw:
            continue
        url = normalize_url(raw) or raw
        if url in seen_url:
            continue
        seen_url.add(url)
        item = dict(feed)
        item["url"] = url
        candidates.append(item)

    # Fingerprints
    fps: List[Optional[Set[str]]] = []
    for item in candidates:
        url = item["url"]
        if url not in cache:
            cache[url] = fingerprint_feed(url)
        fps.append(cache[url] or None)

    keep = [True] * len(candidates)
    for i in range(len(candidates)):
        if not keep[i]:
            continue
        fi = fps[i]
        if not fi:
            continue
        for j in range(i + 1, len(candidates)):
            if not keep[j]:
                continue
            fj = fps[j]
            if not fj:
                continue
            if overlap_ratio(fi, fj) >= overlap_threshold:
                # Garde le mieux classe
                if _feed_rank(candidates[i]) <= _feed_rank(candidates[j]):
                    keep[j] = False
                    logger.info(
                        "Feed equivalent ignore: %s ~= %s",
                        candidates[j]["url"],
                        candidates[i]["url"],
                    )
                else:
                    keep[i] = False
                    logger.info(
                        "Feed equivalent ignore: %s ~= %s",
                        candidates[i]["url"],
                        candidates[j]["url"],
                    )
                    break

    return [c for c, k in zip(candidates, keep) if k]
