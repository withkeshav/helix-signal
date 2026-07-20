"""Persist and load web_search_snapshots for AI prompts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from structlog import get_logger

from database import WebSearchSnapshot

log = get_logger(__name__)

DEFAULT_TTL_HOURS = 14  # slightly > 12h job so cache survives late AI calls


def save_snapshot(
    db: Session,
    *,
    query_key: str,
    query_text: str,
    provider: str,
    hits: list[dict[str, Any]],
    raw_meta: dict[str, Any] | None = None,
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> WebSearchSnapshot | None:
    if not hits:
        return None
    now = datetime.now(timezone.utc)
    row = WebSearchSnapshot(
        query_key=query_key[:64],
        query_text=query_text[:4000],
        provider=provider[:32],
        fetched_at=now,
        expires_at=now + timedelta(hours=ttl_hours),
        hits=hits,
        raw_meta=raw_meta,
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
        return row
    except Exception:
        log.exception("web_search.save_failed", query_key=query_key)
        db.rollback()
        return None


def load_fresh_by_keys(db: Session, query_keys: list[str]) -> list[WebSearchSnapshot]:
    now = datetime.now(timezone.utc)
    rows: list[WebSearchSnapshot] = []
    for key in query_keys:
        row = (
            db.execute(
                select(WebSearchSnapshot)
                .where(
                    WebSearchSnapshot.query_key == key,
                    WebSearchSnapshot.expires_at > now,
                )
                .order_by(desc(WebSearchSnapshot.fetched_at))
                .limit(1)
            )
            .scalars()
            .first()
        )
        if row:
            rows.append(row)
    return rows


def load_web_context_for_asset(db: Session, asset: str | None = None) -> list[dict[str, Any]]:
    """Latest non-expired hits for global + optional asset keys."""
    keys = ["global_news", "issuer_news"]
    if asset:
        keys.append(f"asset:{asset.upper()}")
    rows = load_fresh_by_keys(db, keys)
    blocks: list[dict[str, Any]] = []
    for row in rows:
        blocks.append(
            {
                "query_key": row.query_key,
                "provider": row.provider,
                "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
                "hits": row.hits or [],
            }
        )
    return blocks


def format_web_context_for_prompt(blocks: list[dict[str, Any]], *, max_hits: int = 8) -> str:
    if not blocks:
        return ""
    lines = [
        "WEB_CONTEXT (cached scheduled search; may be incomplete — prefer Helix DATA numbers):",
    ]
    n = 0
    for block in blocks:
        provider = block.get("provider") or "?"
        fetched = block.get("fetched_at") or "?"
        lines.append(f"[{block.get('query_key')} via {provider} at {fetched}]")
        for h in block.get("hits") or []:
            if n >= max_hits:
                break
            title = (h.get("title") or "").strip()
            url = (h.get("url") or "").strip()
            snip = (h.get("snippet") or "").strip()[:280]
            lines.append(f"- {title} ({url}) — {snip}")
            n += 1
        if n >= max_hits:
            break
    if n == 0:
        return ""
    lines.append("RULE: Web is narrative context only. Never invent metrics not in DATA.")
    return "\n".join(lines)
