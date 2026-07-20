"""Detection de langue (langdetect)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from text_analysis.base import error_result, ok_result, skip_result

_MIN_CHARS = 40


class LangDetectAnalyzer:
    name = "lang_detect"

    def is_available(self) -> bool:
        try:
            import langdetect  # noqa: F401
            return True
        except ImportError:
            return False

    def analyze(self, text: str, *, lang_hint: Optional[str] = None) -> Dict[str, Any]:
        if len(text.strip()) < _MIN_CHARS:
            return skip_result("texte trop court")
        try:
            from langdetect import DetectorFactory, detect_langs

            DetectorFactory.seed = 0
            scores = detect_langs(text)
            if not scores:
                return skip_result("langue indeterminee")
            best = scores[0]
            return ok_result(
                lang=best.lang,
                confidence=round(float(best.prob), 4),
                candidates=[
                    {"lang": s.lang, "confidence": round(float(s.prob), 4)}
                    for s in scores[:3]
                ],
            )
        except Exception as exc:
            return error_result(str(exc))
