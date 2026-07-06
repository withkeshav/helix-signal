"""Integration test for signal_engine.core.refresh_chain_data.

Exercises the full async refresh flow against a stubbed source registry —
no network calls. Verifies the SourceStatus rows are upserted correctly
for both the success path and the no-enabled-assets early return.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from database import SourceStatus
from signal_engine.core import refresh_chain_data


def _stub_source(ok: bool = True, payload=None, transform_out=None):
    src = MagicMock()
    async def _async_fetch(*args, **kwargs):
        if not ok:
            raise RuntimeError("boom")
        return payload or {"chains": {}}
    src.async_fetch = _async_fetch
    src.transform = MagicMock(return_value=transform_out or {})
    return src


def _stub_registry(monkeypatch, **sources):
    from signal_engine import core as core_mod
    fake_registry = dict(sources)
    monkeypatch.setattr(core_mod, "build_default_registry", lambda db: fake_registry)


def test_refresh_chain_data_no_enabled_assets(db_session, monkeypatch):
    """When no assets are enabled, refresh writes 'error' status and returns."""
    monkeypatch.setattr("signal_engine.core.load_enabled_assets", lambda: [])
    asyncio.run(refresh_chain_data(db_session))

    rows = db_session.query(SourceStatus).all()
    assert len(rows) >= 1
    for row in rows:
        assert row.status == "error"
        assert row.last_error is not None


def test_refresh_chain_data_success_path(db_session, monkeypatch):
    """With a configured asset and a healthy stubbed DeFiLlama source,
    refresh completes without raising and writes a source status row.
    """
    monkeypatch.setattr(
        "signal_engine.core.load_enabled_assets",
        lambda: [{"symbol": "USDT", "defillama_id": 1, "chains": ["Ethereum"]}],
    )
    monkeypatch.setattr(
        "signal_engine.core.load_configured_chains",
        lambda db: [{"defillama_id": 1, "name": "Ethereum"}],
    )
    _stub_registry(
        monkeypatch,
        defillama=_stub_source(ok=True, payload={
            "fetched_at": datetime.now(timezone.utc),
            "chain_data": {"1": {"peggedUSD": {"current": 60_000_000_000.0}}},
            "asset_symbol": "USDT",
            "asset_name": "Tether",
            "peg_type": "peggedUSD",
        }),
        coingecko=_stub_source(ok=True, transform_out={}),
        dexscreener=_stub_source(ok=True, transform_out={}),
    )
    monkeypatch.setattr(
        "signal_engine.core.async_fetch_chain_tvl_by_defillama_name",
        lambda: _async_return({}),
    )

    asyncio.run(refresh_chain_data(db_session))

    rows = db_session.query(SourceStatus).filter(SourceStatus.source_name == "defillama").all()
    assert len(rows) == 1
    # Status should not be "error" on a clean run.
    assert rows[0].status != "error"


def _async_return(value):
    async def _coro():
        return value
    return _coro()