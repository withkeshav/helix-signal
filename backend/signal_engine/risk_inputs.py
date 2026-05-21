"""Shared risk-score input extraction for dashboard and trend pipelines."""

from __future__ import annotations

from typing import Any

from database import AssetChainSnapshot
from signal_engine import scoring
from signal_engine.core import cross_source_price_check
from signal_engine.metrics_v3 import estimate_slippage


def _aggregate_supply_totals(chains_orm: list[AssetChainSnapshot]) -> tuple[float | None, float, float, float]:
    raw_total = sum((c.supply_current or 0.0) for c in chains_orm)
    total_supply = raw_total if raw_total > 0 else None
    total_prev_day = sum((c.supply_prev_day or 0.0) for c in chains_orm)
    total_prev_week = sum((c.supply_prev_week or 0.0) for c in chains_orm)
    total_prev_month = sum((c.supply_prev_month or 0.0) for c in chains_orm)
    return total_supply, total_prev_day, total_prev_week, total_prev_month


def _chain_shares(chains_orm: list[AssetChainSnapshot], total_supply: float | None) -> list[float]:
    if not total_supply or total_supply <= 0:
        return []
    shares: list[float] = []
    for c in chains_orm:
        if c.supply_current is not None and c.supply_current > 0:
            shares.append(float(c.supply_current) / float(total_supply))
    return shares


def _aggregate_tvl_change_24h_pct(chains_orm: list[AssetChainSnapshot]) -> float | None:
    """TVL 24h change from chain TVL fields only (not circulating supply)."""
    current = sum((c.tvl or 0.0) for c in chains_orm)
    if current <= 0:
        return None
    # Snapshots store current TVL only; without historical TVL in-row we cannot compute
    # a true 24h TVL delta here. Return None so liquidity scoring is not misled by supply deltas.
    return None


def _aggregate_liquidity_metrics(chains_orm: list[AssetChainSnapshot]) -> tuple[float, float, float | None]:
    total_liq = sum((c.total_liquidity_usd or 0.0) for c in chains_orm)
    pool_shares = [c.top3_pool_share_pct for c in chains_orm if c.top3_pool_share_pct is not None]
    top3_pool_share_pct: float | None = None
    if pool_shares:
        # Weight by per-chain liquidity when available, else max concentration signal.
        weights = [(c.top3_pool_share_pct, c.total_liquidity_usd or 0.0) for c in chains_orm if c.top3_pool_share_pct is not None]
        wsum = sum(w for _, w in weights)
        if wsum > 0:
            top3_pool_share_pct = sum(p * w for p, w in weights) / wsum
        else:
            top3_pool_share_pct = max(pool_shares)

    slippage_10k_bps = 0.0
    slippage_100k_bps = 0.0
    if total_liq > 0:
        half = total_liq / 2.0
        slippage_10k_bps = estimate_slippage(size_usd=10_000.0, pool_reserve_a=half, pool_reserve_b=half)
        slippage_100k_bps = estimate_slippage(size_usd=100_000.0, pool_reserve_a=half, pool_reserve_b=half)
    return slippage_10k_bps, slippage_100k_bps, top3_pool_share_pct


def _cross_source_fields(chains_orm: list[AssetChainSnapshot]) -> tuple[int, float]:
    prices: dict[str, float | None] = {}
    for c in chains_orm:
        if c.price is not None:
            prices.setdefault("defillama", c.price)
        if c.price_coingecko is not None:
            prices["coingecko"] = c.price_coingecko
        if c.price_dexscreener is not None:
            prices["dexscreener"] = c.price_dexscreener
        break
    # Use first chain row that has multi-source prices; extend with any chain missing keys
    for c in chains_orm:
        if c.price_coingecko is not None:
            prices["coingecko"] = c.price_coingecko
        if c.price_dexscreener is not None:
            prices["dexscreener"] = c.price_dexscreener
        if c.price is not None and "defillama" not in prices:
            prices["defillama"] = c.price
    check = cross_source_price_check(prices)
    agreement = int(check.get("sources_agreeing") or 0)
    discrepancy = float(check.get("max_discrepancy_pct") or 0.0)
    return agreement, discrepancy


def build_risk_score_kwargs(
    chains_orm: list[AssetChainSnapshot],
    *,
    source_ok: bool,
    source_error: str | None,
    age_seconds: float | None,
    refresh_interval_seconds: int,
    attestation_age_days: float | None = None,
) -> dict[str, Any]:
    """Single source of truth for compute_risk_score() inputs."""
    total_supply, total_prev_day, total_prev_week, total_prev_month = _aggregate_supply_totals(chains_orm)
    chain_shares = _chain_shares(chains_orm, total_supply)
    price = next((c.price for c in chains_orm if c.price is not None), None)
    slippage_10k, slippage_100k, top3_pool = _aggregate_liquidity_metrics(chains_orm)
    tvl_change = _aggregate_tvl_change_24h_pct(chains_orm)
    cross_agreement, cross_disc = _cross_source_fields(chains_orm)

    return dict(
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
        slippage_10k_bps=slippage_10k,
        slippage_100k_bps=slippage_100k,
        top3_pool_share_pct=top3_pool,
        top3_dex_pool_share=top3_pool,
        tvl_change_24h_pct=tvl_change,
        cross_source_agreement=cross_agreement,
        cross_source_discrepancy_pct=cross_disc,
        attestation_age_days=attestation_age_days,
    )


def compute_unified_risk_score(
    chains_orm: list[AssetChainSnapshot],
    *,
    source_ok: bool,
    source_error: str | None,
    age_seconds: float | None,
    refresh_interval_seconds: int,
    attestation_age_days: float | None = None,
) -> dict[str, Any]:
    kwargs = build_risk_score_kwargs(
        chains_orm,
        source_ok=source_ok,
        source_error=source_error,
        age_seconds=age_seconds,
        refresh_interval_seconds=refresh_interval_seconds,
        attestation_age_days=attestation_age_days,
    )
    return scoring.compute_risk_score(**kwargs)
