"""Empreinte simhash pour deduplication proche."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from text_analysis.base import error_result, ok_result, skip_result

_MIN_CHARS = 60
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


class SimhashAnalyzer:
    name = "simhash"

    def is_available(self) -> bool:
        try:
            from simhash import Simhash  # noqa: F401
            return True
        except ImportError:
            return False

    def analyze(self, text: str, *, lang_hint: Optional[str] = None) -> Dict[str, Any]:
        normalized = text.lower().strip()
        if len(normalized) < _MIN_CHARS:
            return skip_result("texte trop court")
        tokens = _TOKEN_RE.findall(normalized)
        if len(tokens) < 8:
            return skip_result("pas assez de tokens")
        try:
            from simhash import Simhash

            value = Simhash(tokens).value
            return ok_result(
                value=str(value),
                hex=format(value, "016x"),
                token_count=len(tokens),
            )
        except Exception as exc:
            return error_result(str(exc))
