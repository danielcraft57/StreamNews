"""Service d'analyse texte sur articles enrichis."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from text_analysis.clean import prepare_text_for_analysis
from text_analysis.runner import list_analyzers, run_analyzers, run_single_analyzer


def merge_analysis_results(
    existing: Optional[Dict[str, Any]],
    new_results: Dict[str, Any],
) -> Dict[str, Any]:
    """Fusionne les blocs par outil sans ecraser les succes existants."""
    base = dict(existing or {})
    for tool_name, block in (new_results or {}).items():
        if not isinstance(block, dict):
            continue
        prev = base.get(tool_name)
        if isinstance(prev, dict) and prev.get("status") == "ok" and block.get("status") != "ok":
            continue
        base[tool_name] = block
    return base


def analyze_article_content(
    content_text: Optional[str],
    content_html: Optional[str] = None,
    *,
    only: Optional[Iterable[str]] = None,
    lang_hint: Optional[str] = None,
    existing_analysis: Optional[Dict[str, Any]] = None,
    media_captions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Prepare le texte et execute les analyseurs demandes."""
    text = prepare_text_for_analysis(content_text, content_html)
    captions = media_captions if media_captions else None
    if len(text.strip()) < 40 and not captions:
        return {
            "analysis_status": "skipped",
            "analysis_error": "contenu insuffisant",
            "analysis": merge_analysis_results(existing_analysis, {}),
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }

    only_list = list(only) if only else None
    if only_list and len(only_list) == 1:
        tool = only_list[0]
        results = {
            tool: run_single_analyzer(
                tool, text, lang_hint=lang_hint, media_captions=captions
            )
        }
    else:
        results = run_analyzers(
            text, only=only_list, lang_hint=lang_hint, media_captions=captions
        )

    merged = merge_analysis_results(existing_analysis, results)
    statuses = [b.get("status") for b in results.values() if isinstance(b, dict)]
    if any(s == "ok" for s in statuses):
        status = "ok"
    elif statuses and all(s == "skipped" for s in statuses):
        status = "skipped"
    else:
        status = "error"

    return {
        "analysis_status": status,
        "analysis_error": None if status == "ok" else "aucun outil n'a produit de resultat",
        "analysis": merged,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }


def available_analyzers() -> List[Dict[str, Any]]:
    return list_analyzers()
