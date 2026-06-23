"""Shared metric computation for dashboard and historical snapshots."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from database import AssetChainSnapshot, SourceStatus
from signal_engine import scoring
from signal_engine.core import get_asset_by_symbol
from signal_engine.risk_inputs import build_risk_score_kwargs, compute_unified_risk_score
from utils import utc_normalize, chain_key_from_name


@dataclass
class ChainMetricRow:
    chain_name: str
    chain_key: str
    supply_current: float | None
    supply_share_pct: float | None
    chain_tvl: float | None
    chain_signal_score: int
    chain_signal_band: str
    data_confidence_score: int
    data_confidence_label: str
    supply_prev_day: float | None = None
    supply_prev_week: float | None = None
    supply_prev_month: float | None = None


@dataclass
class AssetMetricBundle:
    asset_symbol: str
    total_supply: float | None
    price: float | None
    depeg_index: int
    signal_score: int
    signal_band: str
    concentration_score: int
    top_chain_share_pct: float | None
    data_confidence_label: str
    data_confidence_score: int
    source_status: str
    source_ok: bool
    source_error: str | None
    freshness_age_seconds: float | None
    chains: list[ChainMetricRow]
    risk_kwargs: dict | None = None


def compute_asset_metric_bundle(
    db: Session,
    *,
    asset_symbol: str,
    refresh_interval_seconds: int | None = None,
) -> AssetMetricBundle | None:
    """Replicate dashboard signal inputs for one enabled asset (read-only on db)."""
    if refresh_interval_seconds is None:
        try:
            from providers.settings import get_setting
            refresh_interval_seconds = int(get_setting("refresh_core_seconds") or 300)
        except Exception:
            refresh_interval_seconds = int(os.getenv("REFRESH_INTERVAL_SECONDS", "300"))

    sym = asset_symbol.upper()
    selected_asset = get_asset_by_symbol(sym)
    if selected_asset is None or not bool(selected_asset.get("enabled")):
        return None

    chains_orm = (
        db.query(AssetChainSnapshot)
        .filter(AssetChainSnapshot.asset_symbol == sym)
        .order_by(AssetChainSnapshot.supply_current.desc(), AssetChainSnapshot.chain_name.asc())
        .all()
    )
    sources_orm = db.query(SourceStatus).order_by(SourceStatus.id.asc()).all()
    defillama = next((s for s in sources_orm if s.source_name == "defillama"), None)
    source_status = defillama.status if defillama else "unknown"
    source_ok = defillama is not None and defillama.status == "ok"
    source_error = defillama.last_error if defillama else None

    newest_chain_snapshot = max((utc_normalize(c.fetched_at) for c in chains_orm), default=None) if chains_orm else None
    freshness_dict = scoring.compute_freshness(
        source_status=source_status,
        last_successful_fetch=utc_normalize(defillama.last_successful_fetch) if defillama else None,
        newest_chain_snapshot=newest_chain_snapshot,
        refresh_interval_seconds=refresh_interval_seconds,
    )
    age_seconds = freshness_dict.get("age_seconds")

    raw_total = sum((c.supply_current or 0.0) for c in chains_orm)
    total_supply = raw_total if raw_total > 0 else None

    risk_kwargs = build_risk_score_kwargs(
        chains_orm,
        source_ok=source_ok,
        source_error=source_error,
        age_seconds=age_seconds,
        refresh_interval_seconds=refresh_interval_seconds,
    )
    price = risk_kwargs.get("price")
    chain_shares = risk_kwargs.get("chain_shares") or []
    depeg_index = scoring.depeg_index_score(price)

    asset_signal_dict = compute_unified_risk_score(
        chains_orm,
        source_ok=source_ok,
        source_error=source_error,
        age_seconds=age_seconds,
        refresh_interval_seconds=refresh_interval_seconds,
        db=db,
        asset_symbol=sym,
    )
    conc_s, conc_detail = scoring.concentration_component(
        chain_shares,
        top3_dex_pool_share=risk_kwargs.get("top3_dex_pool_share"),
    )
    dc_block = (asset_signal_dict.get("components") or {}).get("observability") or {}
    dc_label = str(dc_block.get("label") or "Unknown")
    dc_score = int(dc_block.get("score") or 0)

    now = datetime.now(timezone.utc)
    chain_rows: list[ChainMetricRow] = []
    for c in chains_orm:
        fetched = utc_normalize(c.fetched_at)
        age_s = (now - fetched).total_seconds() if fetched else None
        share_pct = (
            (float(c.supply_current) / float(total_supply)) * 100.0
            if total_supply and c.supply_current is not None and total_supply > 0
            else None
        )
        cur_supply = float(c.supply_current or 0.0)
        mom_hint, _ = scoring.supply_momentum_component(
            supply_current=cur_supply,
            supply_prev_day=c.supply_prev_day,
            supply_prev_week=c.supply_prev_week,
            supply_prev_month=c.supply_prev_month,
        )
        cs_raw = scoring.chain_row_signal(
            chain_share_pct=share_pct,
            peg_price=c.price,
            momentum_score_hint=mom_hint,
        )
        dc_raw = scoring.chain_data_confidence(
            source_ok=source_ok,
            chain_snapshot_age_seconds=age_s,
            refresh_interval_seconds=refresh_interval_seconds,
        )
        name = str(c.chain_name)
        chain_rows.append(
            ChainMetricRow(
                chain_name=name,
                chain_key=chain_key_from_name(name),
                supply_current=c.supply_current,
                supply_prev_day=c.supply_prev_day,
                supply_prev_week=c.supply_prev_week,
                supply_prev_month=c.supply_prev_month,
                supply_share_pct=round(share_pct, 4) if share_pct is not None else None,
                chain_tvl=c.tvl,
                chain_signal_score=int(cs_raw["score"]),
                chain_signal_band=str(cs_raw["band"]),
                data_confidence_score=int(dc_raw["score"]),
                data_confidence_label=str(dc_raw["label"]),
            )
        )

    return AssetMetricBundle(
        asset_symbol=sym,
        total_supply=total_supply,
        price=price,
        depeg_index=depeg_index,
        signal_score=int(asset_signal_dict["score"]),
        signal_band=str(asset_signal_dict["band"]),
        concentration_score=int(conc_s),
        top_chain_share_pct=conc_detail.get("top_chain_share_pct"),
        data_confidence_label=dc_label,
        data_confidence_score=dc_score,
        source_status=source_status,
        source_ok=source_ok,
        source_error=source_error,
        freshness_age_seconds=age_seconds,
        chains=chain_rows,
        risk_kwargs=risk_kwargs,
    )

