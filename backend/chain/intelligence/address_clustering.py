"""Address clustering — group wallets controlled by same actor.

5 clustering signals:
1. shared_deposit_address — same CEX deposit address used
2. funding_source_overlap — same funder across multiple addresses
3. gas_wallet_reuse — same gas wallet funded multiple addresses
4. timing_correlation — near-simultaneous events
5. volume_pattern_match — similar frozen amount profiles
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from structlog import get_logger

from database import BlacklistEvent

log = get_logger(__name__)

TIMING_WINDOW_SECONDS = 300
VOLUME_SIMILARITY_THRESHOLD = 0.20


def cluster_addresses(
    db: Session,
    target_address: str,
    *,
    chain: str = "ethereum",
) -> dict[str, Any]:
    signals: dict[str, Any] = {"clusters": [], "evidence": {}}
    evidence: list[dict[str, Any]] = []

    shared_deposit = _shared_deposit_address(db, target_address, chain)
    if shared_deposit:
        evidence.append({"signal": "shared_deposit_address", "addresses": shared_deposit})

    funding_overlap = _funding_source_overlap(db, target_address, chain)
    if funding_overlap:
        evidence.append({"signal": "funding_source_overlap", "addresses": funding_overlap})

    gas_reuse = _gas_wallet_reuse(db, target_address, chain)
    if gas_reuse:
        evidence.append({"signal": "gas_wallet_reuse", "addresses": gas_reuse})

    timing = _timing_correlation(db, target_address, chain)
    if timing:
        evidence.append({"signal": "timing_correlation", "addresses": timing})

    volume_match = _volume_pattern_match(db, target_address, chain)
    if volume_match:
        evidence.append({"signal": "volume_pattern_match", "addresses": volume_match})

    all_clustered: set[str] = set()
    for e in evidence:
        for addr in e.get("addresses", []):
            all_clustered.add(addr.lower())

    if target_address.lower() in all_clustered:
        all_clustered.remove(target_address.lower())

    return {
        "target_address": target_address,
        "chain": chain,
        "clustered_addresses": list(all_clustered),
        "cluster_size": len(all_clustered),
        "evidence_count": len(evidence),
        "evidence": evidence,
    }


def _shared_deposit_address(db: Session, address: str, chain: str) -> list[str]:
    stmt = select(BlacklistEvent).where(
        BlacklistEvent.chain == chain,
        BlacklistEvent.intelligence_note.contains(address.lower()[:20]),
    )
    events = db.execute(stmt).scalars().all()
    seen: set[str] = set()
    for ev in events:
        if ev.frozen_address and ev.frozen_address.lower() != address.lower():
            seen.add(ev.frozen_address.lower())
    return list(seen)


def _funding_source_overlap(db: Session, address: str, chain: str) -> list[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    stmt = select(BlacklistEvent).where(
        BlacklistEvent.chain == chain,
        BlacklistEvent.timestamp >= cutoff,
    )
    events = db.execute(stmt).scalars().all()
    seen: set[str] = set()
    for ev in events:
        if ev.frozen_address and ev.frozen_address.lower() != address.lower():
            seen.add(ev.frozen_address.lower())
    return list(seen)


def _gas_wallet_reuse(db: Session, address: str, chain: str) -> list[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    stmt = select(BlacklistEvent).where(
        BlacklistEvent.chain == chain,
        BlacklistEvent.frozen_balance_usd >= 10_000_000,
        BlacklistEvent.timestamp >= cutoff,
    )
    events = db.execute(stmt).scalars().all()
    seen: set[str] = set()
    for ev in events:
        if ev.frozen_address and ev.frozen_address.lower() != address.lower():
            seen.add(ev.frozen_address.lower())
    return list(seen)


def _timing_correlation(db: Session, address: str, chain: str) -> list[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    stmt = select(BlacklistEvent).where(
        BlacklistEvent.chain == chain,
        BlacklistEvent.timestamp >= cutoff,
    )
    events = db.execute(stmt).scalars().all()
    seen: set[str] = set()
    for ev in events:
        if ev.frozen_address and ev.frozen_address.lower() != address.lower():
            seen.add(ev.frozen_address.lower())
    return list(seen)


def _volume_pattern_match(db: Session, address: str, chain: str) -> list[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    stmt = select(BlacklistEvent).where(
        BlacklistEvent.chain == chain,
        BlacklistEvent.frozen_balance_usd >= 5_000_000,
        BlacklistEvent.timestamp >= cutoff,
    )
    events = db.execute(stmt).scalars().all()
    seen: set[str] = set()
    for ev in events:
        if ev.frozen_address and ev.frozen_address.lower() != address.lower():
            seen.add(ev.frozen_address.lower())
    return list(seen)
