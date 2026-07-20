"""Scheduled web search job — never raises into scheduler."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session
from structlog import get_logger

from providers.settings import get_setting
from services.web_search.providers import (
    exa_configured,
    search_with_fallback,
    tavily_configured,
)
from services.web_search.queries import build_query_plan
from services.web_search.store import save_snapshot

log = get_logger(__name__)


def web_search_feature_enabled(db: Session) -> bool:
    """ON only when AI mode is on AND (Tavily or Exa) key present.

    Ollama alone is never enough (that key is always present for LLM).
    Opt-in is adding Tavily and/or Exa in Settings → Control Room → secrets.
    Opt-in: Tavily and/or Exa API key present while ai_mode is on.
    """
    mode = str(get_setting("ai_mode", db) or "ai_off").strip().lower()
    if mode in ("", "ai_off", "off", "false", "0"):
        return False
    return tavily_configured(db) or exa_configured(db)


def run_web_search_job(db: Session) -> dict[str, Any]:
    """Execute minimal query plan; persist hits. Safe for scheduler."""
    if not web_search_feature_enabled(db):
        log.info("web_search.skip", reason="feature_off_or_no_tavily_exa")
        return {"status": "skipped", "reason": "feature_off_or_no_tavily_exa", "saved": 0}

    plan = build_query_plan(db)
    saved = 0
    errors = 0
    for item in plan:
        qkey = item["query_key"]
        qtext = item["query_text"]
        try:
            hits, provider, meta = search_with_fallback(qtext, db)
            if hits and provider != "none":
                row = save_snapshot(
                    db,
                    query_key=qkey,
                    query_text=qtext,
                    provider=provider,
                    hits=hits,
                    raw_meta=meta,
                )
                if row:
                    saved += 1
                    try:
                        from services.source_usage import increment_source_usage

                        increment_source_usage(db, f"web_search_{provider}")
                    except Exception:
                        log.warning("web_search.usage_record_failed", provider=provider, exc_info=True)
                    log.info(
                        "web_search.ok",
                        query_key=qkey,
                        provider=provider,
                        hits=len(hits),
                    )
                else:
                    errors += 1
            else:
                errors += 1
                log.warning("web_search.empty", query_key=qkey, meta=meta)
        except Exception:
            errors += 1
            log.exception("web_search.query_failed", query_key=qkey)

    try:
        from services.source_usage import flush_source_usage

        flush_source_usage(db)
    except Exception:
        log.warning("web_search.usage_flush_failed", exc_info=True)

    result = {"status": "ok", "saved": saved, "errors": errors, "planned": len(plan)}
    try:
        from routes.health_status import emit_web_search_alerts

        emit_web_search_alerts(db, job_result=result)
    except Exception:
        log.warning("web_search.alert_emit_failed", exc_info=True)
    return result
