"""Ollama Cloud sentiment analysis — replaces local FinBERT for OSINT article scoring."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

_SENTIMENT_CACHE: dict[str, dict[str, Any]] = {}


def _sentiment_max_articles() -> int:
    from providers.settings import get_setting
    try:
        val = get_setting("sentiment_max_articles_per_batch")
        if val is not None:
            return int(val)
    except Exception:
        logging.getLogger(__name__).debug("Sentiment max articles lookup failed", exc_info=True)
    import os
    return int(os.getenv("SENTIMENT_MAX_ARTICLES_PER_BATCH", "15"))


def _within_sentiment_budget(estimated_tokens: int) -> bool:
    try:
        from services.components.ai.facade import within_budget
        return within_budget(estimated_tokens)
    except Exception:
        return True


def _parse_sentiment(item: dict) -> dict[str, Any]:
    label = str(item.get("label", "neutral")).lower()
    conf = float(item.get("confidence", 0.5))
    score_map = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}
    return {"score": round(score_map.get(label, 0.0) * conf, 4), "label": label}


def _make_request(titles: list[str], db: Session | None = None) -> list[dict[str, Any]]:
    if db is None:
        return [{"score": 0.0, "label": "neutral"} for _ in titles]

    from services.ai_router import ai_mode, chat_for_feature

    if ai_mode(db) == "ai_off":
        return [{"score": 0.0, "label": "neutral"} for _ in titles]

    titles = titles[:_sentiment_max_articles()]
    if not titles:
        return []

    headlines = "\n".join(f"{i+1}. {t[:120]}" for i, t in enumerate(titles))
    prompt = (
        "Classify the sentiment of each crypto news headline as positive, negative, or neutral.\n"
        "Respond ONLY with a valid JSON array, no other text:\n"
        '[{"label": "positive|negative|neutral", "confidence": 0.0-1.0}, ...]\n\n'
        f"Headlines:\n{headlines}"
    )

    estimated_input = len(prompt.split()) + 50
    estimated_output = len(titles) * 15
    estimated_total = estimated_input + estimated_output

    if not _within_sentiment_budget(estimated_total):
        return [{"score": 0.0, "label": "neutral"} for _ in titles]

    try:
        result = chat_for_feature(
            db=db,
            feature="market_narrative",
            prompt=prompt,
            system="Respond ONLY with valid JSON.",
            max_tokens=500,
        )
        if not result or not result.get("text"):
            return [{"score": 0.0, "label": "neutral"} for _ in titles]
        text = result["text"]
        results = json.loads(text)
        if not isinstance(results, list):
            raise ValueError("Expected array")
        return [_parse_sentiment(r) for r in results]
    except Exception:
        logging.getLogger(__name__).warning("Sentiment analysis request failed", exc_info=True)
        return [{"score": 0.0, "label": "neutral"} for _ in titles]


def clear_cache() -> None:
    _SENTIMENT_CACHE.clear()


def analyze_batch(titles: list[str], db: Session | None = None) -> list[dict[str, Any]]:
    """Analyze sentiment for a list of titles, caching by title to avoid re-calls."""
    uncached = [(i, t) for i, t in enumerate(titles) if t not in _SENTIMENT_CACHE]
    if uncached:
        uncached_titles = [t for _, t in uncached]
        results = _make_request(uncached_titles, db=db)
        for (_, title), result in zip(uncached, results):
            _SENTIMENT_CACHE[title] = result
    return [_SENTIMENT_CACHE.get(t, {"score": 0.0, "label": "neutral"}) for t in titles]
