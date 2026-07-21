"""Detection / dedup des images article (hero, OG, corps)."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse


def image_stem(url: str) -> str:
    if not url:
        return ""
    try:
        name = urlparse(url).path.split("/")[-1].lower()
    except Exception:
        name = str(url).split("/")[-1].lower()
    stem = re.sub(r"\.[a-z0-9]{2,5}$", "", name)
    return re.sub(r"-\d+x\d+$", "", stem)


def images_match(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a.rstrip("/") == b.rstrip("/"):
        return True
    sa, sb = image_stem(a), image_stem(b)
    return bool(sa and sb and sa == sb and len(sa) > 4)


def abs_image_url(raw: Optional[str], base_url: str) -> Optional[str]:
    if not raw:
        return None
    url = urljoin(base_url, str(raw).strip())
    if url.startswith(("http://", "https://")):
        return url
    return None


def pick_primary_image(
    *,
    og_url: Optional[str],
    twitter_url: Optional[str],
    meta_urls: List[str],
    content_images: List[Dict[str, str]],
    base_url: str,
) -> Optional[Dict[str, Any]]:
    """Image principale : og > twitter > meta JSON-LD/OG merge > 1re du corps."""
    candidates: List[Dict[str, str]] = []

    for raw, source in ((og_url, "og"), (twitter_url, "twitter")):
        url = abs_image_url(raw, base_url)
        if url:
            candidates.append({"url": url, "alt": "", "source": source})

    for url in meta_urls or []:
        if url and not any(images_match(url, c["url"]) for c in candidates):
            candidates.append({"url": url, "alt": "", "source": "meta"})

    if not candidates:
        if content_images:
            first = dict(content_images[0])
            first["primary"] = True
            return first
        return None

    primary = dict(candidates[0])
    for cimg in content_images:
        if images_match(cimg.get("url", ""), primary["url"]):
            primary["url"] = cimg["url"]
            primary["alt"] = cimg.get("alt") or primary.get("alt") or ""
            if primary.get("source") == "meta":
                primary["source"] = cimg.get("source") or "content"
            break

    primary["primary"] = True
    return primary


def build_images_list(
    primary: Optional[Dict[str, Any]],
    meta_urls: List[str],
    content_images: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def add(url: str, alt: str = "", source: str = "", is_primary: bool = False) -> None:
        if not url or url in seen:
            return
        seen.add(url)
        item: Dict[str, Any] = {"url": url, "alt": (alt or "")[:300], "source": source}
        if is_primary:
            item["primary"] = True
        out.append(item)

    if primary and primary.get("url"):
        add(
            primary["url"],
            primary.get("alt") or "",
            primary.get("source") or "meta",
            True,
        )

    for url in meta_urls or []:
        if primary and images_match(url, primary.get("url", "")):
            continue
        add(url, "", "meta")

    for img in content_images or []:
        url = img.get("url") or ""
        if primary and images_match(url, primary.get("url", "")):
            continue
        add(url, img.get("alt") or "", img.get("source") or "content")

    return out[:20]


def strip_primary_image_from_html(
    html: str,
    primary: Optional[Dict[str, Any]],
    base_url: str,
) -> str:
    """Retire l'image principale du corps HTML (evite doublon hero)."""
    if not html or not primary or not primary.get("url"):
        return html

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return html

    soup = BeautifulSoup(html, "lxml")
    primary_url = primary["url"]
    primary_stem = image_stem(primary_url)
    refs = [primary_url]
    if primary.get("url") != primary_url:
        refs.append(primary.get("url"))

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        abs_src = abs_image_url(src, base_url) or src
        strip = any(images_match(abs_src, ref) for ref in refs if ref)
        if not strip and primary_stem and image_stem(abs_src) == primary_stem:
            strip = True
        if not strip:
            continue

        figure = img.find_parent("figure") or img.find_parent("picture")
        if figure:
            figure.decompose()
            continue
        parent = img.parent
        if parent and parent.name == "p":
            img.decompose()
            if parent.get_text(strip=True):
                continue
            parent.decompose()
        else:
            img.decompose()

    body = soup.body
    if body is not None:
        return "".join(str(child) for child in body.children).strip()
    return str(soup).strip()
