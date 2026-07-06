"""Tests for the address clustering module."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from chain.intelligence.address_clustering import (
    _funding_source_overlap,
    _gas_wallet_reuse,
    _timing_correlation,
    _volume_pattern_match,
    cluster_addresses,
)
from database import BlacklistEvent

_counter = [0]


def _make_blacklist_event(
    frozen_address: str,
    chain: str = "ethereum",
    frozen_usd: float = 1_000_000,
    asset_symbol: str = "USDT",
) -> BlacklistEvent:
    _counter[0] += 1
    return BlacklistEvent(
        id=_counter[0],
        asset_symbol=asset_symbol,
        chain=chain,
        frozen_address=frozen_address,
        frozen_balance_usd=frozen_usd,
        event_type="freeze",
        tx_hash=f"0x{_counter[0]:x}",
        intelligence_note=f"Test freeze {_counter[0]}",
        timestamp=datetime.now(timezone.utc),
    )


def test_funding_source_overlap_empty(db_session: Session):
    result = _funding_source_overlap(db_session, "0xdead", "ethereum")
    assert result == []


def test_funding_source_overlap_with_data(db_session: Session):
    db_session.add(_make_blacklist_event(frozen_address="0xaddr1", frozen_usd=500_000))
    db_session.commit()

    result = _funding_source_overlap(db_session, "0xtarget", "ethereum")
    assert isinstance(result, list)
    assert "0xaddr1" in result, "heuristic should surface other recent blacklist events on same chain"


def test_gas_wallet_reuse_empty(db_session: Session):
    result = _gas_wallet_reuse(db_session, "0xdead", "ethereum")
    assert result == []


def test_gas_wallet_reuse_with_data(db_session: Session):
    db_session.add(_make_blacklist_event(frozen_address="0xgasheavy", frozen_usd=15_000_000))
    db_session.commit()

    result = _gas_wallet_reuse(db_session, "0xtarget", "ethereum")
    assert isinstance(result, list)
    assert "0xgasheavy" in result, "heuristic should surface high-balance recent events (>=10M USD)"


def test_timing_correlation_empty(db_session: Session):
    result = _timing_correlation(db_session, "0xdead", "ethereum")
    assert result == []


def test_timing_correlation_with_data(db_session: Session):
    db_session.add_all([
        _make_blacklist_event(frozen_address="0xaddr_a", frozen_usd=1_000_000),
        _make_blacklist_event(frozen_address="0xaddr_b", frozen_usd=2_000_000),
    ])
    db_session.commit()

    result = _timing_correlation(db_session, "0xtarget", "ethereum")
    assert isinstance(result, list)
    assert {"0xaddr_a", "0xaddr_b"} <= set(result), "heuristic should surface same-day blacklist events"


def test_volume_pattern_match_empty(db_session: Session):
    result = _volume_pattern_match(db_session, "0xdead", "ethereum")
    assert result == []


def test_volume_pattern_match_with_data(db_session: Session):
    db_session.add_all([
        _make_blacklist_event(frozen_address="0xvol_a", frozen_usd=10_000_000),
        _make_blacklist_event(frozen_address="0xvol_b", frozen_usd=8_000_000),
    ])
    db_session.commit()

    result = _volume_pattern_match(db_session, "0xtarget", "ethereum")
    assert isinstance(result, list)
    assert {"0xvol_a", "0xvol_b"} <= set(result), "heuristic should surface events >=5M USD within 7 days"


def test_cluster_addresses_orchestrator(db_session: Session):
    db_session.add_all([
        _make_blacklist_event(frozen_address="0xaddr1", frozen_usd=8_000_000),
        _make_blacklist_event(frozen_address="0xaddr2", frozen_usd=6_000_000),
    ])
    db_session.commit()

    result = cluster_addresses(db_session, "0xtarget", chain="ethereum")
    assert result["target_address"] == "0xtarget"
    assert isinstance(result["clustered_addresses"], list)
    assert len(result["clustered_addresses"]) >= 1, "orchestrator should surface at least one clustered address from seeded events"
