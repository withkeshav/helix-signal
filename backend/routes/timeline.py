"""Merged asset timeline — scores, events, OSINT, web search, FRED co-occurrence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from core.api_auth import AuthContext, require_read_open
from core.limiter import limiter
from database import (
    AssetTrendSnapshot,
    FredYield,
    OsintArticle,
    SignalEvent,
    WebSearchSnapshot,
    get_db,
)

router = APIRouter()


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def build_timeline(
    db: Session,
    *,
    asset: str | None,
    from_dt: datetime,
    to_dt: datetime,
    limit: int = 200,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    sym = (asset or "").upper().strip() or None

    # Signal events
    q = select(SignalEvent).where(
        SignalEvent.timestamp >= from_dt,
        SignalEvent.timestamp <= to_dt,
    )
    if sym:
        q = q.where(or_(SignalEvent.asset_symbol == sym, SignalEvent.asset_symbol == "SYSTEM"))
    for ev in db.execute(q.order_by(desc(SignalEvent.timestamp)).limit(limit)).scalars().all():
        items.append(
            {
                "kind": "event",
                "ts": ev.timestamp.isoformat() if ev.timestamp else None,
                "asset": ev.asset_symbol,
                "title": ev.title,
                "summary": ev.summary,
                "severity": ev.severity,
                "event_type": ev.event_type,
            }
        )

    # Trend score samples (sparse — one per window of snapshots)
    tq = select(AssetTrendSnapshot).where(
        AssetTrendSnapshot.timestamp >= from_dt,
        AssetTrendSnapshot.timestamp <= to_dt,
    )
    if sym:
        tq = tq.where(AssetTrendSnapshot.asset_symbol == sym)
    for row in db.execute(tq.order_by(desc(AssetTrendSnapshot.timestamp)).limit(min(limit, 50))).scalars().all():
        items.append(
            {
                "kind": "score",
                "ts": row.timestamp.isoformat() if row.timestamp else None,
                "asset": row.asset_symbol,
                "title": f"Signal score {getattr(row, 'signal_score', None)}",
                "summary": f"band={getattr(row, 'signal_band', None)} depeg={getattr(row, 'depeg_index', None)}",
                "severity": "info",
                "event_type": "score_snapshot",
            }
        )

    # OSINT
    oq = select(OsintArticle).where(
        OsintArticle.published_at >= from_dt,
        OsintArticle.published_at <= to_dt,
    )
    for art in db.execute(oq.order_by(desc(OsintArticle.published_at)).limit(min(limit, 40))).scalars().all():
        items.append(
            {
                "kind": "osint",
                "ts": art.published_at.isoformat() if art.published_at else None,
                "asset": sym,
                "title": art.title,
                "summary": (art.summary or "")[:240],
                "severity": "info",
                "event_type": "osint",
                "url": getattr(art, "url", None),
            }
        )

    # Web search snapshots
    wq = select(WebSearchSnapshot).where(
        WebSearchSnapshot.fetched_at >= from_dt,
        WebSearchSnapshot.fetched_at <= to_dt,
    )
    for snap in db.execute(wq.order_by(desc(WebSearchSnapshot.fetched_at)).limit(20)).scalars().all():
        hit0 = (snap.hits or [{}])[0] if snap.hits else {}
        title = hit0.get("title") if isinstance(hit0, dict) else str(hit0)[:120]
        items.append(
            {
                "kind": "web_search",
                "ts": snap.fetched_at.isoformat() if snap.fetched_at else None,
                "asset": sym,
                "title": title or f"Web search {snap.query_key}",
                "summary": f"provider={snap.provider} hits={len(snap.hits or [])}",
                "severity": "info",
                "event_type": "web_search",
            }
        )

    # FRED yields (macro context — date-only; attach at noon UTC)
    fq = select(FredYield).where(FredYield.date >= from_dt.date().isoformat(), FredYield.date <= to_dt.date().isoformat())
    for fy in db.execute(fq.order_by(desc(FredYield.date)).limit(30)).scalars().all():
        try:
            day = datetime.fromisoformat(str(fy.date)).replace(tzinfo=timezone.utc) + timedelta(hours=12)
        except Exception:
            continue
        if day < from_dt or day > to_dt:
            continue
        items.append(
            {
                "kind": "macro",
                "ts": day.isoformat(),
                "asset": "MACRO",
                "title": f"{fy.series_name or fy.series_id}: {fy.value}",
                "summary": f"FRED {fy.series_id}",
                "severity": "info",
                "event_type": "fred_yield",
            }
        )

    items.sort(key=lambda x: x.get("ts") or "", reverse=True)
    return items[:limit]


def co_occurrence(
    items: list[dict[str, Any]],
    *,
    hours: int = 6,
) -> list[dict[str, Any]]:
    """Simple ±N hour co-occurrence between events and OSINT/web_search (rules, not ML)."""
    parsed: list[tuple[datetime, dict[str, Any]]] = []
    for it in items:
        ts = _parse_iso(it.get("ts"))
        if ts:
            parsed.append((ts, it))
    pairs: list[dict[str, Any]] = []
    window = timedelta(hours=hours)
    events = [(t, i) for t, i in parsed if i.get("kind") == "event"]
    others = [(t, i) for t, i in parsed if i.get("kind") in ("osint", "web_search", "macro")]
    for et, ev in events[:50]:
        near = []
        for ot, oth in others:
            if abs((ot - et).total_seconds()) <= window.total_seconds():
                near.append({"kind": oth["kind"], "title": oth.get("title"), "ts": oth.get("ts")})
        if near:
            pairs.append(
                {
                    "event_title": ev.get("title"),
                    "event_ts": ev.get("ts"),
                    "event_type": ev.get("event_type"),
                    "nearby": near[:8],
                }
            )
    return pairs[:40]


@router.get("/v1/timeline")
@limiter.limit("60/minute")
def api_timeline(
    request: Request,
    asset: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    include_cooccurrence: bool = Query(False),
    db: Session = Depends(get_db),
    _auth: AuthContext = Depends(require_read_open("events:read", "osint:read", "intelligence:read")),
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    to_dt = _parse_iso(to) or now
    from_dt = _parse_iso(from_) or (to_dt - timedelta(hours=168))
    if from_dt > to_dt:
        from_dt, to_dt = to_dt, from_dt

    # Clamp by API key history policy when present
    if _auth.kind == "api_key" and _auth.access_policy:
        from core.api_auth import clamp_history_hours

        max_h = clamp_history_hours(_auth, int((to_dt - from_dt).total_seconds() / 3600) or 1)
        from_dt = to_dt - timedelta(hours=max_h)

    items = build_timeline(db, asset=asset, from_dt=from_dt, to_dt=to_dt)
    out: dict[str, Any] = {
        "asset": (asset or "").upper() or None,
        "from": from_dt.isoformat(),
        "to": to_dt.isoformat(),
        "items": items,
    }
    if include_cooccurrence:
        out["co_occurrence"] = co_occurrence(items)
    return out
