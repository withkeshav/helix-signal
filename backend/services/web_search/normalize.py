"""Normalize provider responses to a common hit shape."""

from __future__ import annotations

from typing import Any


def hit(
    *,
    title: str,
    url: str,
    snippet: str,
    score: float | None = None,
    published_at: str | None = None,
) -> dict[str, Any]:
    return {
        "title": (title or "").strip()[:500],
        "url": (url or "").strip()[:2000],
        "snippet": (snippet or "").strip()[:2000],
        "score": score,
        "published_at": published_at,
    }


def normalize_tavily(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in payload.get("results") or []:
        if not isinstance(row, dict):
            continue
        out.append(
            hit(
                title=str(row.get("title") or ""),
                url=str(row.get("url") or ""),
                snippet=str(row.get("content") or row.get("raw_content") or ""),
                score=float(row["score"]) if row.get("score") is not None else None,
            )
        )
    return [h for h in out if h["url"] or h["title"]]


def normalize_exa(payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in payload.get("results") or []:
        if not isinstance(row, dict):
            continue
        snippet = (
            row.get("text")
            or row.get("summary")
            or (row.get("highlights") or [None])[0]
            or ""
        )
        if isinstance(snippet, list):
            snippet = " ".join(str(s) for s in snippet[:3])
        out.append(
            hit(
                title=str(row.get("title") or ""),
                url=str(row.get("url") or row.get("id") or ""),
                snippet=str(snippet),
                score=float(row["score"]) if row.get("score") is not None else None,
                published_at=str(row["publishedDate"]) if row.get("publishedDate") else None,
            )
        )
    return [h for h in out if h["url"] or h["title"]]


def normalize_ollama(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Ollama web_search response shapes vary; accept common fields."""
    out: list[dict[str, Any]] = []
    rows = payload.get("results") or payload.get("data") or payload.get("organic") or []
    if isinstance(payload.get("result"), list):
        rows = payload["result"]
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            hit(
                title=str(row.get("title") or row.get("name") or ""),
                url=str(row.get("url") or row.get("link") or ""),
                snippet=str(row.get("content") or row.get("snippet") or row.get("text") or ""),
            )
        )
    return [h for h in out if h["url"] or h["title"]]
