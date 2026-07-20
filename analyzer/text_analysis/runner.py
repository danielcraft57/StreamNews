"""Orchestration des analyseurs independants."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from text_analysis.base import TextAnalyzer, error_result
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
]

_REGISTRY: Dict[str, TextAnalyzer] = {a.name: a for a in _BUILTIN_ANALYZERS}


def list_analyzers() -> List[Dict[str, Any]]:
    """Liste les outils disponibles et leur statut d'installation."""
    out = []
    for analyzer in _BUILTIN_ANALYZERS:
        out.append({
            "name": analyzer.name,
            "available": analyzer.is_available(),
        })
    return out


def get_analyzer(name: str) -> Optional[TextAnalyzer]:
    return _REGISTRY.get(name)


def run_analyzers(
    text: str,
    *,
    only: Optional[Iterable[str]] = None,
    lang_hint: Optional[str] = None,
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
        results[analyzer.name] = _safe_analyze(analyzer, text, lang_hint=hint)

    return results


def run_single_analyzer(
    name: str,
    text: str,
    *,
    lang_hint: Optional[str] = None,
) -> Dict[str, Any]:
    analyzer = get_analyzer(name)
    if not analyzer:
        return error_result(f"analyseur inconnu: {name}")
    if not analyzer.is_available():
        return {"status": "skipped", "reason": "dependance non installee"}
    return _safe_analyze(analyzer, text, lang_hint=lang_hint)


def _select_analyzers(only: Optional[Iterable[str]]) -> List[TextAnalyzer]:
    if not only:
        return list(_BUILTIN_ANALYZERS)
    names = {n.strip() for n in only if n and n.strip()}
    return [a for a in _BUILTIN_ANALYZERS if a.name in names]


def _safe_analyze(
    analyzer: TextAnalyzer,
    text: str,
    *,
    lang_hint: Optional[str] = None,
) -> Dict[str, Any]:
    if not analyzer.is_available():
        return {"status": "skipped", "reason": "dependance non installee"}
    try:
        return analyzer.analyze(text, lang_hint=lang_hint)
    except Exception as exc:
        return error_result(str(exc))
