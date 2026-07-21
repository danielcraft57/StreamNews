"""Orchestration des analyseurs independants."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from text_analysis.base import TextAnalyzer, error_result
from text_analysis.face_detect import FaceDetectAnalyzer, face_detect_enabled
from text_analysis.keywords_yake import YakeKeywordsAnalyzer
from text_analysis.lang_detect import LangDetectAnalyzer
from text_analysis.ner_spacy import SpacyNerAnalyzer
from text_analysis.simhash_tool import SimhashAnalyzer
from text_analysis.summary_sumy import SumySummaryAnalyzer

_BUILTIN_ANALYZERS: List[TextAnalyzer] = [
    LangDetectAnalyzer(),
    YakeKeywordsAnalyzer(),
    SimhashAnalyzer(),
    SumySummaryAnalyzer(),
    SpacyNerAnalyzer(),
    FaceDetectAnalyzer(),
]

_REGISTRY: Dict[str, TextAnalyzer] = {a.name: a for a in _BUILTIN_ANALYZERS}


def list_analyzers() -> List[Dict[str, Any]]:
    """Liste les outils disponibles et leur statut d'installation."""
    out = []
    for analyzer in _BUILTIN_ANALYZERS:
        info: Dict[str, Any] = {
            "name": analyzer.name,
            "available": analyzer.is_available(),
        }
        if analyzer.name == "face_detect":
            info["enabled"] = face_detect_enabled()
            info["optional"] = True
        out.append(info)
    return out


def get_analyzer(name: str) -> Optional[TextAnalyzer]:
    return _REGISTRY.get(name)


def run_analyzers(
    text: str,
    *,
    only: Optional[Iterable[str]] = None,
    lang_hint: Optional[str] = None,
    media_captions: Optional[List[Dict[str, Any]]] = None,
    media_items: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Execute chaque analyseur independamment."""
    selected = _select_analyzers(only)
    results: Dict[str, Any] = {}
    detected_lang = lang_hint

    for analyzer in selected:
        if analyzer.name == "lang_detect":
            block = _safe_analyze(analyzer, text, lang_hint=detected_lang)
            results[analyzer.name] = block
            if block.get("status") == "ok" and block.get("lang"):
                detected_lang = block["lang"]
            continue

        hint = detected_lang if analyzer.name in ("keywords_yake", "ner_spacy") else lang_hint
        results[analyzer.name] = _safe_analyze(
            analyzer,
            text,
            lang_hint=hint,
            media_captions=media_captions if analyzer.name == "ner_spacy" else None,
            media_items=media_items if analyzer.name == "face_detect" else None,
        )

    return results


def run_single_analyzer(
    name: str,
    text: str,
    *,
    lang_hint: Optional[str] = None,
    media_captions: Optional[List[Dict[str, Any]]] = None,
    media_items: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    analyzer = get_analyzer(name)
    if not analyzer:
        return error_result(f"analyseur inconnu: {name}")
    if not analyzer.is_available():
        return {"status": "skipped", "reason": "dependance non installee"}
    return _safe_analyze(
        analyzer,
        text,
        lang_hint=lang_hint,
        media_captions=media_captions if name == "ner_spacy" else None,
        media_items=media_items if name == "face_detect" else None,
    )


def _select_analyzers(only: Optional[Iterable[str]]) -> List[TextAnalyzer]:
    if only:
        names = {n.strip() for n in only if n and n.strip()}
        return [a for a in _BUILTIN_ANALYZERS if a.name in names]
    # Par defaut : face_detect seulement si explicitement active
    out: List[TextAnalyzer] = []
    for a in _BUILTIN_ANALYZERS:
        if a.name == "face_detect" and not face_detect_enabled():
            continue
        out.append(a)
    return out


def _safe_analyze(
    analyzer: TextAnalyzer,
    text: str,
    *,
    lang_hint: Optional[str] = None,
    media_captions: Optional[List[Dict[str, Any]]] = None,
    media_items: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if not analyzer.is_available():
        return {"status": "skipped", "reason": "dependance non installee"}
    try:
        kwargs: Dict[str, Any] = {"lang_hint": lang_hint}
        if media_captions is not None and analyzer.name == "ner_spacy":
            kwargs["media_captions"] = media_captions
        if media_items is not None and analyzer.name == "face_detect":
            kwargs["media_items"] = media_items
        return analyzer.analyze(text, **kwargs)
    except TypeError:
        return analyzer.analyze(text, lang_hint=lang_hint)
    except Exception as exc:
        return error_result(str(exc))
