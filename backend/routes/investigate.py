"""POST /api/v1/investigate — address investigation route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.admin_auth import require_admin_token
from database import get_db
from schemas import InvestigateRequest, InvestigationReportOut

router = APIRouter()


@router.post("/investigate", response_model=InvestigationReportOut, dependencies=[Depends(require_admin_token)])
async def investigate(body: InvestigateRequest, db: Session = Depends(get_db)):
    from services.investigation_engine import run_investigation
    report = await run_investigation(db, body.address, body.chain, body.asset)
    return InvestigationReportOut(**{
        "seed_address": report.seed_address,
        "chain": report.chain,
        "asset_symbol": report.asset_symbol,
        "peel_hops": report.peel_hops,
        "cluster": report.cluster,
        "bridge_hops": report.bridge_hops,
        "blacklist_hits": report.blacklist_hits,
        "osint_articles": report.osint_articles,
        "total_value_usd": report.total_value_usd,
        "timeline": report.timeline,
        "narrative": report.narrative,
        "risk_level": report.risk_level,
        "generated_at": report.generated_at,
        "errors": report.errors,
    })
