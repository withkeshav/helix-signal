"""Insight asset API routes (WO-DA-4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from core.limiter import limiter
from database import get_db
from services.insight_assets import VALID_KINDS, export_insights_ndjson, get_insight_response

router = APIRouter()


@router.get("/insights/{kind}")
@limiter.limit("60/minute")
def get_insight(
    request: Request,
    kind: str,
    asset: str = Query("USDT"),
    db: Session = Depends(get_db),
) -> dict:
    """Return versioned insight object; deterministic payload always present."""
    if kind not in VALID_KINDS:
        raise HTTPException(status_code=404, detail=f"Unknown insight kind: {kind}")
    try:
        return get_insight_response(db, kind, asset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/insights/{kind}/export")
@limiter.limit("10/minute")
def export_insights(
    request: Request,
    kind: str,
    format: str = Query("ndjson", pattern="^(ndjson|csv)$"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    if kind not in VALID_KINDS:
        raise HTTPException(status_code=404, detail=f"Unknown insight kind: {kind}")
    if format == "ndjson":
        body = export_insights_ndjson(db, kind, limit=limit)
        return PlainTextResponse(body, media_type="application/x-ndjson")
    import csv
    import io
    import json

    rows = []
    for line in export_insights_ndjson(db, kind, limit=limit).splitlines():
        if line.strip():
            rows.append(json.loads(line))
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in row.items()})
    return PlainTextResponse(buf.getvalue(), media_type="text/csv")
