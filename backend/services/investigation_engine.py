"""Investigation engine — ZachXBT-style report generator.

Pipeline: peel_chain → address_clustering → bridge_hop_tracker
          → blacklist_events → OSINT articles → LLM narrative

Now uses select() exclusively (SA 2.0 style).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from structlog import get_logger

log = get_logger(__name__)


INVESTIGATION_TIMEOUT_SECONDS = 60


@dataclass
class InvestigationReport:
    seed_address: str
    chain: str
    asset_symbol: str
    peel_hops: list[dict] = field(default_factory=list)
    cluster: dict[str, Any] = field(default_factory=dict)
    bridge_hops: list[dict] = field(default_factory=list)
    blacklist_hits: list[dict] = field(default_factory=list)
    osint_articles: list[dict] = field(default_factory=list)
    total_value_usd: float = 0.0
    timeline: list[dict] = field(default_factory=list)
    narrative: str = ""
    risk_level: str = "LOW"
    generated_at: str = ""
    errors: list[str] = field(default_factory=list)


async def run_investigation(
    db: Session,
    address: str,
    chain: str = "ethereum",
    asset_symbol: str = "USDT",
) -> InvestigationReport:
    import asyncio

    report = InvestigationReport(
        seed_address=address,
        chain=chain,
        asset_symbol=asset_symbol,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    try:
        return await asyncio.wait_for(
            _run_pipeline(report, db, address, chain, asset_symbol),
            timeout=INVESTIGATION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        report.errors.append("pipeline_timeout")
        report.narrative = "Investigation timed out — partial results available."
        return report


async def _run_pipeline(
    report: InvestigationReport,
    db: Session,
    address: str,
    chain: str,
    asset_symbol: str,
) -> InvestigationReport:
    # 1. Peel chain
    try:
        from chain.intelligence.peel_chain_detector import detect_peel_chain
        peel = await detect_peel_chain(db, address, chain=chain, asset_symbol=asset_symbol)
        if peel.get("status") == "peel_chain_detected":
            report.peel_hops = peel.get("hops", [])
            report.total_value_usd += peel.get("total_value_usd", 0)
    except Exception as e:
        log.warning("investigation.step_failed", step="peel_chain", error=str(e))
        report.errors.append("peel_chain_failed")

    # 2. Address clustering
    try:
        from chain.intelligence.address_clustering import cluster_addresses
        report.cluster = cluster_addresses(db, address, chain=chain)
    except Exception as e:
        log.warning("investigation.step_failed", step="address_clustering", error=str(e))
        report.errors.append("address_clustering_failed")

    # 3. Bridge hop tracker
    try:
        from chain.intelligence.bridge_hop_tracker import track_bridge_hops
        bridges = await track_bridge_hops(db, address, chain=chain)
        report.bridge_hops = bridges.get("bridge_hops", [])
    except Exception as e:
        log.warning("investigation.step_failed", step="bridge_hops", error=str(e))
        report.errors.append("bridge_hops_failed")

    # 4. Blacklist events
    try:
        from database import BlacklistEvent
        blacklist_rows = (
            db.execute(
                select(BlacklistEvent)
                .where(
                    BlacklistEvent.chain == chain,
                    BlacklistEvent.frozen_address.ilike(f"%{address[-20:]}%"),
                )
                .order_by(BlacklistEvent.timestamp.desc())
                .limit(20)
            ).scalars().all()
        )
        for ev in blacklist_rows:
            hit = {
                "event_id": ev.id,
                "asset_symbol": ev.asset_symbol,
                "frozen_address": ev.frozen_address,
                "frozen_balance_usd": ev.frozen_balance_usd,
                "event_type": ev.event_type,
                "tx_hash": ev.tx_hash,
                "intelligence_note": ev.intelligence_note,
                "timestamp": ev.timestamp.isoformat() if ev.timestamp else "",
            }
            report.blacklist_hits.append(hit)

        for hop in report.peel_hops:
            addr = hop.get("next_address", "")
            if addr:
                extra = (
                    db.execute(
                        select(BlacklistEvent)
                        .where(
                            BlacklistEvent.chain == chain,
                            BlacklistEvent.frozen_address.ilike(f"%{addr[-20:]}%"),
                        )
                    ).scalars().first()
                )
                if extra:
                    report.blacklist_hits.append({
                        "event_id": extra.id,
                        "asset_symbol": extra.asset_symbol,
                        "frozen_address": extra.frozen_address,
                        "frozen_balance_usd": extra.frozen_balance_usd,
                        "event_type": extra.event_type,
                        "tx_hash": extra.tx_hash,
                        "intelligence_note": extra.intelligence_note,
                        "timestamp": extra.timestamp.isoformat() if extra.timestamp else "",
                    })
    except Exception as e:
        log.warning("investigation.step_failed", step="blacklist", error=str(e))
        report.errors.append("blacklist_failed")

    # 5. OSINT articles
    try:
        from database import OsintArticle, OsintArticleAsset
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        article_ids = select(OsintArticleAsset.article_id).where(
            OsintArticleAsset.asset_symbol == asset_symbol
        )
        articles = (
            db.execute(
                select(OsintArticle)
                .where(
                    OsintArticle.id.in_(article_ids),
                    OsintArticle.published_at >= cutoff,
                    OsintArticle.event_type.in_([
                        "DEPEG_CONFIRMED", "PROTOCOL_EXPLOIT",
                        "ISSUER_FREEZE", "SANCTIONS_ACTION",
                    ]),
                )
                .order_by(OsintArticle.published_at.desc())
                .limit(10)
            ).scalars().all()
        )
        for art in articles:
            report.osint_articles.append({
                "article_id": art.id,
                "title": art.title[:100],
                "source": art.source,
                "event_type": art.event_type,
                "published_at": art.published_at.isoformat() if art.published_at else "",
                "sentiment_score": art.sentiment_score,
            })
    except Exception as e:
        log.warning("investigation.step_failed", step="osint", error=str(e))
        report.errors.append("osint_failed")

    # 6. Timeline — merge all events sorted by timestamp
    for hop in report.peel_hops:
        report.timeline.append({
            "timestamp": "",
            "event_type": "peel_hop",
            "detail": f"Hop to {hop.get('next_address', '')[:10]}... value=${hop.get('value_usd', 0):,.0f}",
        })
    for b in report.bridge_hops:
        report.timeline.append({
            "timestamp": "",
            "event_type": "bridge_hop",
            "detail": f"{b.get('bridge', '')} ({b.get('risk', '')} risk)",
        })
    for h in report.blacklist_hits:
        report.timeline.append({
            "timestamp": h.get("timestamp", ""),
            "event_type": "blacklist",
            "detail": f"${h.get('frozen_balance_usd', 0):,.0f} frozen in {h.get('tx_hash', '')[:10]}...",
        })
    for a in report.osint_articles:
        report.timeline.append({
            "timestamp": a.get("published_at", ""),
            "event_type": "osint",
            "detail": f"[{a.get('event_type', '')}] {a.get('title', '')[:60]}",
        })

    report.timeline.sort(key=lambda t: t.get("timestamp", ""))

    # 7. Risk level
    report.risk_level = _compute_risk_level(report)

    # 8. LLM narrative
    summary_dict = {
        "peel_hops": len(report.peel_hops),
        "cluster_size": report.cluster.get("cluster_size", 0),
        "bridge_hops": [b.get("bridge") for b in report.bridge_hops],
        "blacklist_hits": len(report.blacklist_hits),
        "osint_articles": len(report.osint_articles),
        "total_value_usd": report.total_value_usd,
        "risk_level": report.risk_level,
    }
    try:
        from services.ai_router import chat_for_feature
        prompt = (
            f"You are a crypto forensics analyst. Summarize the following "
            f"investigation findings in 3 sentences for a compliance officer. "
            f"Focus on risk level, fund flow pattern, and recommended action. "
            f"Data: {json.dumps(summary_dict)}"
        )
        import asyncio
        result = await asyncio.to_thread(
            chat_for_feature,
            db=db,
            feature="anomaly_investigation",
            prompt=prompt,
            system="You are a compliance-focused blockchain forensics analyst. Be concise.",
            max_tokens=200,
        )
        if result and result.get("text"):
            report.narrative = result["text"].strip()
    except Exception:
        log.exception("investigation.narrative_failed")
        report.narrative = "Analysis in progress."

    return report


def _compute_risk_level(report: InvestigationReport) -> str:
    privacy_bridges = {"tornado_cash", "railgun"}
    for b in report.bridge_hops:
        if b.get("bridge", "").lower() in privacy_bridges:
            return "CRITICAL"
    if report.blacklist_hits:
        return "CRITICAL"
    if len(report.peel_hops) > 5:
        return "CRITICAL"

    high_risk_bridges = {"tornado_cash", "railgun"}
    for b in report.bridge_hops:
        if b.get("risk") == "high":
            return "HIGH"
    if report.total_value_usd > 1_000_000:
        return "HIGH"

    if report.peel_hops or report.cluster.get("cluster_size", 0) > 3:
        return "MEDIUM"

    return "LOW"
