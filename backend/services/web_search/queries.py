"""Minimal stablecoin-focused query set (budget-aware)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session
from structlog import get_logger

log = get_logger(__name__)


def build_query_plan(db: Session) -> list[dict[str, str]]:
    """Return list of {query_key, query_text} — global always; assets only if stressed."""
    plan = [
        {
            "query_key": "global_news",
            "query_text": "stablecoin depeg OR USDT USDC market news regulation",
        },
        {
            "query_key": "issuer_news",
            "query_text": "Tether OR Circle reserve attestation OR freeze blacklist stablecoin",
        },
    ]

    # Risk-triggered asset queries (max 2)
    try:
        from signal_engine.core import load_enabled_assets
        from services.dashboard import build_dashboard_response

        assets = [str(a.get("symbol", "")).upper() for a in load_enabled_assets(db) if a.get("symbol")]
        stressed: list[tuple[str, float]] = []
        for sym in assets[:8]:
            try:
                dash = build_dashboard_response(db, sym)
                band = (dash.asset_signal.band or "Normal").lower()
                score = float(dash.asset_signal.score or 0)
                if band in ("watch", "risk", "warning", "critical") or score >= 40:
                    stressed.append((sym, score))
            except Exception:
                continue
        stressed.sort(key=lambda x: -x[1])
        for sym, _ in stressed[:2]:
            plan.append(
                {
                    "query_key": f"asset:{sym}",
                    "query_text": f"{sym} stablecoin news depeg regulation OR freeze",
                }
            )
    except Exception:
        log.warning("web_search.query_plan_assets_failed", exc_info=True)

    return plan
