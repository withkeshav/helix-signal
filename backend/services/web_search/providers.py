"""HTTP clients for Tavily, Exa, Ollama web_search."""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.orm import Session
from structlog import get_logger

from providers.settings import get_secret
from services.web_search.normalize import normalize_exa, normalize_ollama, normalize_tavily

log = get_logger(__name__)

MAX_RESULTS = 5


def _key(secret_name: str, db: Session | None) -> str:
    """Resolve secret from DB (encrypted) or env via registry key_env on get_secret."""
    return str(get_secret(secret_name, db) or "").strip()


def tavily_configured(db: Session | None) -> bool:
    return bool(_key("secret_tavily_api_key", db))


def exa_configured(db: Session | None) -> bool:
    return bool(_key("secret_exa_api_key", db))


def ollama_configured(db: Session | None) -> bool:
    return bool(_key("secret_ollama_api_key", db))


def search_tavily(query: str, db: Session | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    api_key = _key("secret_tavily_api_key", db)
    if not api_key:
        return [], {"error": "no_key"}
    try:
        with httpx.Client(timeout=25.0) as client:
            r = client.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "query": query,
                    "search_depth": "basic",
                    "max_results": MAX_RESULTS,
                    "topic": "news",
                    "include_answer": False,
                    "include_raw_content": False,
                },
            )
            if r.status_code >= 400:
                log.warning("web_search.tavily_http", status=r.status_code, body=r.text[:200])
                return [], {"error": f"http_{r.status_code}"}
            data = r.json()
            hits = normalize_tavily(data if isinstance(data, dict) else {})
            return hits, {"provider": "tavily", "credits": (data or {}).get("usage")}
    except Exception as exc:
        log.warning("web_search.tavily_failed", error=str(exc), exc_info=True)
        return [], {"error": str(exc)}


def search_exa(query: str, db: Session | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    api_key = _key("secret_exa_api_key", db)
    if not api_key:
        return [], {"error": "no_key"}
    try:
        with httpx.Client(timeout=25.0) as client:
            r = client.post(
                "https://api.exa.ai/search",
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
                json={
                    "query": query,
                    "numResults": MAX_RESULTS,
                    "type": "auto",
                    "contents": {"text": {"maxCharacters": 500}},
                },
            )
            if r.status_code >= 400:
                log.warning("web_search.exa_http", status=r.status_code, body=r.text[:200])
                return [], {"error": f"http_{r.status_code}"}
            data = r.json()
            hits = normalize_exa(data if isinstance(data, dict) else {})
            return hits, {"provider": "exa"}
    except Exception as exc:
        log.warning("web_search.exa_failed", error=str(exc), exc_info=True)
        return [], {"error": str(exc)}


def search_ollama(query: str, db: Session | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    api_key = _key("secret_ollama_api_key", db)
    if not api_key:
        return [], {"error": "no_key"}
    try:
        with httpx.Client(timeout=25.0) as client:
            r = client.post(
                "https://ollama.com/api/web_search",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"query": query},
            )
            if r.status_code >= 400:
                log.warning("web_search.ollama_http", status=r.status_code, body=r.text[:200])
                return [], {"error": f"http_{r.status_code}"}
            data = r.json()
            hits = normalize_ollama(data if isinstance(data, dict) else {})
            return hits, {"provider": "ollama"}
    except Exception as exc:
        log.warning("web_search.ollama_failed", error=str(exc), exc_info=True)
        return [], {"error": str(exc)}


def search_with_fallback(query: str, db: Session | None) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    """Tavily → Exa → Ollama. Caller must only invoke when feature is enabled (Tavily or Exa key)."""
    attempts: list[dict[str, Any]] = []

    if tavily_configured(db):
        hits, meta = search_tavily(query, db)
        attempts.append({"provider": "tavily", **meta, "hits": len(hits)})
        if hits:
            return hits, "tavily", {"attempts": attempts, **meta}

    if exa_configured(db):
        hits, meta = search_exa(query, db)
        attempts.append({"provider": "exa", **meta, "hits": len(hits)})
        if hits:
            return hits, "exa", {"attempts": attempts, **meta}

    # Third backup only — never the opt-in signal
    if ollama_configured(db):
        hits, meta = search_ollama(query, db)
        attempts.append({"provider": "ollama", **meta, "hits": len(hits)})
        if hits:
            return hits, "ollama", {"attempts": attempts, **meta}

    return [], "none", {"attempts": attempts, "error": "all_failed"}
