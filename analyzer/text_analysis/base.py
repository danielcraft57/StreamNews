"""Contrat commun des analyseurs de texte."""
from __future__ import annotations

from typing import Any, Dict, Optional, Protocol


class TextAnalyzer(Protocol):
    """Chaque outil est independant et renvoie son propre bloc de resultat."""

    name: str

    def is_available(self) -> bool:
        ...

    def analyze(self, text: str, *, lang_hint: Optional[str] = None) -> Dict[str, Any]:
        ...


def ok_result(**fields: Any) -> Dict[str, Any]:
    return {"status": "ok", **fields}


def skip_result(reason: str) -> Dict[str, Any]:
    return {"status": "skipped", "reason": reason}


def error_result(error: str) -> Dict[str, Any]:
    return {"status": "error", "error": error[:500]}
