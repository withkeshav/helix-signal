"""Shared metric computation for dashboard and historical snapshots."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from database import AssetChainSnapshot, SourceStatus
from signal_engine import scoring
from signal_engine.core import get_asset_by_symbol


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _chain_key(name: str) -> str:
    return str(name).strip().lower().replace(" ", "-")


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


def compute_asset_metric_bundle(
    db: Session,
    *,
    asset_symbol: str,
    refresh_interval_seconds: int | None = None,
) -> AssetMetricBundle | None:
    """Replicate dashboard signal inputs for one enabled asset (read-only on db)."""
    if refresh_interval_seconds is None:
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

    newest_chain_snapshot = max((_utc(c.fetched_at) for c in chains_orm), default=None) if chains_orm else None
    freshness_dict = scoring.compute_freshness(
        source_status=source_status,
        last_successful_fetch=_utc(defillama.last_successful_fetch) if defillama else None,
        newest_chain_snapshot=newest_chain_snapshot,
        refresh_interval_seconds=refresh_interval_seconds,
    )
    age_seconds = freshness_dict.get("age_seconds")

    raw_total = sum((c.supply_current or 0.0) for c in chains_orm)
    total_supply = raw_total if raw_total > 0 else None
    total_prev_day = sum((c.supply_prev_day or 0.0) for c in chains_orm)
    total_prev_week = sum((c.supply_prev_week or 0.0) for c in chains_orm)
    total_prev_month = sum((c.supply_prev_month or 0.0) for c in chains_orm)

    chain_shares: list[float] = []
    if total_supply and total_supply > 0:
        for c in chains_orm:
            if c.supply_current is not None and c.supply_current > 0:
                chain_shares.append(float(c.supply_current) / float(total_supply))

    price = next((c.price for c in chains_orm if c.price is not None), None)
    depeg_index = scoring.depeg_index_score(price)

    asset_signal_dict = scoring.compute_asset_signal(
        price=price,
        supply_current=float(total_supply or 0.0),
        supply_prev_day=total_prev_day if total_prev_day > 0 else None,
        supply_prev_week=total_prev_week if total_prev_week > 0 else None,
        supply_prev_month=total_prev_month if total_prev_month > 0 else None,
        chain_shares=chain_shares,
        source_ok=source_ok,
        source_error=source_error,
        age_seconds=age_seconds,
        refresh_interval_seconds=refresh_interval_seconds,
    )
    conc_s, conc_detail = scoring.concentration_component(chain_shares)
    dc_block = (asset_signal_dict.get("components") or {}).get("data_confidence") or {}
    dc_label = str(dc_block.get("label") or "Unknown")
    dc_score = int(dc_block.get("score") or 0)

    now = datetime.now(timezone.utc)
    chain_rows: list[ChainMetricRow] = []
    for c in chains_orm:
        fetched = _utc(c.fetched_at)
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
                chain_key=_chain_key(name),
                supply_current=c.supply_current,
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
    )

