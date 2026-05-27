"""Circuit-breaker AI trigger — invoked only when math detects z-score > 3.

Part of Phase 4 Agentic Orchestration: no periodic polling, no dumb cron.
The anomaly engine runs first (pure math). Only if it flags a statistically
significant event does this agent spend budget on LLM inference.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy.orm import Session
from structlog import get_logger

from database import SignalEvent
from services.ai_router import ai_mode, enrich_with_ai
from signal_engine.core import load_enabled_assets

log = get_logger(__name__)

MAX_ASSETS_PER_CYCLE = int(os.getenv("ANOMALY_AGENT_MAX_ASSETS", "5"))
INVESTIGATION_COOLDOWN_MINUTES = int(os.getenv("ANOMALY_INVESTIGATION_COOLDOWN_MINUTES", "30"))


def _recent_ai_investigation(db: Session, *, asset_symbol: str) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=INVESTIGATION_COOLDOWN_MINUTES)
    count = (
        db.query(SignalEvent)
        .filter(
            SignalEvent.asset_symbol == asset_symbol,
            SignalEvent.event_type == "ai_investigation",
            SignalEvent.timestamp >= cutoff,
        )
        .count()
    )
    return count > 0


def _circuit_breaker_triggered(anomalies: dict[str, Any]) -> bool:
    """Check if any z-score exceeds 3.0 in the anomaly results."""
    for metric_key in ("supply", "price"):
        items = anomalies.get("z_score", {}).get(metric_key, [])
        if isinstance(items, list):
            for item in items:
                if abs(item.get("z_score", 0)) > 3.0:
                    return True
    return False


def investigate_anomaly(
    db: Session,
    *,
    asset_symbol: str,
    anomaly_results: dict[str, Any],
) -> dict[str, Any]:
    """Build a context from anomaly results and invoke the SLM for investigation.

    Returns a briefing dict; also persists a SignalEvent with the AI response.
    """
    mode = ai_mode()
    if mode == "ai_off":
        return {"asset_symbol": asset_symbol, "investigated": False, "reason": "ai_off"}

    if _recent_ai_investigation(db, asset_symbol=asset_symbol):
        log.info("anomaly_agent.cooldown", asset=asset_symbol)
        return {"asset_symbol": asset_symbol, "investigated": False, "reason": "cooldown"}

    z_items = anomaly_results.get("z_score", {})
    anomalies = anomaly_results.get("anomalies", [])

    highest_z = 0.0
    for metric_key in ("supply", "price"):
        items = z_items.get(metric_key, [])
        if isinstance(items, list):
            for item in items:
                z = abs(item.get("z_score", 0))
                if z > highest_z:
                    highest_z = z

    anomaly_summary = "; ".join(
        f"{a.get('metric','?')} z={a.get('z_score',0):.1f}"
        for a in (anomalies or [])
    ) or "none"

    context = {
        "asset_symbol": asset_symbol,
        "feature": "anomaly_investigation",
        "z_score_max": round(highest_z, 2),
        "anomalies": anomaly_summary,
        "bridge_flow": anomaly_results.get("bridge_flow", {}),
    }

    result = enrich_with_ai(
        feature="anomaly_investigation",
        context=context,
        priority=True,
    )

    if not result.get("available"):
        log.info("anomaly_agent.skip", asset=asset_symbol, reason=result.get("reason"))
        return {"asset_symbol": asset_symbol, "investigated": False, **result}

    briefing_text = result.get("summary", "")

    event = SignalEvent(
        asset_symbol=asset_symbol,
        chain_key=None,
        event_type="ai_investigation",
        severity="warning" if highest_z > 3.0 else "info",
        title=f"{asset_symbol} anomaly investigation (z={highest_z:.1f})",
        summary=briefing_text[:497] + "…" if len(briefing_text) > 500 else briefing_text,
        old_value=None,
        new_value=None,
        delta=str(round(highest_z, 2)),
        threshold="3σ",
        timestamp=datetime.now(timezone.utc),
        metadata_json=json.dumps({
            "highest_z": round(highest_z, 2),
            "anomaly_results": {
                "z_score": z_items,
                "anomalies": anomalies,
                "bridge_flow": anomaly_results.get("bridge_flow", {}),
            },
            "ai_provider": result.get("provider"),
            "ai_model": result.get("model"),
            "tokens_used": result.get("tokens"),
        }),
    )
    db.add(event)
    db.commit()

    log.info("anomaly_agent.complete", asset=asset_symbol, z=round(highest_z, 2), provider=result.get("provider"))
    return {
        "asset_symbol": asset_symbol,
        "investigated": True,
        "highest_z": round(highest_z, 2),
        "summary": briefing_text,
        "provider": result.get("provider"),
        "tokens": result.get("tokens"),
    }


def run_circuit_breaker_cycle(db: Session) -> list[dict[str, Any]]:
    """Iterate enabled assets, run anomaly detection, and trigger AI on
    z-score breaches. Called from the background refresh loop."""
    mode = ai_mode()
    if mode == "ai_off":
        log.info("circuit_breaker.ai_off")
        return []

    assets = load_enabled_assets()
    if not assets:
        log.info("circuit_breaker.no_assets")
        return []

    from services.anomaly import detect_anomalies

    results: list[dict[str, Any]] = []
    count = 0

    for asset in assets:
        if count >= MAX_ASSETS_PER_CYCLE:
            log.warning("circuit_breaker.max_assets_reached", limit=MAX_ASSETS_PER_CYCLE)
            break

        sym = asset.get("symbol", "")
        if not sym:
            continue

        try:
            anomalies = detect_anomalies(db, asset_symbol=sym)
            if not anomalies.get("anomalies"):
                continue

            if not _circuit_breaker_triggered(anomalies):
                log.debug("circuit_breaker.zscore_below_threshold", asset=sym)
                continue

            r = investigate_anomaly(db, asset_symbol=sym, anomaly_results=anomalies)
            results.append(r)
            count += 1

        except Exception:
            log.exception("circuit_breaker.cycle_failed", asset=sym)

    return results
