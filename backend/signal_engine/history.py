"""V2.4 historical trend snapshots and local signal events (SQLite, forward-only)."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select, delete
from sqlalchemy.orm import Session

from database import AssetTrendSnapshot, ChainTrendSnapshot, SignalEvent, SourceStatus
from services.alerts import evaluate_alerts
from signal_engine.metrics import compute_asset_metric_bundle
from utils import utc_now

BUCKET_SECONDS = 300
EVENT_DEDUP_MINUTES = 30
DEPEG_WARN = 40
DEPEG_CRIT = 70
SUPPLY_WARN_PCT = 2.0
SUPPLY_INFO_PCT = 1.0
CONC_SHARE_DELTA_WARN = 5.0
CONC_SCORE_DELTA_WARN = 10

# Cooldown for source_recovered events — max 1 per 6 hours
SOURCE_RECOVERED_COOLDOWN_HOURS = 6
_last_source_recovery_emitted: datetime | None = None
_source_recovery_lock = threading.Lock()


def _depeg_zone(score: int) -> str:
    if score >= DEPEG_CRIT:
        return "high"
    if score >= DEPEG_WARN:
        return "mid"
    return "low"


def _refresh_interval() -> int:
    try:
        from providers.settings import get_setting
        return int(get_setting("refresh_core_seconds") or 300)
    except Exception:
        return int(os.getenv("REFRESH_INTERVAL_SECONDS", "300"))


def _previous_asset_snapshot(db: Session, *, asset_symbol: str, bucket_id: int) -> AssetTrendSnapshot | None:
    row = (
        db.execute(
            select(AssetTrendSnapshot)
            .where(AssetTrendSnapshot.asset_symbol == asset_symbol)
            .order_by(desc(AssetTrendSnapshot.timestamp))
        ).scalars().first()
    )
    if row is None:
        return None
    if row.bucket_id == bucket_id:
        return (
            db.execute(
                select(AssetTrendSnapshot)
                .where(
                    AssetTrendSnapshot.asset_symbol == asset_symbol,
                    AssetTrendSnapshot.bucket_id != bucket_id,
                )
                .order_by(desc(AssetTrendSnapshot.timestamp))
            ).scalars().first()
        )
    return row


def _duplicate_event(
    db: Session,
    *,
    asset_symbol: str,
    chain_key: str | None,
    event_type: str,
    severity: str,
    new_value: str | None,
) -> bool:
    cutoff = utc_now() - timedelta(minutes=EVENT_DEDUP_MINUTES)
    stmt = select(SignalEvent).where(
        SignalEvent.asset_symbol == asset_symbol,
        SignalEvent.event_type == event_type,
        SignalEvent.severity == severity,
        SignalEvent.timestamp >= cutoff,
    )
    if chain_key:
        stmt = stmt.where(SignalEvent.chain_key == chain_key)
    else:
        stmt = stmt.where(SignalEvent.chain_key.is_(None))
    last = db.execute(stmt.order_by(desc(SignalEvent.timestamp))).scalars().first()
    return last is not None and (new_value is None or last.new_value == new_value)


def _emit(
    pending_events: list[SignalEvent],
    db: Session,
    *,
    asset_symbol: str,
    chain_key: str | None,
    event_type: str,
    severity: str,
    title: str,
    summary: str,
    old_value: str | None,
    new_value: str | None,
    delta: str | None,
    threshold: str | None,
    ts: datetime,
    metadata: dict[str, Any] | None = None,
) -> None:
    if _duplicate_event(
        db,
        asset_symbol=asset_symbol,
        chain_key=chain_key,
        event_type=event_type,
        severity=severity,
        new_value=new_value,
    ):
        return
    row = SignalEvent(
        asset_symbol=asset_symbol,
        chain_key=chain_key,
        event_type=event_type,
        severity=severity,
        title=title,
        summary=summary,
        old_value=old_value,
        new_value=new_value,
        delta=delta,
        threshold=threshold,
        timestamp=ts,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    pending_events.append(row)

def _flush_events(db: Session, pending_events: list[SignalEvent], *, metrics_by_asset: dict[str, dict] | None = None) -> None:
    """Flush all pending events to the database using bulk insert, then dispatch webhooks."""
    if not pending_events:
        return
    to_dispatch = list(pending_events)
    db.bulk_save_objects(pending_events)
    pending_events.clear()
    # Dispatch webhooks in a background thread to avoid blocking the history flow (Phase 3.4)
    import threading
    def _bg_dispatch():
        try:
            from services.alert_router import deliver_events
            deliver_events(db, to_dispatch, metrics_by_asset=metrics_by_asset)
        except Exception as exc:
            log = __import__("structlog").get_logger(__name__)
            log.warning("webhook.dispatch_error", exc_info=True)
    threading.Thread(target=_bg_dispatch, daemon=True, name="webhook-dispatch").start()


def _emit_band_change(pending_events: list[SignalEvent], db: Session, *, sym: str, prev_band: str | None, new_band: str, ts: datetime) -> None:
    if prev_band is None or prev_band == new_band:
        return
    order = {"Normal": 0, "Watch": 1, "Risk": 2}
    pi = order.get(prev_band, 0)
    ni = order.get(new_band, 0)
    if ni > pi:
        severity = "critical" if new_band == "Risk" else "warning"
    else:
        severity = "info"
    _emit(
        pending_events, db,
        asset_symbol=sym,
        chain_key=None,
        event_type="signal_band_change",
        severity=severity,
        title=f"{sym} signal moved to {new_band}",
        summary=f"Composite Helix Signal band changed from {prev_band} to {new_band} after the latest refresh.",
        old_value=prev_band,
        new_value=new_band,
        delta=None,
        threshold=None,
        ts=ts,
    )


def _emit_depeg_change(pending_events: list[SignalEvent], db: Session, *, sym: str, prev_score: int | None, new_score: int, ts: datetime) -> None:
    if prev_score is None:
        return
    pz, nz = _depeg_zone(prev_score), _depeg_zone(new_score)
    if pz == nz:
        return
    if nz == "high":
        severity = "critical"
    elif nz == "mid" and pz == "low":
        severity = "warning"
    else:
        severity = "info"
    _emit(
        pending_events, db,
        asset_symbol=sym,
        chain_key=None,
        event_type="depeg_pressure_change",
        severity=severity,
        title=f"{sym} peg pressure shift",
        summary=f"Depeg Index moved from {prev_score} to {new_score} (zones {pz} to {nz}).",
        old_value=str(prev_score),
        new_value=str(new_score),
        delta=str(new_score - prev_score),
        threshold=f"warn>={DEPEG_WARN}, critical>={DEPEG_CRIT}",
        ts=ts,
    )


def _emit_supply_change(
    pending_events: list[SignalEvent],
    db: Session,
    *,
    sym: str,
    prev_supply: float | None,
    new_supply: float | None,
    ts: datetime,
) -> None:
    if prev_supply is None or new_supply is None or prev_supply <= 0:
        return
    pct = ((new_supply - prev_supply) / prev_supply) * 100.0
    if abs(pct) < SUPPLY_INFO_PCT:
        return
    severity = "warning" if abs(pct) >= SUPPLY_WARN_PCT else "info"
    _emit(
        pending_events, db,
        asset_symbol=sym,
        chain_key=None,
        event_type="large_supply_change",
        severity=severity,
        title=f"{sym} supply move vs last snapshot",
        summary=f"Total reported supply changed by {pct:+.3f}% compared to the prior stored trend point.",
        old_value=f"{prev_supply:.2f}",
        new_value=f"{new_supply:.2f}",
        delta=f"{pct:+.3f}%",
        threshold=f">={SUPPLY_INFO_PCT}% info, >={SUPPLY_WARN_PCT}% warning",
        ts=ts,
    )


def _emit_concentration_change(
    pending_events: list[SignalEvent],
    db: Session,
    *,
    sym: str,
    prev_top: float | None,
    new_top: float | None,
    prev_score: int | None,
    new_score: int,
    ts: datetime,
) -> None:
    fired = False
    if prev_top is not None and new_top is not None and abs(new_top - prev_top) >= CONC_SHARE_DELTA_WARN:
        fired = True
        _emit(
            pending_events, db,
            asset_symbol=sym,
            chain_key=None,
            event_type="concentration_change",
            severity="warning" if abs(new_top - prev_top) >= CONC_SHARE_DELTA_WARN * 1.5 else "info",
            title=f"{sym} top-chain share shift",
            summary=f"Largest chain supply share moved from {prev_top:.2f}% to {new_top:.2f}%.",
            old_value=f"{prev_top:.2f}%",
            new_value=f"{new_top:.2f}%",
            delta=f"{new_top - prev_top:+.2f} pts",
            threshold=f"{CONC_SHARE_DELTA_WARN} percentage points",
            ts=ts,
        )
    if (
        not fired
        and prev_score is not None
        and abs(new_score - prev_score) >= CONC_SCORE_DELTA_WARN
    ):
        _emit(
            pending_events, db,
            asset_symbol=sym,
            chain_key=None,
            event_type="concentration_change",
            severity="info",
            title=f"{sym} concentration score shift",
            summary=f"Chain concentration subscore moved from {prev_score} to {new_score}.",
            old_value=str(prev_score),
            new_value=str(new_score),
            delta=str(new_score - prev_score),
            threshold=str(CONC_SCORE_DELTA_WARN),
            ts=ts,
        )


def _emit_confidence_drop(
    pending_events: list[SignalEvent],
    db: Session,
    *, sym: str, prev_label: str | None, new_label: str, ts: datetime
) -> None:
    if prev_label != "High":
        return
    if new_label not in ("Medium", "Low"):
        return
    _emit(
        pending_events, db,
        asset_symbol=sym,
        chain_key=None,
        event_type="data_confidence_drop",
        severity="warning",
        title=f"{sym} data confidence softened",
        summary=f"Aggregate data confidence moved from {prev_label} to {new_label} based on source health and snapshot age.",
        old_value=prev_label,
        new_value=new_label,
        delta=None,
        threshold="High to Medium or Low",
        ts=ts,
    )


def _emit_source_recovered(pending_events: list[SignalEvent], db: Session, *, prior: str | None, ts: datetime) -> None:
    global _last_source_recovery_emitted
    if prior != "error":
        return
    with _source_recovery_lock:
        if _last_source_recovery_emitted is not None:
            elapsed = (ts - _last_source_recovery_emitted).total_seconds()
            if elapsed < SOURCE_RECOVERED_COOLDOWN_HOURS * 3600:
                return
        _last_source_recovery_emitted = ts
    _emit(
        pending_events, db,
        asset_symbol="ALL",
        chain_key=None,
        event_type="source_recovered",
        severity="debug",
        title="DefiLlama source recovered",
        summary="DefiLlama ingest completed successfully after a prior error state.",
        old_value="error",
        new_value="ok",
        delta=None,
        threshold=None,
        ts=ts,
        metadata={"source": "defillama"},
    )


def persist_trends_and_events(
    db: Session,
    *,
    successful_asset_symbols: list[str],
    completed_at: datetime,
    prior_source_status: str | None,
) -> None:
    """
    Persist asset and chain trend rows for this refresh bucket, then emit deduplicated events.
    Caller must only invoke after a successful multi-asset refresh (source status already ok).
    """
    if not successful_asset_symbols:
        return
    defillama = db.execute(select(SourceStatus).where(SourceStatus.source_name == "defillama")).scalars().first()
    if defillama is None or defillama.status != "ok":
        return

    pending_events: list[SignalEvent] = []
    interval = _refresh_interval()
    bucket_id = int(completed_at.timestamp() // BUCKET_SECONDS)
    ts = completed_at if completed_at.tzinfo else completed_at.replace(tzinfo=timezone.utc)

    _emit_source_recovered(pending_events, db, prior=prior_source_status, ts=ts)

    seen: set[str] = set()
    for sym in successful_asset_symbols:
        u = sym.upper()
        if u in seen:
            continue
        seen.add(u)

        prev_row = _previous_asset_snapshot(db, asset_symbol=u, bucket_id=bucket_id)

        # Delete existing snapshots for this bucket using bulk operations
        db.execute(
            delete(AssetTrendSnapshot).where(
                AssetTrendSnapshot.asset_symbol == u,
                AssetTrendSnapshot.bucket_id == bucket_id,
            )
        )
        db.execute(
            delete(ChainTrendSnapshot).where(
                ChainTrendSnapshot.asset_symbol == u,
                ChainTrendSnapshot.bucket_id == bucket_id,
            )
        )

        bundle = compute_asset_metric_bundle(db, asset_symbol=u, refresh_interval_seconds=interval)
        if bundle is None:
            continue

        rk = bundle.risk_kwargs or {}
        cross_source = None
        if rk.get("cross_source_agreement") is not None:
            cross_source = {
                "agreement": rk["cross_source_agreement"],
                "discrepancy_pct": rk.get("cross_source_discrepancy_pct", 0.0),
            }

        # Prepare objects for bulk insert
        asset_trend = AssetTrendSnapshot(
            asset_symbol=u,
            timestamp=ts,
            bucket_id=bucket_id,
            total_supply=bundle.total_supply,
            price=bundle.price,
            depeg_index=bundle.depeg_index,
            signal_score=bundle.signal_score,
            signal_band=bundle.signal_band,
            concentration_score=bundle.concentration_score,
            data_confidence_label=bundle.data_confidence_label,
            source_status=bundle.source_status,
            cross_source_discrepancy=cross_source,
        )
        
        chain_trends = []
        for ch in bundle.chains:
            chain_trend = ChainTrendSnapshot(
                asset_symbol=u,
                chain_key=ch.chain_key,
                chain_name=ch.chain_name,
                timestamp=ts,
                bucket_id=bucket_id,
                supply=ch.supply_current,
                supply_share_pct=ch.supply_share_pct,
                chain_tvl=ch.chain_tvl,
                chain_signal_score=ch.chain_signal_score,
                chain_signal_band=ch.chain_signal_band,
                data_confidence_score=ch.data_confidence_score,
            )
            chain_trends.append(chain_trend)
        
        # Bulk insert using bulk_save_objects for better performance
        db.add(asset_trend)
        if chain_trends:
            db.bulk_save_objects(chain_trends)

        if prev_row is None:
            continue

        _emit_band_change(pending_events, db, sym=u, prev_band=prev_row.signal_band, new_band=bundle.signal_band, ts=ts)
        _emit_depeg_change(pending_events, db, sym=u, prev_score=prev_row.depeg_index, new_score=bundle.depeg_index, ts=ts)
        _emit_supply_change(
            pending_events,
            db,
            sym=u,
            prev_supply=prev_row.total_supply,
            new_supply=bundle.total_supply,
            ts=ts,
        )
        prev_top = None
        # Approximate prior top share from stored concentration alone is weak; use chain table if needed.
        prev_q = (
            db.execute(
                select(ChainTrendSnapshot)
                .where(
                    ChainTrendSnapshot.asset_symbol == u,
                    ChainTrendSnapshot.bucket_id == prev_row.bucket_id,
                )
                .order_by(desc(ChainTrendSnapshot.supply_share_pct))
            ).scalars().first()
        )
        if prev_q and prev_q.supply_share_pct is not None:
            prev_top = float(prev_q.supply_share_pct)
        new_top = bundle.top_chain_share_pct
        _emit_concentration_change(
            pending_events,
            db,
            sym=u,
            prev_top=prev_top,
            new_top=new_top,
            prev_score=prev_row.concentration_score,
            new_score=bundle.concentration_score,
            ts=ts,
        )
        _emit_confidence_drop(
            pending_events,
            db,
            sym=u,
            prev_label=prev_row.data_confidence_label,
            new_label=bundle.data_confidence_label,
            ts=ts,
        )

        total_prev_week = sum((c.supply_prev_week or 0.0) for c in bundle.chains) if bundle.chains else 0
        supply_7d_pct = None
        if bundle.total_supply and total_prev_week > 0:
            supply_7d_pct = ((bundle.total_supply - total_prev_week) / total_prev_week) * 100.0

        bundle_dict = {
            "total_supply": bundle.total_supply,
            "price": bundle.price,
            "depeg_index": bundle.depeg_index,
            "signal_score": bundle.signal_score,
            "signal_band": bundle.signal_band,
            "concentration_score": bundle.concentration_score,
            "data_confidence_label": bundle.data_confidence_label,
            "freshness_age_seconds": bundle.freshness_age_seconds,
            "supply_change_7d_pct": supply_7d_pct,
            "top3_pool_share_pct": bundle.top_chain_share_pct,
        }
        # Enrich with risk_kwargs fields needed by alert evaluators
        rk = bundle.risk_kwargs or {}
        bundle_dict["slippage_100k"] = rk.get("slippage_100k_bps")
        bundle_dict["slippage_7d_median"] = rk.get("slippage_7d_median")
        bundle_dict["supply_age_hours"] = rk.get("supply_age_hours")
        evaluate_alerts(db, bundle=bundle_dict, asset_symbol=u, now=ts)
    
    # Flush all pending events (with per-asset metrics for webhook payloads)
    metrics_by_asset: dict[str, dict] = {}
    for sym in seen:
        bundle = compute_asset_metric_bundle(db, asset_symbol=sym, refresh_interval_seconds=interval)
        if bundle:
            metrics_by_asset[sym] = {
                "signal_score": bundle.signal_score,
                "depeg_index": bundle.depeg_index,
            }
    _flush_events(db, pending_events, metrics_by_asset=metrics_by_asset)

