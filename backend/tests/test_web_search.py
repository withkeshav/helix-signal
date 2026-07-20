"""Unit tests for scheduled web search (Tavily → Exa → Ollama) and AI cache helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from services.web_search.normalize import (
    normalize_exa,
    normalize_ollama,
    normalize_tavily,
)
from services.web_search.store import format_web_context_for_prompt


# ---------------------------------------------------------------------------
# Normalize
# ---------------------------------------------------------------------------


def test_normalize_tavily_basic():
    payload = {
        "results": [
            {
                "title": "USDT news",
                "url": "https://example.com/a",
                "content": "Peg stable",
                "score": 0.9,
            },
            {"title": "", "url": "", "content": "skip"},
        ]
    }
    hits = normalize_tavily(payload)
    assert len(hits) == 1
    assert hits[0]["title"] == "USDT news"
    assert hits[0]["url"] == "https://example.com/a"
    assert hits[0]["snippet"] == "Peg stable"
    assert hits[0]["score"] == pytest.approx(0.9)


def test_normalize_exa_text_and_published():
    payload = {
        "results": [
            {
                "title": "Circle attestation",
                "url": "https://example.com/b",
                "text": "Reserves full",
                "score": 0.5,
                "publishedDate": "2026-07-01",
            }
        ]
    }
    hits = normalize_exa(payload)
    assert len(hits) == 1
    assert hits[0]["snippet"] == "Reserves full"
    assert hits[0]["published_at"] == "2026-07-01"


def test_normalize_ollama_variants():
    hits = normalize_ollama(
        {
            "results": [
                {"title": "A", "url": "https://a.test", "content": "body"},
            ]
        }
    )
    assert hits[0]["title"] == "A"
    hits2 = normalize_ollama(
        {
            "data": [
                {"name": "B", "link": "https://b.test", "snippet": "snip"},
            ]
        }
    )
    assert hits2[0]["title"] == "B"
    assert hits2[0]["url"] == "https://b.test"


# ---------------------------------------------------------------------------
# Feature gate
# ---------------------------------------------------------------------------


def test_feature_off_when_ai_off():
    from services.web_search.job import web_search_feature_enabled

    db = MagicMock()
    with (
        patch("services.web_search.job.get_setting", return_value="ai_off"),
        patch("services.web_search.job.tavily_configured", return_value=True),
        patch("services.web_search.job.exa_configured", return_value=False),
    ):
        assert web_search_feature_enabled(db) is False


def test_feature_off_when_only_ollama_would_exist():
    """Ollama alone must never enable web search (key always present for LLM)."""
    from services.web_search.job import web_search_feature_enabled

    db = MagicMock()
    with (
        patch("services.web_search.job.get_setting", return_value="ai_full"),
        patch("services.web_search.job.tavily_configured", return_value=False),
        patch("services.web_search.job.exa_configured", return_value=False),
    ):
        assert web_search_feature_enabled(db) is False


def test_feature_on_with_tavily_and_ai_mode():
    from services.web_search.job import web_search_feature_enabled

    db = MagicMock()
    with (
        patch("services.web_search.job.get_setting", return_value="ai_lite"),
        patch("services.web_search.job.tavily_configured", return_value=True),
        patch("services.web_search.job.exa_configured", return_value=False),
    ):
        assert web_search_feature_enabled(db) is True


def test_feature_on_with_exa_only():
    from services.web_search.job import web_search_feature_enabled

    db = MagicMock()
    with (
        patch("services.web_search.job.get_setting", return_value="ai_full"),
        patch("services.web_search.job.tavily_configured", return_value=False),
        patch("services.web_search.job.exa_configured", return_value=True),
    ):
        assert web_search_feature_enabled(db) is True


# ---------------------------------------------------------------------------
# Fallback chain
# ---------------------------------------------------------------------------


def test_search_with_fallback_tavily_first():
    from services.web_search.providers import search_with_fallback

    db = MagicMock()
    tavily_hits = [{"title": "T", "url": "https://t", "snippet": "s"}]
    with (
        patch("services.web_search.providers.tavily_configured", return_value=True),
        patch("services.web_search.providers.exa_configured", return_value=True),
        patch("services.web_search.providers.ollama_configured", return_value=True),
        patch(
            "services.web_search.providers.search_tavily",
            return_value=(tavily_hits, {"provider": "tavily"}),
        ) as mt,
        patch("services.web_search.providers.search_exa") as me,
        patch("services.web_search.providers.search_ollama") as mo,
    ):
        hits, provider, meta = search_with_fallback("q", db)
        assert provider == "tavily"
        assert hits == tavily_hits
        mt.assert_called_once()
        me.assert_not_called()
        mo.assert_not_called()


def test_search_with_fallback_to_exa_then_ollama():
    from services.web_search.providers import search_with_fallback

    db = MagicMock()
    ollama_hits = [{"title": "O", "url": "https://o", "snippet": "s"}]
    with (
        patch("services.web_search.providers.tavily_configured", return_value=True),
        patch("services.web_search.providers.exa_configured", return_value=True),
        patch("services.web_search.providers.ollama_configured", return_value=True),
        patch(
            "services.web_search.providers.search_tavily",
            return_value=([], {"error": "http_429"}),
        ),
        patch(
            "services.web_search.providers.search_exa",
            return_value=([], {"error": "empty"}),
        ),
        patch(
            "services.web_search.providers.search_ollama",
            return_value=(ollama_hits, {"provider": "ollama"}),
        ),
    ):
        hits, provider, meta = search_with_fallback("q", db)
        assert provider == "ollama"
        assert hits == ollama_hits
        assert len(meta.get("attempts") or []) >= 2


def test_run_job_skips_when_feature_off():
    from services.web_search.job import run_web_search_job

    db = MagicMock()
    with patch(
        "services.web_search.job.web_search_feature_enabled",
        return_value=False,
    ):
        result = run_web_search_job(db)
        assert result["status"] == "skipped"
        assert result["saved"] == 0


def test_run_job_saves_hits():
    from services.web_search.job import run_web_search_job

    db = MagicMock()
    hits = [{"title": "N", "url": "https://n", "snippet": "x"}]
    with (
        patch("services.web_search.job.web_search_feature_enabled", return_value=True),
        patch(
            "services.web_search.job.build_query_plan",
            return_value=[{"query_key": "global_news", "query_text": "stablecoin"}],
        ),
        patch(
            "services.web_search.job.search_with_fallback",
            return_value=(hits, "tavily", {"attempts": []}),
        ),
        patch("services.web_search.job.save_snapshot", return_value=MagicMock()) as save,
    ):
        result = run_web_search_job(db)
        assert result["status"] == "ok"
        assert result["saved"] == 1
        save.assert_called_once()


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------


def test_format_web_context_empty():
    assert format_web_context_for_prompt([]) == ""
    assert format_web_context_for_prompt([{"query_key": "g", "hits": []}]) == ""


def test_format_web_context_includes_rule():
    blocks = [
        {
            "query_key": "global_news",
            "provider": "tavily",
            "fetched_at": "2026-07-20T12:00:00+00:00",
            "hits": [
                {
                    "title": "Headline",
                    "url": "https://news.test/1",
                    "snippet": "Markets calm",
                }
            ],
        }
    ]
    text = format_web_context_for_prompt(blocks)
    assert "WEB_CONTEXT" in text
    assert "Headline" in text
    assert "prefer helix data" in text.lower()
    assert "narrative context only" in text.lower()


def test_secrets_registered():
    from providers.settings_registry import _DEFAULT_SETTINGS

    assert "secret_tavily_api_key" in _DEFAULT_SETTINGS
    assert "secret_exa_api_key" in _DEFAULT_SETTINGS
    assert _DEFAULT_SETTINGS["secret_tavily_api_key"]["type"] == "secret"
    assert _DEFAULT_SETTINGS["secret_exa_api_key"]["type"] == "secret"
    assert "retention_web_search_snapshots_days" in _DEFAULT_SETTINGS
