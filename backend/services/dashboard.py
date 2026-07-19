"""Dashboard response assembly service.

This module provides functions for building dashboard responses that aggregate
data from multiple sources and compute risk metrics. It serves as the primary
interface between the data layer and the frontend dashboard.

Key responsibilities:
- Building comprehensive dashboard responses
- Computing risk scores and metrics
- Aggregating data from various sources
- Ensuring data consistency and completeness
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import AssetChainSnapshot, SourceStatus
from schemas import (
    AssetMetadataOut,
    AssetSignalOut,
    AttestationOut,
    ChainConcentrationOut,
    ChainSignalOut,
    CrossSourceSignalOut,
    DashboardChainRow,
    DashboardResponse,
    DataConfidenceOut,
    DataQualityOut,
    DepegIndexOut,
    FreshnessOut,
    SourceStatusOut,
    SupplyFeedOut,
    SupplyMomentumOut,
)
from schemas import TrendPointOut, TrendSummaryOut
from signal_engine import scoring
from signal_engine.core import get_asset_by_symbol, get_default_asset_symbol
from signal_engine.risk_inputs import build_risk_score_kwargs, inject_velocity, inject_onchain
from utils import utc_normalize, window_delta


def build_trend_summary(points: list[TrendPointOut], *, window: str, now: datetime) -> TrendSummaryOut:
    span_td = window_delta(window)
    window_seconds = max(span_td.total_seconds(), 1.0)
    window_hours = window_seconds / 3600.0
    axis_min = now - span_td
    axis_max = now
    wl = window.strip().lower()

    n = len(points)
    if n == 0:
        return TrendSummaryOut(
            point_count=0,
            supply_change_abs=None,
            supply_change_pct=None,
            score_change=None,
            max_depeg_index=None,
            latest_band=None,
            selected_window=wl,
            window_span_hours=round(window_hours, 4),
            first_timestamp=None,
            latest_timestamp=None,
            available_duration_minutes=None,
            low_data=True,
            low_data_reason="No trend snapshots in this window yet. Run refreshes to collect forward history.",
            chart_axis_min_utc=axis_min,
            chart_axis_max_utc=axis_max,
        )

    first, last = points[0], points[-1]
    first_ts = first.timestamp
    last_ts = last.timestamp
    avail_seconds = max((last_ts - first_ts).total_seconds(), 0.0)
    avail_minutes = avail_seconds / 60.0
    coverage = avail_seconds / window_seconds

    supply_abs = None
    supply_pct = None
    if first.total_supply is not None and last.total_supply is not None:
        supply_abs = float(last.total_supply) - float(first.total_supply)
        if first.total_supply:
            supply_pct = (supply_abs / float(first.total_supply)) * 100.0
    score_change = float(last.signal_score - first.signal_score) if n >= 2 else None
    max_depeg = max((p.depeg_index for p in points), default=None)

    low_data = n < 2 or coverage < 0.92
    low_data_reason: str | None = None
    if n < 2:
        low_data_reason = (
            "Need at least two snapshots to draw reliable trend lines. "
            "History collection started recently inside the selected window."
        )
    elif coverage < 0.92:
        hrs = int(avail_seconds // 3600)
        mins = int((avail_seconds % 3600) // 60)
        dur_txt = f"{hrs}h {mins}m" if hrs else (f"{mins} min" if mins else "under 1 min")
        low_data_reason = (
            f"History collection started recently. Showing about {dur_txt} of available data "
            f"inside the selected {wl} window."
        )

    return TrendSummaryOut(
        point_count=n,
        supply_change_abs=supply_abs,
        supply_change_pct=supply_pct,
        score_change=score_change,
        max_depeg_index=max_depeg,
        latest_band=last.signal_band,
        selected_window=wl,
        window_span_hours=round(window_hours, 4),
        first_timestamp=first_ts,
        latest_timestamp=last_ts,
        available_duration_minutes=round(avail_minutes, 3),
        low_data=low_data,
        low_data_reason=low_data_reason,
        chart_axis_min_utc=axis_min,
        chart_axis_max_utc=axis_max,
    )


def _fetch_chain_and_sources(
    db: Session, selected_symbol: str, refresh_interval: int
) -> tuple[list[AssetChainSnapshot], list[SourceStatus], SourceStatus | None, str, str | None]:
    chains_orm = (
        db.execute(
            select(AssetChainSnapshot)
            .where(AssetChainSnapshot.asset_symbol == selected_symbol)
            .order_by(AssetChainSnapshot.supply_current.desc(), AssetChainSnapshot.chain_name.asc())
        )
        .scalars()
        .all()
    )
    sources_orm = db.execute(select(SourceStatus).order_by(SourceStatus.id.asc())).scalars().all()
    defillama = next((s for s in sources_orm if s.source_name == "defillama"), None)
    source_status = defillama.status if defillama else "unknown"
    source_error = defillama.last_error if defillama else None
    return chains_orm, sources_orm, defillama, source_status, source_error


def _compute_freshness_and_supply(
    chains_orm: list[AssetChainSnapshot], defillama: SourceStatus | None,
    source_status: str, refresh_interval: int,
) -> tuple[FreshnessOut, float | None, float | None, list[float], bool]:
    newest_chain_snapshot = max((utc_normalize(c.fetched_at) for c in chains_orm), default=None) if chains_orm else None
    freshness_dict = scoring.compute_freshness(
        source_status=source_status,
        last_successful_fetch=utc_normalize(defillama.last_successful_fetch) if defillama else None,
        newest_chain_snapshot=newest_chain_snapshot,
        refresh_interval_seconds=refresh_interval,
    )
    freshness = FreshnessOut(**freshness_dict)
    raw_total = sum((c.supply_current or 0.0) for c in chains_orm)
    total_supply = raw_total if raw_total > 0 else None
    total_prev_day = sum((c.supply_prev_day or 0.0) for c in chains_orm)
    total_change_24h_pct: float | None = None
    if total_supply is not None and total_prev_day > 0:
        total_change_24h_pct = ((total_supply - total_prev_day) / total_prev_day) * 100.0
    chain_shares: list[float] = []
    if total_supply and total_supply > 0:
        for c in chains_orm:
            if c.supply_current is not None and c.supply_current > 0:
                chain_shares.append(float(c.supply_current) / float(total_supply))
    source_ok = defillama is not None and defillama.status == "ok"
    return freshness, total_supply, total_change_24h_pct, chain_shares, source_ok


def _compute_depeg_and_risk(
    db: Session, selected_symbol: str, chains_orm: list[AssetChainSnapshot],
    total_supply: float | None, chain_shares: list[float],
    source_ok: bool, source_error: str | None, freshness_dict: dict,
    refresh_interval: int,
) -> tuple[DepegIndexOut, AssetSignalOut, ChainConcentrationOut]:
    price = next((c.price for c in chains_orm if c.price is not None), None)
    dev_abs, dev_pct = scoring.peg_deviation(price) if price is not None else (None, None)
    depeg_index = DepegIndexOut(
        score=scoring.depeg_index_score(price),
        current_price=price, deviation_abs=dev_abs, deviation_pct=dev_pct,
        peg_status=scoring.peg_status_label(price),
    )
    risk_kwargs = build_risk_score_kwargs(
        chains_orm, source_ok=source_ok, source_error=source_error,
        age_seconds=freshness_dict.get("age_seconds"),
        refresh_interval_seconds=refresh_interval,
    )
    risk_kwargs = inject_velocity(db, risk_kwargs, asset_symbol=selected_symbol)
    risk_kwargs = inject_onchain(db, risk_kwargs, asset_symbol=selected_symbol)
    conc_s, conc_detail = scoring.concentration_component(
        chain_shares, top3_dex_pool_share=risk_kwargs.get("top3_dex_pool_share"),
    )
    asset_signal_dict = scoring.compute_risk_score(**risk_kwargs)
    top_chain_name: str | None = None
    if total_supply and total_supply > 0 and chains_orm:
        top_row = max(chains_orm, key=lambda c: (c.supply_current or 0.0))
        if (top_row.supply_current or 0.0) > 0:
            top_chain_name = top_row.chain_name
    chain_concentration = ChainConcentrationOut(
        top_chain=top_chain_name, top_chain_share_pct=conc_detail.get("top_chain_share_pct"),
        hhi=conc_detail.get("hhi"), label=scoring.composite_band(conc_s),
    )
    asset_signal = AssetSignalOut(
        score=int(asset_signal_dict["score"]), band=str(asset_signal_dict["band"]),
        components=dict(asset_signal_dict["components"]),
    )
    return depeg_index, asset_signal, chain_concentration


def _build_chain_rows(
    chains_orm: list[AssetChainSnapshot], selected_symbol: str, selected_asset: dict,
    total_supply: float | None, source_ok: bool, refresh_interval: int, now: datetime,
) -> list[DashboardChainRow]:
    asset_name = selected_asset.get("name")
    rows: list[DashboardChainRow] = []
    for c in chains_orm:
        fetched = utc_normalize(c.fetched_at)
        age_s = (now - fetched).total_seconds() if fetched else None
        sm_raw = scoring.chain_supply_momentum(
            supply_current=c.supply_current, supply_prev_day=c.supply_prev_day,
            supply_prev_week=c.supply_prev_week, supply_prev_month=c.supply_prev_month,
        )
        share_pct = (
            (float(c.supply_current) / float(total_supply)) * 100.0
            if total_supply and c.supply_current is not None and total_supply > 0 else None
        )
        mom_hint, _ = scoring.supply_momentum_component(
            supply_current=float(c.supply_current or 0.0), supply_prev_day=c.supply_prev_day,
            supply_prev_week=c.supply_prev_week, supply_prev_month=c.supply_prev_month,
        )
        cs_raw = scoring.chain_row_signal(
            chain_share_pct=share_pct, peg_price=c.price, momentum_score_hint=mom_hint,
        )
        dc_raw = scoring.chain_data_confidence(
            source_ok=source_ok, chain_snapshot_age_seconds=age_s,
            refresh_interval_seconds=refresh_interval,
        )
        rows.append(DashboardChainRow(
            asset_symbol=selected_symbol, asset_name=asset_name, chain_name=c.chain_name,
            supply_current=c.supply_current, supply_prev_day=c.supply_prev_day,
            supply_prev_week=c.supply_prev_week, supply_prev_month=c.supply_prev_month,
            chain_tvl=c.tvl, price=c.price, price_coingecko=c.price_coingecko,
            price_dexscreener=c.price_dexscreener, market_cap=c.market_cap,
            volume_24h=c.volume_24h, total_liquidity_usd=c.total_liquidity_usd,
            top3_pool_share_pct=c.top3_pool_share_pct, pool_count=c.pool_count,
            peg_type=c.peg_type, fetched_at=c.fetched_at,
            supply_momentum=SupplyMomentumOut(**sm_raw),
            chain_share_pct=round(share_pct, 4) if share_pct is not None else None,
            chain_signal=ChainSignalOut(score=int(cs_raw["score"]), band=str(cs_raw["band"])),
            data_confidence=DataConfidenceOut(score=int(dc_raw["score"]), label=str(dc_raw["label"]), reason=str(dc_raw["reason"])),
        ))
    return rows


def _compute_cross_source_and_feed(
    chains_orm: list[AssetChainSnapshot], selected_symbol: str,
    now: datetime, sources_orm: list[SourceStatus],
) -> tuple[CrossSourceSignalOut, SupplyFeedOut]:
    prices_all = [c.price for c in chains_orm if c.price is not None]
    prices_cg = [c.price_coingecko for c in chains_orm if c.price_coingecko is not None]
    prices_ds = [c.price_dexscreener for c in chains_orm if c.price_dexscreener is not None]
    all_prices = prices_all + prices_cg + prices_ds
    source_rows: list[dict] = []
    ref_chain = next((c for c in chains_orm if c.price is not None or c.price_coingecko or c.price_dexscreener), None)
    if ref_chain:
        if ref_chain.price is not None:
            source_rows.append({"source": "DeFiLlama", "price": ref_chain.price})
        if ref_chain.price_coingecko is not None:
            source_rows.append({"source": "CoinGecko", "price": ref_chain.price_coingecko})
        if ref_chain.price_dexscreener is not None:
            source_rows.append({"source": "DexScreener", "price": ref_chain.price_dexscreener})
    try:
        from sources.chainlink_oracle import get_cached_oracle_price
        oracle_p = get_cached_oracle_price(selected_symbol)
        if oracle_p is not None:
            source_rows.append({"source": "Chainlink", "price": oracle_p})
            all_prices.append(oracle_p)
    except Exception:
        log.debug("dashboard.chainlink_oracle_skipped", exc_info=True)
    cross_source = CrossSourceSignalOut()
    if len(all_prices) >= 2:
        avg_p = sum(all_prices) / len(all_prices)
        max_disc = max(abs(p - avg_p) / avg_p * 100 if avg_p else 0 for p in all_prices)
        cross_source = CrossSourceSignalOut(
            sources_agreeing=len(source_rows) or len(all_prices),
            max_discrepancy_pct=round(max_disc, 4), discrepancy_flag=max_disc > 0.5,
            avg_price=round(avg_p, 6), sources=source_rows,
        )
    elif source_rows:
        cross_source = CrossSourceSignalOut(sources=source_rows, sources_agreeing=len(source_rows))
    supply_feed = SupplyFeedOut()
    defillama_source = next((s for s in sources_orm if s.source_name == "defillama"), None)
    if defillama_source and defillama_source.last_successful_fetch:
        feed_age = (now - utc_normalize(defillama_source.last_successful_fetch)).total_seconds() / 60
        supply_feed = SupplyFeedOut(
            age_minutes=round(feed_age, 1),
            status="fresh" if feed_age < 15 else ("aging" if feed_age < 60 else "stale"),
            label="Fresh" if feed_age < 15 else ("Aging" if feed_age < 60 else "Stale"),
            note=f"DefiLlama supply feed last updated {feed_age:.0f} min ago",
        )
    return cross_source, supply_feed


def _compute_attestation_and_nlp(db: Session, selected_symbol: str) -> tuple[AttestationOut, bool]:
    attestation_signal = AttestationOut()
    try:
        from services.osint import get_attestation_status
        att = get_attestation_status(db)
        if selected_symbol in att:
            a = att[selected_symbol]
            att_age = a.get("attestation_age_days")
            if att_age is not None:
                att_status = "fresh" if att_age < 90 else ("aging" if att_age < 180 else "stale")
                attestation_signal = AttestationOut(
                    status=att_status, age_days=att_age,
                    last_report_date=a.get("latest_attestation_report_date"),
                    label="Fresh" if att_age < 90 else ("Aging" if att_age < 180 else "Stale"),
                    note=f"{att_age:.0f}d since last attestation report",
                )
    except Exception:
        logging.getLogger(__name__).debug("Attestation lookup failed", exc_info=True)
    from providers.settings import get_setting
    nlp_from_settings = get_setting("feature_nlp_sentiment", db)
    nlp_enabled = bool(nlp_from_settings) if nlp_from_settings is not None else False
    return attestation_signal, nlp_enabled


def build_dashboard_response(db: Session, asset: str | None = None) -> DashboardResponse:
    from services.asset_overlay import effective_asset_enabled, get_asset_overrides

    selected_symbol = (asset or get_default_asset_symbol()).upper()
    selected_asset = get_asset_by_symbol(selected_symbol)
    overrides = get_asset_overrides(db)
    if selected_asset is None or not effective_asset_enabled(selected_asset, overrides):
        raise HTTPException(status_code=404, detail=f"Asset '{selected_symbol}' is not enabled")

    from providers.settings import get_setting
    refresh_interval = int(get_setting("refresh_core_seconds", db) or 300)

    chains_orm, sources_orm, defillama, source_status, source_error = _fetch_chain_and_sources(db, selected_symbol, refresh_interval)
    freshness, total_supply, total_change_24h_pct, chain_shares, source_ok = _compute_freshness_and_supply(chains_orm, defillama, source_status, refresh_interval)
    depeg_index, asset_signal, chain_concentration = _compute_depeg_and_risk(db, selected_symbol, chains_orm, total_supply, chain_shares, source_ok, source_error, freshness.model_dump() if hasattr(freshness, 'model_dump') else {}, refresh_interval)

    now = datetime.now(timezone.utc)
    dashboard_chains = _build_chain_rows(chains_orm, selected_symbol, selected_asset, total_supply, source_ok, refresh_interval, now)
    cross_source, supply_feed = _compute_cross_source_and_feed(chains_orm, selected_symbol, now, sources_orm)
    attestation_signal, nlp_enabled = _compute_attestation_and_nlp(db, selected_symbol)

    sources = [SourceStatusOut.model_validate(s) for s in sources_orm]
    degraded_sources = [s.source_name for s in sources_orm if s.status != "ok"]

    return DashboardResponse(
        asset=AssetMetadataOut(symbol=selected_symbol, name=selected_asset.get("name"), peg_type=selected_asset.get("peg_type")),
        generated_at=now, refresh_interval_seconds=refresh_interval,
        freshness=freshness, asset_signal=asset_signal, depeg_index=depeg_index,
        chain_concentration=chain_concentration, cross_source_signal=cross_source,
        supply_feed=supply_feed, attestation=attestation_signal,
        total_supply_current=total_supply, total_supply_change_24h_pct=total_change_24h_pct,
        chains=dashboard_chains, sources=sources,
        data_quality=DataQualityOut(degraded_sources=degraded_sources, using_cached_data=len(degraded_sources) > 0, nlp_available=nlp_enabled),
    )
