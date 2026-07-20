"""Extraction d'entites nommees (spaCy) enrichie."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Set, Tuple

from text_analysis.base import error_result, ok_result, skip_result

_MIN_CHARS = 80
_DEFAULT_MODEL = os.getenv("SPACY_MODEL", "fr_core_news_sm")
_MAX_ENTITIES = int(os.getenv("SPACY_MAX_ENTITIES", "40"))

# Normalise labels FR/EN vers un jeu stable
_LABEL_MAP = {
    "PER": "PERSON",
    "PERSON": "PERSON",
    "ORG": "ORG",
    "LOC": "LOC",
    "GPE": "GPE",
    "FAC": "FAC",
    "PRODUCT": "PRODUCT",
    "EVENT": "EVENT",
    "WORK_OF_ART": "WORK_OF_ART",
    "LAW": "LAW",
    "LANGUAGE": "LANGUAGE",
    "DATE": "DATE",
    "TIME": "TIME",
    "PERCENT": "PERCENT",
    "MONEY": "MONEY",
    "QUANTITY": "QUANTITY",
    "ORDINAL": "ORDINAL",
    "CARDINAL": "CARDINAL",
    "NORP": "NORP",
    "MISC": "MISC",
}

_nlp_cache: Dict[str, Any] = {}


def normalize_entity_label(label: str) -> str:
    raw = (label or "MISC").strip().upper()
    return _LABEL_MAP.get(raw, raw or "MISC")


def is_person_label(label: str) -> bool:
    return normalize_entity_label(label) == "PERSON"


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
        # Preferer md si SPACY_MODEL le demande, sinon sm
        preferred = os.getenv("SPACY_MODEL", _DEFAULT_MODEL)
        if lang_hint:
            lang = lang_hint[:2].lower()
            candidates.extend(
                [
                    f"{lang}_core_news_md",
                    f"{lang}_core_news_sm",
                    f"{lang}_core_web_md",
                    f"{lang}_core_web_sm",
                ]
            )
        if preferred not in candidates:
            candidates.insert(0, preferred)
        candidates.extend(["fr_core_news_md", "fr_core_news_sm", "en_core_web_md", "en_core_web_sm"])

        seen: Set[str] = set()
        ordered = []
        for name in candidates:
            if name and name not in seen:
                seen.add(name)
                ordered.append(name)

        for model_name in ordered:
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

    def analyze(
        self,
        text: str,
        *,
        lang_hint: Optional[str] = None,
        media_captions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Analyse le corps + optionnellement les legendes media (alt/title)."""
        body = (text or "").strip()
        captions = media_captions if isinstance(media_captions, list) else []
        caption_blob = self._join_captions(captions)

        if len(body) < _MIN_CHARS and not caption_blob:
            return skip_result("texte trop court")

        try:
            nlp = self._load_model(lang_hint)
            entities: List[Dict[str, Any]] = []
            seen: Set[Tuple[str, str]] = set()

            if body:
                self._collect_ents(
                    nlp(body[:100_000]),
                    entities,
                    seen,
                    source="ner_spacy",
                    media_id=None,
                )

            # Legendes / alt images-videos : souvent riches en noms
            for cap in captions:
                if not isinstance(cap, dict):
                    continue
                piece = " ".join(
                    str(cap.get(k) or "").strip()
                    for k in ("title", "alt", "caption")
                    if cap.get(k)
                ).strip()
                if len(piece) < 3:
                    continue
                media_id = cap.get("media_id")
                self._collect_ents(
                    nlp(piece[:5_000]),
                    entities,
                    seen,
                    source="ner_spacy_media",
                    media_id=int(media_id) if isinstance(media_id, int) else None,
                )

            if not entities:
                return skip_result("aucune entite detectee")

            persons = [e for e in entities if is_person_label(e["label"])]
            return ok_result(
                entities=entities[:_MAX_ENTITIES],
                persons=persons[:_MAX_ENTITIES],
                entity_count=len(entities),
                person_count=len(persons),
                model=nlp.meta.get("name", _DEFAULT_MODEL),
            )
        except OSError as exc:
            return skip_result(str(exc))
        except Exception as exc:
            return error_result(str(exc))

    @staticmethod
    def _join_captions(captions: List[Dict[str, Any]]) -> str:
        parts = []
        for cap in captions:
            if not isinstance(cap, dict):
                continue
            for k in ("title", "alt", "caption"):
                v = (cap.get(k) or "").strip()
                if v:
                    parts.append(v)
        return " ".join(parts)

    def _collect_ents(
        self,
        doc: Any,
        entities: List[Dict[str, Any]],
        seen: Set[Tuple[str, str]],
        *,
        source: str,
        media_id: Optional[int],
    ) -> None:
        for ent in doc.ents:
            text = ent.text.strip()
            if not text or len(text) > 500:
                continue
            label = normalize_entity_label(ent.label_)
            key = (text.lower(), label)
            if key in seen:
                continue
            seen.add(key)
            row: Dict[str, Any] = {
                "text": text,
                "label": label,
                "start_char": int(ent.start_char),
                "end_char": int(ent.end_char),
                "source": source,
            }
            if media_id is not None:
                row["media_id"] = media_id
            entities.append(row)
            if len(entities) >= _MAX_ENTITIES:
                return
