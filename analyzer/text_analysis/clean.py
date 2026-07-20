"""Nettoyage du corps article (liens, URLs) avant stockage ou analyse."""
from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup

_URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>\"')\]]+",
    re.IGNORECASE,
)
_MAILTO_RE = re.compile(r"mailto:[^\s<>\"')\]]+", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


def strip_urls_from_text(text: Optional[str]) -> str:
    """Retire les URLs et mailto du texte brut."""
    if not text:
        return ""
    cleaned = _MAILTO_RE.sub("", text)
    cleaned = _URL_RE.sub("", cleaned)
    return _WS_RE.sub(" ", cleaned).strip()


def strip_links_from_html(html: Optional[str]) -> str:
    """Retire les balises <a> en conservant le texte d'ancre."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for anchor in soup.find_all("a"):
        anchor.unwrap()
    body = soup.body
    if body is not None:
        return "".join(str(child) for child in body.children).strip()
    return str(soup).strip()


def html_to_plain_text(html: Optional[str]) -> str:
    """Extrait le texte visible depuis du HTML."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(" ", strip=True)


def prepare_text_for_analysis(
    content_text: Optional[str],
    content_html: Optional[str] = "",
) -> str:
    """Texte normalise pour les analyseurs (sans liens ni URLs)."""
    base = (content_text or "").strip()
    if not base and content_html:
        base = html_to_plain_text(content_html)
    return strip_urls_from_text(base)
