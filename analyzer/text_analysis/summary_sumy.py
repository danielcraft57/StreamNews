"""Resume extractif (sumy TextRank)."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from text_analysis.base import error_result, ok_result, skip_result

_MIN_CHARS = 200
_SENTENCES = int(os.getenv("SUMY_SENTENCES", "3"))


def _ensure_nltk_data() -> None:
    import nltk

    for resource in ("punkt", "punkt_tab"):
        try:
            nltk.data.find(f"tokenizers/{resource}")
        except LookupError:
            try:
                nltk.download(resource, quiet=True)
            except Exception:
                pass


class SumySummaryAnalyzer:
    name = "summary_sumy"

    def is_available(self) -> bool:
        try:
            import sumy  # noqa: F401
            return True
        except ImportError:
            return False

    def analyze(self, text: str, *, lang_hint: Optional[str] = None) -> Dict[str, Any]:
        if len(text.strip()) < _MIN_CHARS:
            return skip_result("texte trop court")
        try:
            from sumy.nlp.tokenizers import Tokenizer
            from sumy.parsers.plaintext import PlaintextParser
            from sumy.summarizers.text_rank import TextRankSummarizer

            _ensure_nltk_data()
            parser = PlaintextParser.from_string(text, Tokenizer("french"))
            summarizer = TextRankSummarizer()
            sentences = list(summarizer(parser.document, _SENTENCES))
            if not sentences:
                return skip_result("resume vide")
            parts = [str(s).strip() for s in sentences if str(s).strip()]
            summary = " ".join(parts).strip()
            return ok_result(
                summary=summary,
                sentences=parts,
                sentence_count=len(parts),
                method="text_rank",
            )
        except Exception as exc:
            return error_result(str(exc))
