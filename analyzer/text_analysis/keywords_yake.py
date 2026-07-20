"""Extraction de mots-cles (YAKE)."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from text_analysis.base import error_result, ok_result, skip_result

_MIN_CHARS = 80
_DEFAULT_LANG = os.getenv("YAKE_LANG", "fr")
_TOP_N = int(os.getenv("YAKE_TOP_N", "12"))


class YakeKeywordsAnalyzer:
    name = "keywords_yake"

    def is_available(self) -> bool:
        try:
            import yake  # noqa: F401
            return True
        except ImportError:
            return False

    def analyze(self, text: str, *, lang_hint: Optional[str] = None) -> Dict[str, Any]:
        if len(text.strip()) < _MIN_CHARS:
            return skip_result("texte trop court")
        try:
            import yake

            lang = (lang_hint or _DEFAULT_LANG or "fr")[:2].lower()
            extractor = yake.KeywordExtractor(
                lan=lang,
                n=3,
                dedupLim=0.9,
                top=_TOP_N,
                features=None,
            )
            raw: List[tuple] = extractor.extract_keywords(text)
            keywords = [kw for kw, _score in raw if kw]
            if not keywords:
                return skip_result("aucun mot-cle extrait")
            return ok_result(keywords=keywords[:_TOP_N], lang=lang)
        except Exception as exc:
            return error_result(str(exc))
