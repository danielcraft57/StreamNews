"""Enrichissement d'un article : fetch HTML + structured data + corps."""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import aiohttp
import bleach
import trafilatura
from bs4 import BeautifulSoup

from logging_config import get_logger
from text_analysis.clean import strip_links_from_html, strip_urls_from_text
from utils.image_urls import (
    build_images_list,
    pick_primary_image,
    strip_primary_image_from_html,
)

logger = get_logger(__name__)

FETCH_TIMEOUT = float(os.getenv("ENRICH_FETCH_TIMEOUT", "15"))
USER_AGENT = os.getenv(
    "ENRICH_USER_AGENT",
    "StreamNews/1.0 (+https://github.com/streamnews; RSS analyzer)",
)

_ARTICLE_TYPES = {
    "article",
    "newsarticle",
    "blogposting",
    "reportagenewsarticle",
    "techarticle",
    "scholarlyarticle",
}

_ALLOWED_TAGS = [
    "p", "br", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "strong", "em", "b", "i",
    "blockquote", "img", "figure", "figcaption",
    "span", "div", "pre", "code", "hr", "table",
    "thead", "tbody", "tr", "th", "td",
]
_ALLOWED_ATTRS = {
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "title"],
    "*": ["class"],
}


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _first_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s or None
    if isinstance(value, dict):
        for key in ("name", "value", "@value", "text"):
            if key in value:
                return _first_str(value[key])
        return None
    if isinstance(value, list):
        for item in value:
            s = _first_str(item)
            if s:
                return s
    return str(value).strip() or None


def _type_names(obj: Dict) -> List[str]:
    raw = obj.get("@type") or obj.get("type")
    names = []
    for item in _as_list(raw):
        if isinstance(item, str):
            names.append(item.split("/")[-1].lower())
        elif isinstance(item, dict):
            t = item.get("@id") or item.get("name")
            if t:
                names.append(str(t).split("/")[-1].lower())
    return names


def _is_article_ld(obj: Dict) -> bool:
    return bool(set(_type_names(obj)) & _ARTICLE_TYPES)


def _walk_jsonld(data: Any) -> List[Dict]:
    found: List[Dict] = []
    if isinstance(data, dict):
        if "@graph" in data:
            for node in _as_list(data["@graph"]):
                found.extend(_walk_jsonld(node))
        else:
            found.append(data)
            for v in data.values():
                if isinstance(v, (dict, list)):
                    found.extend(_walk_jsonld(v))
    elif isinstance(data, list):
        for item in data:
            found.extend(_walk_jsonld(item))
    return found


def _image_urls(value: Any, base_url: str) -> List[str]:
    urls: List[str] = []
    for item in _as_list(value):
        raw = None
        if isinstance(item, str):
            raw = item
        elif isinstance(item, dict):
            raw = item.get("url") or item.get("contentUrl") or item.get("@id")
        if not raw:
            continue
        abs_url = urljoin(base_url, str(raw).strip())
        if abs_url.startswith(("http://", "https://")):
            urls.append(abs_url)
    return urls


def _author_name(value: Any) -> Optional[str]:
    parts = []
    for item in _as_list(value):
        if isinstance(item, dict):
            name = _first_str(item.get("name")) or _first_str(item)
        else:
            name = _first_str(item)
        if name:
            parts.append(name)
    return ", ".join(parts) if parts else None


def _base_url(soup: BeautifulSoup, page_url: str) -> str:
    base = soup.find("base", href=True)
    if base and base.get("href"):
        return urljoin(page_url, base["href"].strip())
    return page_url


def _parse_jsonld_blocks(soup: BeautifulSoup) -> List[Any]:
    blocks = []
    for tag in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = tag.string or tag.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            blocks.append(json.loads(raw))
        except json.JSONDecodeError:
            try:
                blocks.append(json.loads(f"[{raw}]"))
            except json.JSONDecodeError:
                continue
    return blocks


def _pick_jsonld_article(soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    for block in _parse_jsonld_blocks(soup):
        for node in _walk_jsonld(block):
            if not isinstance(node, dict) or not _is_article_ld(node):
                continue
            meta["source"] = "json-ld"
            meta["schema_type"] = _type_names(node)[0] if _type_names(node) else "Article"
            if node.get("headline"):
                meta["title"] = _first_str(node.get("headline"))
            elif node.get("name"):
                meta["title"] = _first_str(node.get("name"))
            if node.get("description"):
                meta["description"] = _first_str(node.get("description"))
            if node.get("datePublished"):
                meta["date_published"] = _first_str(node.get("datePublished"))
            if node.get("dateModified"):
                meta["date_modified"] = _first_str(node.get("dateModified"))
            author = _author_name(node.get("author"))
            if author:
                meta["author"] = author
            images = _image_urls(node.get("image"), base_url)
            if images:
                meta["images"] = images
            if node.get("articleBody"):
                meta["article_body"] = _first_str(node.get("articleBody"))
            kw = node.get("keywords")
            if kw:
                if isinstance(kw, str):
                    meta["keywords"] = [k.strip() for k in kw.split(",") if k.strip()]
                else:
                    meta["keywords"] = [_first_str(k) for k in _as_list(kw) if _first_str(k)]
            return meta
    return meta


def _pick_rdfa(soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
    """RDFa : property og:* / schema:* et typeof Article."""
    meta: Dict[str, Any] = {}
    prop_map = {
        "og:title": "title",
        "og:description": "description",
        "og:image": "images",
        "twitter:title": "title",
        "twitter:description": "description",
        "twitter:image": "images",
        "schema:headline": "title",
        "schema:name": "title",
        "schema:description": "description",
        "schema:datePublished": "date_published",
        "schema:dateModified": "date_modified",
        "schema:author": "author",
        "schema:image": "images",
    }
    for el in soup.find_all(attrs={"property": True}):
        prop = (el.get("property") or "").strip().lower()
        key = prop_map.get(prop)
        if not key:
            continue
        val = _itemprop_text(el)
        if not val:
            continue
        if key == "images":
            urls = _image_urls(val, base_url)
            if urls:
                meta.setdefault("images", []).extend(urls)
        elif key == "author" and "author" not in meta:
            meta["author"] = val
        elif key not in meta:
            meta[key] = val

    for scope in soup.find_all(attrs={"typeof": True}):
        typeof = (scope.get("typeof") or "").lower()
        type_name = typeof.rsplit(":", 1)[-1]
        if type_name not in _ARTICLE_TYPES:
            continue
        meta.setdefault("schema_type", type_name)
        for prop, key in (
            ("headline", "title"), ("name", "title"), ("description", "description"),
            ("datePublished", "date_published"), ("dateModified", "date_modified"),
            ("image", "images"),
        ):
            el = scope.find(attrs={"property": re.compile(rf"(schema:)?{prop}$", re.I)})
            if not el:
                continue
            val = _itemprop_text(el)
            if not val:
                continue
            if key == "images":
                urls = _image_urls(val, base_url)
                if urls:
                    meta.setdefault("images", []).extend(urls)
            elif key not in meta:
                meta[key] = val
        author_el = scope.find(attrs={"property": re.compile(r"(schema:)?author$", re.I)})
        if author_el and "author" not in meta:
            name_el = author_el.find(attrs={"property": re.compile(r"(schema:)?name$", re.I)})
            meta["author"] = _itemprop_text(name_el or author_el)

    if meta:
        meta["source"] = "rdfa"
    return meta


def _pick_dublin_core(soup: BeautifulSoup) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    dc_map = {
        "dc.title": "title",
        "dcterms.title": "title",
        "dc.description": "description",
        "dcterms.abstract": "description",
        "dc.creator": "author",
        "dcterms.created": "date_published",
        "dcterms.modified": "date_modified",
        "dc.subject": "keywords",
    }
    for tag in soup.find_all("meta"):
        name = (tag.get("name") or tag.get("property") or "").strip().lower()
        key = dc_map.get(name)
        content = (tag.get("content") or "").strip()
        if not key or not content:
            continue
        if key == "keywords":
            meta.setdefault("keywords", []).append(content)
        elif key not in meta:
            meta[key] = content
    if meta:
        meta["source"] = "dublin-core"
    return meta


def _pick_page_links(soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    canonical = soup.find("link", rel=lambda v: v and "canonical" in str(v).lower())
    if canonical and canonical.get("href"):
        meta["canonical_url"] = urljoin(base_url, canonical["href"].strip())
    icon = (
        soup.find("link", rel=lambda v: v and "icon" in str(v).lower() and "apple" not in str(v).lower())
        or soup.find("link", rel="shortcut icon")
    )
    if icon and icon.get("href"):
        meta["favicon_url"] = urljoin(base_url, icon["href"].strip())
    keywords = _meta_content(soup, "keywords", "news_keywords")
    if keywords:
        meta["keywords"] = [k.strip() for k in keywords.split(",") if k.strip()]
    if meta:
        meta["source"] = "page-meta"
    return meta


def _reading_time_minutes(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    words = len(re.findall(r"\w+", text, flags=re.UNICODE))
    if words < 40:
        return None
    return max(1, round(words / 200))


def _meta_content(soup: BeautifulSoup, *keys: str) -> Optional[str]:
    for key in keys:
        tag = soup.find("meta", attrs={"property": key}) or soup.find(
            "meta", attrs={"name": key}
        )
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def _pick_opengraph(soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    title = _meta_content(soup, "og:title", "twitter:title")
    if title:
        meta["title"] = title
    desc = _meta_content(soup, "og:description", "twitter:description", "description")
    if desc:
        meta["description"] = desc
    img = _meta_content(soup, "og:image", "twitter:image")
    if img:
        urls = _image_urls(img, base_url)
        if urls:
            meta["images"] = urls
    og_type = _meta_content(soup, "og:type")
    if og_type:
        meta["og_type"] = og_type
    if meta:
        meta["source"] = "opengraph"
    return meta


def _itemprop_text(el) -> Optional[str]:
    if el.has_attr("content"):
        return el["content"].strip() or None
    if el.name == "meta" and el.get("content"):
        return el["content"].strip() or None
    if el.name == "img" and el.get("src"):
        return el["src"].strip() or None
    if el.name == "time" and el.get("datetime"):
        return el["datetime"].strip() or None
    text = el.get_text(" ", strip=True)
    return text or None


def _pick_microdata(soup: BeautifulSoup, base_url: str) -> Dict[str, Any]:
    """Microdata HTML5 basique (itemscope Article / NewsArticle)."""
    meta: Dict[str, Any] = {}
    for scope in soup.find_all(attrs={"itemscope": True}):
        itemtype = (scope.get("itemtype") or "").lower()
        type_name = itemtype.rstrip("/").split("/")[-1]
        if type_name not in _ARTICLE_TYPES:
            continue
        meta["source"] = "microdata"
        meta["schema_type"] = type_name

        def prop(name: str) -> Optional[str]:
            el = scope.find(attrs={"itemprop": name})
            if not el:
                return None
            return _itemprop_text(el)

        title = prop("headline") or prop("name")
        if title:
            meta["title"] = title
        desc = prop("description")
        if desc:
            meta["description"] = desc
        date_p = prop("datePublished")
        if date_p:
            meta["date_published"] = date_p
        author_el = scope.find(attrs={"itemprop": "author"})
        if author_el:
            author = _itemprop_text(author_el.find(attrs={"itemprop": "name"}) or author_el)
            if author:
                meta["author"] = author
        img_el = scope.find(attrs={"itemprop": "image"})
        if img_el:
            raw = img_el.get("content") or img_el.get("src") or _itemprop_text(img_el)
            urls = _image_urls(raw, base_url)
            if urls:
                meta["images"] = urls
        return meta
    return meta


def _merge_meta(*parts: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"sources": []}
    images: List[str] = []
    keywords: List[str] = []
    for part in parts:
        if not part:
            continue
        src = part.get("source")
        if src:
            out["sources"].append(src)
        for key in (
            "title", "description", "author", "date_published",
            "date_modified", "schema_type", "og_type", "article_body",
            "canonical_url", "favicon_url",
        ):
            if key not in out and part.get(key):
                out[key] = part[key]
        for kw in part.get("keywords") or []:
            label = str(kw).strip()
            if label and label.lower() not in {k.lower() for k in keywords}:
                keywords.append(label)
        for url in part.get("images") or []:
            if url not in images:
                images.append(url)
    if images:
        out["images"] = images
    if keywords:
        out["keywords"] = keywords[:30]
    return out


def _sanitize_html(html: Optional[str]) -> str:
    if not html:
        return ""
    cleaned = bleach.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        protocols=["http", "https", "mailto"],
        strip=True,
    )
    return strip_links_from_html(cleaned)


def _images_from_html(html: str, base_url: str, limit: int = 12) -> List[Dict[str, str]]:
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    out: List[Dict[str, str]] = []
    seen = set()
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if not src:
            continue
        abs_url = urljoin(base_url, src.strip())
        if not abs_url.startswith(("http://", "https://")):
            continue
        if abs_url in seen:
            continue
        seen.add(abs_url)
        out.append({
            "url": abs_url,
            "alt": (img.get("alt") or "")[:300],
            "source": "content",
        })
        if len(out) >= limit:
            break
    return out


def extract_from_html(html: str, page_url: str) -> Dict[str, Any]:
    """Parse HTML -> contenu + meta + images (testable, sync)."""
    if not html or not html.strip():
        return {
            "title": None,
            "author": None,
            "content_html": "",
            "content_text": "",
            "images": [],
            "article_meta": {},
        }

    soup = BeautifulSoup(html, "lxml")
    base_url = _base_url(soup, page_url)

    ld = _pick_jsonld_article(soup, base_url)
    og = _pick_opengraph(soup, base_url)
    md = _pick_microdata(soup, base_url)
    rdfa = _pick_rdfa(soup, base_url)
    dc = _pick_dublin_core(soup)
    page = _pick_page_links(soup, base_url)
    merged = _merge_meta(ld, og, md, rdfa, dc, page)

    content_html = ""
    content_text = ""

    try:
        downloaded = trafilatura.extract(
            html,
            url=page_url,
            include_comments=False,
            include_tables=True,
            include_images=True,
            include_links=False,
            output_format="html",
            favor_recall=True,
        )
        if downloaded:
            content_html = _sanitize_html(downloaded)
    except Exception as exc:
        logger.warning("trafilatura html failed for %s: %s", page_url, exc)

    try:
        text = trafilatura.extract(
            html,
            url=page_url,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
        )
        if text:
            content_text = strip_urls_from_text(text.strip())
    except Exception as exc:
        logger.warning("trafilatura text failed for %s: %s", page_url, exc)

    if not content_text and merged.get("article_body"):
        content_text = strip_urls_from_text(str(merged["article_body"]).strip())
        if not content_html:
            content_html = _sanitize_html(
                "<p>" + bleach.clean(content_text, tags=[], strip=True) + "</p>"
            )

    if not content_html and content_text:
        paras = [p.strip() for p in content_text.split("\n") if p.strip()]
        content_html = _sanitize_html(
            "".join(f"<p>{bleach.clean(p, tags=[], strip=True)}</p>" for p in paras)
        )

    images: List[Dict[str, str]] = []
    seen = set()
    meta_urls: List[str] = []
    for url in merged.get("images") or []:
        if url in seen:
            continue
        seen.add(url)
        meta_urls.append(url)

    content_imgs = _images_from_html(content_html, base_url)
    og_img = _meta_content(soup, "og:image")
    tw_img = _meta_content(soup, "twitter:image")
    primary = pick_primary_image(
        og_url=og_img,
        twitter_url=tw_img,
        meta_urls=meta_urls,
        content_images=content_imgs,
        base_url=base_url,
    )
    images = build_images_list(primary, meta_urls, content_imgs)

    if primary and content_html:
        content_html = strip_primary_image_from_html(content_html, primary, base_url)

    article_meta = {
        k: v
        for k, v in merged.items()
        if k not in ("images", "article_body") and v is not None
    }
    article_meta["page_url"] = page_url
    if urlparse(page_url).netloc:
        article_meta["domain"] = urlparse(page_url).netloc.lower()
    if primary and primary.get("url"):
        article_meta["primary_image"] = primary["url"]
    rt = _reading_time_minutes(content_text or merged.get("article_body"))
    if rt:
        article_meta["reading_time_minutes"] = rt

    return {
        "title": merged.get("title"),
        "author": merged.get("author"),
        "content_html": content_html,
        "content_text": content_text,
        "images": images[:20],
        "article_meta": article_meta,
    }


async def fetch_html(url: str) -> str:
    timeout = aiohttp.ClientTimeout(total=FETCH_TIMEOUT)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr,en;q=0.8",
    }
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(url, allow_redirects=True) as resp:
            resp.raise_for_status()
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "html" not in ctype and "xml" not in ctype and ctype:
                if not ctype.startswith("text/"):
                    raise ValueError(f"Content-Type non HTML: {ctype}")
            return await resp.text(errors="replace")


async def enrich_article_url(url: str) -> Dict[str, Any]:
    """Fetch + extract. Leve en cas d'erreur reseau / HTTP."""
    html = await fetch_html(url)
    result = extract_from_html(html, url)
    if (
        not result.get("content_html")
        and not result.get("content_text")
        and not result.get("images")
        and not result.get("article_meta")
    ):
        raise ValueError("Aucun contenu extractible")
    return result
