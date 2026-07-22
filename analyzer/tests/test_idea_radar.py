"""Tests matching intent / themes / score du radar idees."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.idea_radar_service import (
    match_intents,
    match_themes,
    score_bucket,
    snippet_around,
)


def test_match_intents_english_and_french():
    text = "I'd pay for a better billing tool. Aussi besoin d'un outil simple."
    keys = {k for k, _, _ in match_intents(text)}
    assert "id_pay" in keys
    assert "need_tool" in keys


def test_match_themes_saas_ai():
    text = "Nouveau SaaS B2B avec LLM et RAG pour les equipes."
    themes = match_themes(text)
    assert "saas" in themes
    assert "ai" in themes


def test_score_bucket_rewards_intent_and_diversity():
    weak = score_bucket(
        intent_weight=1.0,
        intent_hits=1,
        article_count=1,
        site_count=1,
        recency_bonus=0.0,
    )
    strong = score_bucket(
        intent_weight=6.0,
        intent_hits=3,
        article_count=5,
        site_count=3,
        recency_bonus=1.5,
    )
    assert strong > weak


def test_snippet_around_keeps_context():
    text = "Avant " + ("x" * 40) + " looking for " + ("y" * 40) + " apres"
    snip = snippet_around(text, "looking for", radius=20)
    assert "looking for" in snip.lower()
    assert "…" in snip or "Avant" not in snip or len(snip) < len(text)
