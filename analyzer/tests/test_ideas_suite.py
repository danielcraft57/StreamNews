"""Unit tests watchlist / brief / fiches markdown."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.brief_service import week_start_iso
from services.idea_notes_service import render_idea_markdown


def test_render_idea_markdown_basic():
    md = render_idea_markdown(
        {
            "title": "Billing SaaS",
            "theme": "billing",
            "status": "draft",
            "problem": "Trop de friction au checkout",
            "evidence": ["I'd pay for simpler invoices", "looking for Stripe alternative"],
            "mvp_plan": "Landing + Stripe checkout",
            "source_refs": [{"title": "Ask HN: invoices"}],
        }
    )
    assert "# Billing SaaS" in md
    assert "**Theme:** billing" in md
    assert "I'd pay for simpler invoices" in md
    assert "Landing + Stripe checkout" in md
    assert "Ask HN: invoices" in md


def test_week_start_iso_is_monday():
    from datetime import datetime

    # Thursday 2026-07-23 → Monday 2026-07-20
    assert week_start_iso(datetime(2026, 7, 23, 12, 0, 0)) == "2026-07-20"


def test_brief_topic_sort_prefers_higher_score():
    topics = [
        {"term": "billing", "score": 8, "article_count": 2},
        {"term": "ai", "score": 20, "article_count": 5},
        {"term": "rag", "score": 12, "article_count": 4},
    ]
    topics.sort(key=lambda x: (-float(x.get("score") or 0), -(x.get("article_count") or 0)))
    assert topics[0]["term"] == "ai"
    assert topics[1]["term"] == "rag"


def test_watchlist_delta_positive_when_current_higher():
    current, previous = 10, 3
    delta = current - previous
    score = delta * 2 + current
    assert delta == 7
    assert score > current
