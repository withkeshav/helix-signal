"""Ollama Cloud sentiment analysis — replaces local FinBERT for OSINT article scoring."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

OLLAMA_API_BASE = os.getenv("OLLAMA_CLOUD_BASE", "https://ollama.com/v1")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
OLLAMA_MODEL = os.getenv("OLLAMA_CLOUD_MODEL", "ministral-3:8b-cloud")

_SENTIMENT_CACHE: dict[str, dict[str, Any]] = {}


def _parse_sentiment(item: dict) -> dict[str, Any]:
    label = str(item.get("label", "neutral")).lower()
    conf = float(item.get("confidence", 0.5))
    score_map = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}
    return {"score": round(score_map.get(label, 0.0) * conf, 4), "label": label}


def _make_request(titles: list[str]) -> list[dict[str, Any]]:
    if not OLLAMA_API_KEY:
        return [{"score": 0.0, "label": "neutral"} for _ in titles]

    headlines = "\n".join(f"{i+1}. {t[:200]}" for i, t in enumerate(titles))
    prompt = (
        "Classify the sentiment of each crypto news headline as positive, negative, or neutral.\n"
        "Respond ONLY with a valid JSON array, no other text:\n"
        '[{"label": "positive|negative|neutral", "confidence": 0.0-1.0}, ...]\n\n'
        f"Headlines:\n{headlines}"
    )

    try:
        resp = httpx.post(
            f"{OLLAMA_API_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {OLLAMA_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 4096,
            },
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        results = json.loads(text)
        if not isinstance(results, list):
            raise ValueError("Expected array")
        return [_parse_sentiment(r) for r in results]
    except Exception:
        return [{"score": 0.0, "label": "neutral"} for _ in titles]


def clear_cache() -> None:
    _SENTIMENT_CACHE.clear()


def analyze_batch(titles: list[str]) -> list[dict[str, Any]]:
    """Analyze sentiment for a list of titles, caching by title to avoid re-calls."""
    uncached = [(i, t) for i, t in enumerate(titles) if t not in _SENTIMENT_CACHE]
    if uncached:
        uncached_titles = [t for _, t in uncached]
        results = _make_request(uncached_titles)
        for (_, title), result in zip(uncached, results):
            _SENTIMENT_CACHE[title] = result
    return [_SENTIMENT_CACHE.get(t, {"score": 0.0, "label": "neutral"}) for t in titles]
