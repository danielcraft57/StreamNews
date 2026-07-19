"""Normalisation d'URLs pour dedup feeds / articles (http vs https, trailing slash, etc.)."""
from __future__ import annotations

from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TRACKING_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def normalize_url(url: Optional[str]) -> str:
    """Canonise une URL pour comparaison / stockage."""
    if not url:
        return ""
    raw = str(url).strip()
    if not raw:
        return ""

    try:
        parsed = urlparse(raw)
    except Exception:
        return raw.rstrip("/")

    scheme = (parsed.scheme or "https").lower()
    if scheme == "http":
        scheme = "https"

    netloc = (parsed.netloc or "").lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    path = parsed.path or ""
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_KEYS
    ]
    query = urlencode(query_pairs, doseq=True)

    return urlunparse((scheme, netloc, path, "", query, ""))


def normalize_identifier(value: Optional[str]) -> Optional[str]:
    """Normalise un guid / id d'article (souvent une URL WordPress ?p=)."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    lower = raw.lower()
    if lower.startswith("http://") or lower.startswith("https://"):
        return normalize_url(raw) or None
    return raw


def article_dedupe_key(link: str, guid: Optional[str] = None) -> str:
    """Cle unique stable : prefer guid normalise, sinon lien normalise."""
    g = normalize_identifier(guid)
    if g:
        return f"g:{g}"
    return f"l:{normalize_url(link)}"
