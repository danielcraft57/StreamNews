"""Tests orchestration analyse texte."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.text_analysis_service import analyze_article_content, merge_analysis_results
from text_analysis.runner import list_analyzers, run_single_analyzer


SAMPLE = (
    "La Banque centrale europeenne a annonce une hausse des taux directeurs. "
    "Les marches financiers ont reagi avec prudence face a cette decision. "
    "Les analystes estiment que l inflation reste elevee en zone euro malgre "
    "plusieurs mois de politique monetaire restrictive. "
    "Les entreprises du secteur bancaire pourraient beneficier de marges "
    "ameliorees a moyen terme selon plusieurs economistes."
)


def test_list_analyzers_returns_builtin_tools():
    names = {a["name"] for a in list_analyzers()}
    assert "lang_detect" in names
    assert "keywords_yake" in names
    assert "simhash" in names


def test_merge_analysis_results_keeps_ok_on_error():
    merged = merge_analysis_results(
        {"lang_detect": {"status": "ok", "lang": "fr"}},
        {"lang_detect": {"status": "error", "error": "boom"}},
    )
    assert merged["lang_detect"]["status"] == "ok"


def test_run_lang_detect_when_available():
    result = run_single_analyzer("lang_detect", SAMPLE)
    if result.get("status") == "skipped":
        return
    assert result["status"] == "ok"
    assert result.get("lang")


def test_analyze_article_content_structure():
    payload = analyze_article_content(SAMPLE, only=["simhash"])
    assert "analysis" in payload
    assert "analysis_status" in payload
    assert "simhash" in payload["analysis"]
