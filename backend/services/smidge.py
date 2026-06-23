"""SMIDGE score card — combines Bluechip M/I/G with locally computed S/D/E."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from signal_engine import scoring
from signal_engine.metrics import compute_asset_metric_bundle
from sources.bluechip import fetch_bluechip_ratings


def _stability_score(*, depeg_index: int, price: float | None) -> int:
    """S — peg stability from depeg index (inverted: lower depeg = higher stability)."""
    base = max(0, 100 - int(depeg_index))
    if price is not None:
        _, pct = scoring.peg_deviation(price)
        if pct > 1.0:
            base = max(0, base - 15)
    return base


def _decentralization_score(hhi: float | None) -> int:
    """D — decentralization from chain HHI (lower HHI = higher score)."""
    if hhi is None:
        return 50
    if hhi <= 2000:
        return 90
    if hhi <= 4000:
        return 70
    if hhi <= 7000:
        return 45
    return 25


def _externals_score(sentiment: float | None, *, nlp_enabled: bool) -> int:
    """E — external sentiment when NLP enabled."""
    if not nlp_enabled or sentiment is None:
        return 50
    # Map -1..1 to 0..100
    return int(max(0, min(100, (sentiment + 1.0) * 50)))


def compute_smidge(db: Session, *, asset_symbol: str) -> dict[str, Any]:
    sym = asset_symbol.upper()
    bundle = compute_asset_metric_bundle(db, asset_symbol=sym)
    if bundle is None:
        return {"asset_symbol": sym, "available": False}

    from providers.settings import get_setting
    api_key = get_setting("bluechip_api_key", db)
    bluechip = fetch_bluechip_ratings(sym, api_key=str(api_key) if api_key else None)

    hhi = None
    rk = bundle.risk_kwargs or {}
    chain_shares = rk.get("chain_shares") or []
    if chain_shares:
        _, conc_detail = scoring.concentration_component(chain_shares)
        hhi = conc_detail.get("hhi")

    nlp_enabled = bool(get_setting("feature_nlp_sentiment", db))
    sentiment = None
    if nlp_enabled:
        try:
            from database import OsintArticle
            from sqlalchemy import desc

            row = (
                db.query(OsintArticle)
                .filter(OsintArticle.asset_symbol == sym, OsintArticle.sentiment_score.isnot(None))
                .order_by(desc(OsintArticle.published_at))
                .first()
            )
            if row:
                sentiment = float(row.sentiment_score)
        except Exception:
            sentiment = None

    dimensions = {
        "S": _stability_score(depeg_index=bundle.depeg_index, price=bundle.price),
        "M": bluechip.get("management"),
        "I": bluechip.get("implementation"),
        "D": _decentralization_score(hhi),
        "G": bluechip.get("governance"),
        "E": _externals_score(sentiment, nlp_enabled=nlp_enabled),
    }

    scores = [v for v in dimensions.values() if v is not None]
    composite = round(sum(scores) / len(scores)) if scores else None

    return {
        "asset_symbol": sym,
        "available": True,
        "dimensions": dimensions,
        "composite_score": composite,
        "bluechip": bluechip,
        "labels": {
            "S": "Stability",
            "M": "Management",
            "I": "Implementation",
            "D": "Decentralization",
            "G": "Governance",
            "E": "Externals",
        },
    }
