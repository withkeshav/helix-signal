"""V2.4 historical trend snapshots and local signal events (SQLite, forward-only)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import AssetTrendSnapshot, ChainTrendSnapshot, SignalEvent, SourceStatus
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


def _depeg_zone(score: int) -> str:
    if score >= DEPEG_CRIT:
        return "high"
    if score >= DEPEG_WARN:
        return "mid"
    return "low"


def _refresh_interval() -> int:
    return int(os.getenv("REFRESH_INTERVAL_SECONDS", "300"))


def _previous_asset_snapshot(db: Session, *, asset_symbol: str, bucket_id: int) -> AssetTrendSnapshot | None:
    row = (
        db.query(AssetTrendSnapshot)
        .filter(AssetTrendSnapshot.asset_symbol == asset_symbol)
        .order_by(desc(AssetTrendSnapshot.timestamp))
        .first()
    )
    if row is None:
        return None
    if row.bucket_id == bucket_id:
        return (
            db.query(AssetTrendSnapshot)
            .filter(AssetTrendSnapshot.asset_symbol == asset_symbol, AssetTrendSnapshot.bucket_id != bucket_id)
            .order_by(desc(AssetTrendSnapshot.timestamp))
            .first()
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
    q = (
        db.query(SignalEvent)
        .filter(
            SignalEvent.asset_symbol == asset_symbol,
            SignalEvent.event_type == event_type,
            SignalEvent.severity == severity,
            SignalEvent.timestamp >= cutoff,
        )
    )
    if chain_key:
        q = q.filter(SignalEvent.chain_key == chain_key)
    else:
        q = q.filter(SignalEvent.chain_key.is_(None))
    last = q.order_by(desc(SignalEvent.timestamp)).first()
    return last is not None and (new_value is None or last.new_value == new_value)


def _emit(
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
    db.add(row)


def _emit_band_change(db: Session, *, sym: str, prev_band: str | None, new_band: str, ts: datetime) -> None:
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
        db,
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


def _emit_depeg_change(db: Session, *, sym: str, prev_score: int | None, new_score: int, ts: datetime) -> None:
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
        db,
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
        db,
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
            db,
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
            db,
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
    db: Session,
    *, sym: str, prev_label: str | None, new_label: str, ts: datetime
) -> None:
    if prev_label != "High":
        return
    if new_label not in ("Medium", "Low"):
        return
    _emit(
        db,
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


def _emit_source_recovered(db: Session, *, prior: str | None, ts: datetime) -> None:
    if prior != "error":
        return
    _emit(
        db,
        asset_symbol="ALL",
        chain_key=None,
        event_type="source_recovered",
        severity="info",
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
    defillama = db.query(SourceStatus).filter(SourceStatus.source_name == "defillama").first()
    if defillama is None or defillama.status != "ok":
        return

    interval = _refresh_interval()
    bucket_id = int(completed_at.timestamp() // BUCKET_SECONDS)
    ts = completed_at if completed_at.tzinfo else completed_at.replace(tzinfo=timezone.utc)

    _emit_source_recovered(db, prior=prior_source_status, ts=ts)

    seen: set[str] = set()
    for sym in successful_asset_symbols:
        u = sym.upper()
        if u in seen:
            continue
        seen.add(u)

        prev_row = _previous_asset_snapshot(db, asset_symbol=u, bucket_id=bucket_id)

        db.query(AssetTrendSnapshot).filter(
            AssetTrendSnapshot.asset_symbol == u,
            AssetTrendSnapshot.bucket_id == bucket_id,
        ).delete(synchronize_session=False)
        db.query(ChainTrendSnapshot).filter(
            ChainTrendSnapshot.asset_symbol == u,
            ChainTrendSnapshot.bucket_id == bucket_id,
        ).delete(synchronize_session=False)

        bundle = compute_asset_metric_bundle(db, asset_symbol=u, refresh_interval_seconds=interval)
        if bundle is None:
            continue

        db.add(
            AssetTrendSnapshot(
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
            )
        )
        for ch in bundle.chains:
            db.add(
                ChainTrendSnapshot(
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
            )

        if prev_row is None:
            continue

        _emit_band_change(db, sym=u, prev_band=prev_row.signal_band, new_band=bundle.signal_band, ts=ts)
        _emit_depeg_change(db, sym=u, prev_score=prev_row.depeg_index, new_score=bundle.depeg_index, ts=ts)
        _emit_supply_change(
            db,
            sym=u,
            prev_supply=prev_row.total_supply,
            new_supply=bundle.total_supply,
            ts=ts,
        )
        prev_top = None
        # Approximate prior top share from stored concentration alone is weak; use chain table if needed.
        prev_q = (
            db.query(ChainTrendSnapshot)
            .filter(
                ChainTrendSnapshot.asset_symbol == u,
                ChainTrendSnapshot.bucket_id == prev_row.bucket_id,
            )
            .order_by(desc(ChainTrendSnapshot.supply_share_pct))
            .first()
        )
        if prev_q and prev_q.supply_share_pct is not None:
            prev_top = float(prev_q.supply_share_pct)
        new_top = bundle.top_chain_share_pct
        _emit_concentration_change(
            db,
            sym=u,
            prev_top=prev_top,
            new_top=new_top,
            prev_score=prev_row.concentration_score,
            new_score=bundle.concentration_score,
            ts=ts,
        )
        _emit_confidence_drop(
            db,
            sym=u,
            prev_label=prev_row.data_confidence_label,
            new_label=bundle.data_confidence_label,
            ts=ts,
        )
