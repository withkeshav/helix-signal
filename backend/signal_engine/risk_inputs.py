"""Shared risk-score input extraction for dashboard and trend pipelines."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import AssetChainSnapshot, FiatReserveSnapshot, CollateralSnapshot, YieldBearingSnapshot
from signal_engine import scoring
from signal_engine.core import cross_source_price_check
from signal_engine.metrics_v3 import estimate_slippage
from services.velocity import compute_supply_velocity

# --- V4 stablecoin taxonomy (24 coins × 4 types) ---

STABLECOIN_TAXONOMY = {
    # ---- Fiat-Backed (8) ----
    "USDT":  {"type": "fiat_backed", "sub_type": "offshore_issuer",   "yield_bearing": False},
    "USDC":  {"type": "fiat_backed", "sub_type": "regulated_us",      "yield_bearing": False},
    "PYUSD": {"type": "fiat_backed", "sub_type": "regulated_us",      "yield_bearing": False},
    "FDUSD": {"type": "fiat_backed", "sub_type": "offshore_issuer",   "yield_bearing": False},
    "GUSD":  {"type": "fiat_backed", "sub_type": "regulated_us",      "yield_bearing": False},
    "RLUSD": {"type": "fiat_backed", "sub_type": "regulated_us",      "yield_bearing": False},
    "USD1":  {"type": "fiat_backed", "sub_type": "political_actor",   "yield_bearing": False},
    "USDG":  {"type": "fiat_backed", "sub_type": "consortium",        "yield_bearing": False},
    # ---- Crypto-Collateralized (5) ----
    "DAI":   {"type": "crypto_collateralized", "sub_type": "multi_collateral", "yield_bearing": False},
    "USDS":  {"type": "crypto_collateralized", "sub_type": "sky_protocol",     "yield_bearing": False},
    "LUSD":  {"type": "crypto_collateralized", "sub_type": "eth_only",         "yield_bearing": False},
    "GHO":   {"type": "crypto_collateralized", "sub_type": "aave_backed",      "yield_bearing": False},
    "crvUSD":{"type": "crypto_collateralized", "sub_type": "llamma_amm",       "yield_bearing": False},
    # ---- Yield-Bearing (9) ----
    "USDY":     {"type": "yield_bearing", "sub_type": "tbill_tokenized",     "yield_bearing": True},
    "BUIDL":    {"type": "yield_bearing", "sub_type": "tbill_tokenized",     "yield_bearing": True},
    "USYC":     {"type": "yield_bearing", "sub_type": "tbill_tokenized",     "yield_bearing": True},
    "sDAI":     {"type": "yield_bearing", "sub_type": "defi_lending",        "yield_bearing": True},
    "sUSDS":    {"type": "yield_bearing", "sub_type": "defi_lending",        "yield_bearing": True},
    "aUSDC":    {"type": "yield_bearing", "sub_type": "defi_lending",        "yield_bearing": True},
    "syrupUSDC":{"type": "yield_bearing", "sub_type": "undercollat_lending", "yield_bearing": True},
    "USDe":     {"type": "yield_bearing", "sub_type": "delta_neutral",       "yield_bearing": False},
    "sUSDe":    {"type": "yield_bearing", "sub_type": "delta_neutral",       "yield_bearing": True},
    # ---- Algorithmic (2) ----
    "USDD":  {"type": "algorithmic", "sub_type": "reserve_backed", "yield_bearing": False},
    "FRAX":  {"type": "algorithmic", "sub_type": "fractional",     "yield_bearing": False},
}


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


def _cross_source_fields(chains_orm: list[AssetChainSnapshot], *, asset_symbol: str | None = None) -> tuple[int, float]:
    prices: dict[str, float | None] = {}
    sym = asset_symbol or (chains_orm[0].asset_symbol if chains_orm else None)
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
    if sym:
        try:
            from sources.chainlink_oracle import get_cached_oracle_price, fetch_oracle_price
            oracle_p = get_cached_oracle_price(sym) or fetch_oracle_price(sym)
            if oracle_p is not None:
                prices["chainlink"] = oracle_p
        except Exception:
            pass
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
    asset_symbol = chains_orm[0].asset_symbol if chains_orm else None
    cross_agreement, cross_disc = _cross_source_fields(chains_orm, asset_symbol=asset_symbol)

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


def inject_velocity(
    db: Session | None,
    kwargs: dict[str, Any],
    *,
    asset_symbol: str | None,
) -> dict[str, Any]:
    """Attach supply velocity fields when history is available."""
    if db is None or not asset_symbol:
        return kwargs
    supply_velocity = compute_supply_velocity(db, asset_symbol=asset_symbol.upper(), window_hours=24)
    if supply_velocity.get("available"):
        vel = supply_velocity.get("velocity", {})
        acc = supply_velocity.get("acceleration", {})
        kwargs["supply_velocity_1h"] = vel.get("1h")
        kwargs["supply_velocity_4h"] = vel.get("4h")
        kwargs["supply_velocity_12h"] = vel.get("12h")
        kwargs["supply_velocity_24h"] = vel.get("24h")
        kwargs["supply_accel_1h"] = acc.get("1h")
        kwargs["supply_accel_4h"] = acc.get("4h")
    return kwargs


def type_specific_inputs(
    db: Session | None,
    *,
    asset_symbol: str | None,
    stablecoin_type: str | None,
) -> dict[str, Any]:
    """Query V4 snapshot tables and return merged v4_snapshot_inputs dict."""
    if db is None or not asset_symbol or not stablecoin_type:
        return {}
    now = datetime.now(timezone.utc)
    v4_inputs: dict[str, Any] = {}

    try:
        fiat = db.execute(
            select(FiatReserveSnapshot)
            .where(FiatReserveSnapshot.asset_symbol == asset_symbol.upper())
            .order_by(FiatReserveSnapshot.created_at.desc())
        ).scalars().first()
        if fiat:
            v4_inputs["coverage_ratio"] = fiat.coverage_ratio
            v4_inputs["reserve_composition"] = fiat.reserve_composition
            v4_inputs["attestation_lag_days"] = fiat.attestation_lag_days
            v4_inputs["genius_act_compliant"] = fiat.genius_act_compliant
            v4_inputs["mica_status"] = fiat.mica_status

        coll = db.execute(
            select(CollateralSnapshot)
            .where(CollateralSnapshot.asset_symbol == asset_symbol.upper())
            .order_by(CollateralSnapshot.timestamp.desc())
        ).scalars().first()
        if coll:
            v4_inputs["collateral_ratio"] = coll.collateral_ratio
            v4_inputs["liquidation_queue_usd"] = coll.liquidation_queue_usd
            v4_inputs["debt_ceiling_utilization_pct"] = coll.debt_ceiling_utilization_pct
            v4_inputs["recovery_mode"] = (coll.collateral_assets_json or {}).get("recovery_mode", False) if coll.collateral_assets_json else False

        yb = db.execute(
            select(YieldBearingSnapshot)
            .where(YieldBearingSnapshot.asset_symbol == asset_symbol.upper())
            .order_by(YieldBearingSnapshot.timestamp.desc())
        ).scalars().first()
        if yb:
            v4_inputs["current_apy"] = yb.current_apy
            v4_inputs["yield_source"] = yb.yield_source
            v4_inputs["insurance_fund_usd"] = yb.insurance_fund_usd
            v4_inputs["insurance_fund_coverage"] = yb.insurance_fund_coverage
            v4_inputs["staking_ratio"] = yb.staking_ratio
            v4_inputs["lending_utilization_pct"] = yb.lending_utilization_pct
    except Exception:
        pass

    return v4_inputs


def inject_onchain(
    db: Session | None,
    kwargs: dict[str, Any],
    *,
    asset_symbol: str | None,
) -> dict[str, Any]:
    if db is None or not asset_symbol:
        return kwargs
    try:
        from services.onchain import onchain_risk_inputs
        onchain = onchain_risk_inputs(asset_symbol, db)
        if onchain.get("onchain_available"):
            kwargs["whale_net_outflow_usd"] = onchain.get("whale_net_outflow_usd")
            kwargs["whale_alert"] = onchain.get("whale_alert")
            kwargs["top10_holder_share_pct"] = onchain.get("top10_holder_share_pct")
            kwargs["net_mint_burn_usd_24h"] = onchain.get("net_mint_burn_usd_24h")
    except Exception:
        pass
    return kwargs


def compute_unified_risk_score(
    chains_orm: list[AssetChainSnapshot],
    *,
    source_ok: bool,
    source_error: str | None,
    age_seconds: float | None,
    refresh_interval_seconds: int,
    attestation_age_days: float | None = None,
    db: Session | None = None,
    asset_symbol: str | None = None,
    stablecoin_type: str | None = None,
) -> dict[str, Any]:
    kwargs = build_risk_score_kwargs(
        chains_orm,
        source_ok=source_ok,
        source_error=source_error,
        age_seconds=age_seconds,
        refresh_interval_seconds=refresh_interval_seconds,
        attestation_age_days=attestation_age_days,
    )
    sym = asset_symbol or (chains_orm[0].asset_symbol if chains_orm else None)
    kwargs = inject_velocity(db, kwargs, asset_symbol=sym)
    kwargs = inject_onchain(db, kwargs, asset_symbol=sym)
    if stablecoin_type:
        kwargs["stablecoin_type"] = stablecoin_type
        kwargs["v4_snapshot_inputs"] = type_specific_inputs(db, asset_symbol=sym, stablecoin_type=stablecoin_type)
    return scoring.compute_risk_score(**kwargs)
