"""Extraction d'entites nommees (spaCy)."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from text_analysis.base import error_result, ok_result, skip_result

_MIN_CHARS = 80
_DEFAULT_MODEL = os.getenv("SPACY_MODEL", "fr_core_news_sm")
_MAX_ENTITIES = int(os.getenv("SPACY_MAX_ENTITIES", "25"))

_nlp_cache: Dict[str, Any] = {}


class SpacyNerAnalyzer:
    name = "ner_spacy"

    def is_available(self) -> bool:
        try:
            import spacy  # noqa: F401
            return True
        except ImportError:
            return False

    def _load_model(self, lang_hint: Optional[str]) -> Any:
        import spacy

        candidates: List[str] = []
        if lang_hint:
            candidates.append(f"{lang_hint[:2].lower()}_core_news_sm")
        if _DEFAULT_MODEL not in candidates:
            candidates.append(_DEFAULT_MODEL)
        candidates.extend(["fr_core_news_sm", "en_core_web_sm"])

        for model_name in candidates:
            if model_name in _nlp_cache:
                return _nlp_cache[model_name]
            try:
                nlp = spacy.load(model_name)
                _nlp_cache[model_name] = nlp
                return nlp
            except OSError:
                continue
        raise OSError(
            "Aucun modele spaCy installe. "
            f"Ex: python -m spacy download {_DEFAULT_MODEL}"
        )

    def analyze(self, text: str, *, lang_hint: Optional[str] = None) -> Dict[str, Any]:
        if len(text.strip()) < _MIN_CHARS:
            return skip_result("texte trop court")
        try:
            nlp = self._load_model(lang_hint)
            doc = nlp(text[:100_000])
            entities: List[Dict[str, str]] = []
            seen = set()
            for ent in doc.ents:
                label = ent.text.strip()
                if not label or label.lower() in seen:
                    continue
                seen.add(label.lower())
                entities.append({"text": label, "label": ent.label_})
                if len(entities) >= _MAX_ENTITIES:
                    break
            if not entities:
                return skip_result("aucune entite detectee")
            return ok_result(
                entities=entities,
                model=nlp.meta.get("name", _DEFAULT_MODEL),
            )
        except OSError as exc:
            return skip_result(str(exc))
        except Exception as exc:
            return error_result(str(exc))
