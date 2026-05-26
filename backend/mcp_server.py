"""Official Model Context Protocol (MCP) server for Helix-Signal V4.

Exposes quantitative stablecoin intelligence tools to any MCP-compatible
agent (Stablescope, ClawTeam, Cline, etc.) via stdio transport.

Run standalone:
    python -m backend.mcp_server

Or include the FastMCP app in a uvicorn mount for SSE:
    from backend.mcp_server import mcp_app
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP

from database import AssetChainSnapshot, SessionLocal
from core.olap import get_duckdb
from services.olap_service import (
    compute_duckdb_correlations,
    compute_yield_capital_flight_correlations,
    compute_cross_chain_correlations,
)
from services.anomaly import detect_anomalies, emit_anomaly_events
from services.osint import get_attestation_status, get_sentiment_timeseries

mcp_app = FastMCP(
    "Helix-Signal",
    instructions="Quantitative stablecoin intelligence server. "
    "Tools query on-chain supply, macro yields, anomaly detection, and attestation status.",
    host="127.0.0.1",
    port=int(os.getenv("MCP_PORT", "8100")),
)


def _db_session():
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tool 1 — DuckDB OLAP correlations
# ---------------------------------------------------------------------------


@mcp_app.tool()
def query_duckdb_correlations(asset_symbol: str | None = None) -> list[dict[str, Any]]:
    """Compute pairwise Pearson correlations (price/supply, price/depeg, etc.)
    from the DuckDB OLAP asset_trend_snapshots table. Optionally filter by asset_symbol."""
    return compute_duckdb_correlations(asset_symbol=asset_symbol.upper() if asset_symbol else None)


# ---------------------------------------------------------------------------
# Tool 2 — Macro yield impact on stablecoin flows
# ---------------------------------------------------------------------------


@mcp_app.tool()
def get_macro_yield_impact(asset_symbol: str | None = None) -> list[dict[str, Any]]:
    """Cross-reference stablecoin supply/price trends against FRED T-Bill yields
    (DGS1MO, DGS3MO) stored in DuckDB. Returns correlation coefficients
    measuring capital flight sensitivity to TradFi yield changes."""
    return compute_yield_capital_flight_correlations(asset_symbol=asset_symbol.upper() if asset_symbol else None)


# ---------------------------------------------------------------------------
# Tool 3 — Asset health metrics from latest chain snapshot
# ---------------------------------------------------------------------------


@mcp_app.tool()
def get_asset_health_metrics(asset_symbol: str) -> dict[str, Any]:
    """Pull the latest quantitative variables for an asset from
    AssetChainSnapshot: per-chain supply, price, TVL, concentration, attestation."""
    sym = asset_symbol.upper()
    db = SessionLocal()
    try:
        rows = (
            db.query(AssetChainSnapshot)
            .filter(AssetChainSnapshot.asset_symbol == sym)
            .order_by(AssetChainSnapshot.supply_current.desc())
            .all()
        )
        if not rows:
            return {"asset_symbol": sym, "available": False, "note": "No data found"}

        chains = []
        total_supply = 0.0
        for r in rows:
            sup = r.supply_current or 0.0
            total_supply += sup
            chains.append({
                "chain": r.chain_name,
                "supply_current": r.supply_current,
                "supply_prev_day": r.supply_prev_day,
                "tvl": r.tvl,
                "price": r.price,
                "market_cap": r.market_cap,
                "peg_type": r.peg_type,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            })

        attestation = get_attestation_status(db).get(sym, {})
        con = get_duckdb()
        trend_count = con.execute(
            "SELECT count(*) FROM asset_trend_snapshots WHERE asset_symbol = ?", [sym]
        ).fetchone()[0]

        return {
            "asset_symbol": sym,
            "available": True,
            "chain_count": len(chains),
            "total_supply": round(total_supply, 2),
            "chains": chains,
            "attestation": {
                "status": attestation.get("attestation_status"),
                "last_report": attestation.get("attestation_last_report"),
                "age_days": attestation.get("attestation_age_days"),
            },
            "trend_snapshot_count": trend_count,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tool 4 — Bridge-aware anomaly check
# ---------------------------------------------------------------------------


@mcp_app.tool()
def run_bridge_aware_anomaly_check(asset_symbol: str) -> dict[str, Any]:
    """Execute context-aware anomaly detection (z-score + isolation forest
    + bridge-flow analysis) on the asset's trend history. Returns anomalies
    with z-scores; any z-score > 3 is flagged as a circuit-breaker event."""
    sym = asset_symbol.upper()
    db = SessionLocal()
    try:
        raw = detect_anomalies(db, asset_symbol=sym)
        if not raw.get("enabled", True):
            return raw

        emitted = emit_anomaly_events(db, asset_symbol=sym, anomalies=raw)
        db.commit()

        zscore_breached = False
        for metric_key in ("supply", "price"):
            items = raw.get("z_score", {}).get(metric_key, [])
            for item in items:
                if abs(item.get("z_score", 0)) > 3.0:
                    zscore_breached = True

        return {
            "asset_symbol": sym,
            "anomalies": raw.get("anomalies", []),
            "bridge_flow": raw.get("bridge_flow", {}),
            "z_score": raw.get("z_score", {}),
            "isolation_forest": raw.get("isolation_forest", {}),
            "events_emitted": emitted,
            "circuit_breaker_triggered": zscore_breached,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tool info registration
# ---------------------------------------------------------------------------

TOOL_MANIFEST = {
    "query_duckdb_correlations": {
        "description": "Compute pairwise Pearson correlations from OLAP trend snapshots",
        "parameters": {"asset_symbol": {"type": "string", "description": "Optional asset filter (e.g. USDT)"}},
    },
    "get_macro_yield_impact": {
        "description": "Cross-reference stablecoin flows against FRED T-Bill yields",
        "parameters": {"asset_symbol": {"type": "string", "description": "Optional asset filter"}},
    },
    "get_asset_health_metrics": {
        "description": "Pull latest chain snapshot metrics for an asset",
        "parameters": {"asset_symbol": {"type": "string", "description": "Asset symbol (e.g. USDT)"}},
    },
    "run_bridge_aware_anomaly_check": {
        "description": "Run z-score + isolation forest anomaly detection with bridge-flow awareness",
        "parameters": {"asset_symbol": {"type": "string", "description": "Asset symbol (e.g. USDT)"}},
    },
}


@mcp_app.tool()
def list_tools() -> list[dict[str, Any]]:
    """Return the tool manifest for agentic discovery."""
    return [{"name": k, **v} for k, v in TOOL_MANIFEST.items()]


if __name__ == "__main__":
    mcp_app.run(transport="stdio")
