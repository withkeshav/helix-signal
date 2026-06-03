"""Tests for multi-source conflict resolution."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from models.quality import SourceStatus
from services.components.conflict_resolver import ConflictResolver, SourceRegistry


def _source_registry() -> SourceRegistry:
    r = SourceRegistry()
    r.register("coingecko", "price", priority=100, staleness_seconds=120)
    r.register("dexscreener", "price", priority=80, staleness_seconds=60)
    r.register("defillama", "price", priority=60, staleness_seconds=300)
    r.register("groq", "ai_insight", priority=90, staleness_seconds=300)
    r.register("ollama_cloud", "ai_insight", priority=70, staleness_seconds=300)
    return r


class TestSourceRegistry:
    def test_register_and_get(self) -> None:
        r = SourceRegistry()
        r.register("coingecko", "price", priority=100)
        assert r.get("coingecko") is not None
        assert r.get("coingecko")["data_type"] == "price"
        assert r.get("coingecko")["priority"] == 100

    def test_get_prioritized_orders_by_priority(self) -> None:
        r = _source_registry()
        ordered = r.get_prioritized("price")
        names = [s["name"] for s in ordered]
        assert names == ["coingecko", "dexscreener", "defillama"]

    def test_get_prioritized_filters_by_data_type(self) -> None:
        r = _source_registry()
        assert len(r.get_prioritized("price")) == 3
        assert len(r.get_prioritized("ai_insight")) == 2
        assert len(r.get_prioritized("sentiment")) == 0

    def test_is_fresh_no_db_assumes_fresh(self) -> None:
        r = _source_registry()
        assert r.is_fresh("coingecko") is True

    def test_is_fresh_checks_staleness(self, db_session) -> None:
        r = _source_registry()
        now = datetime.now(timezone.utc)
        db_session.add(SourceStatus(
            source_name="coingecko",
            status="ok",
            last_successful_fetch=now,
            updated_at=now,
        ))
        db_session.commit()
        assert r.is_fresh("coingecko", db=db_session) is True

    def test_is_fresh_stale_source(self, db_session) -> None:
        r = _source_registry()
        old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        db_session.add(SourceStatus(
            source_name="coingecko",
            status="ok",
            last_successful_fetch=old,
            updated_at=old,
        ))
        db_session.commit()
        assert r.is_fresh("coingecko", db=db_session) is False

    def test_get_prioritized_stale_pushed_back(self, db_session) -> None:
        r = _source_registry()
        now = datetime.now(timezone.utc)
        old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        db_session.add_all([
            SourceStatus(source_name="coingecko", status="ok", last_successful_fetch=old, updated_at=now),
            SourceStatus(source_name="dexscreener", status="ok", last_successful_fetch=now, updated_at=now),
            SourceStatus(source_name="defillama", status="ok", last_successful_fetch=now, updated_at=now),
        ])
        db_session.commit()
        names = [s["name"] for s in r.get_prioritized("price", db=db_session)]
        # dexscreener has higher priority than defillama and is fresh
        assert names[0] == "dexscreener"
        assert names[-1] == "coingecko"


class TestConflictResolver:
    def test_fallback_returns_fresh_source(self) -> None:
        r = _source_registry()
        resolver = ConflictResolver(r)
        prices = {"coingecko": 1.0001, "dexscreener": 1.0002, "defillama": 1.0000}
        result = resolver.resolve_with_fallback("price", prices)
        assert result["source"] == "coingecko"
        assert result["stale"] is False

    def test_fallback_skips_none(self) -> None:
        r = _source_registry()
        resolver = ConflictResolver(r)
        prices = {"coingecko": None, "dexscreener": 1.0002}
        result = resolver.resolve_with_fallback("price", prices)
        assert result["source"] == "dexscreener"

    def test_fallback_all_none(self) -> None:
        r = _source_registry()
        resolver = ConflictResolver(r)
        result = resolver.resolve_with_fallback("price", {"coingecko": None})
        assert result["value"] is None
        assert result["source"] is None

    def test_fallback_uses_stale_when_none_fresh(self, db_session) -> None:
        r = _source_registry()
        now = datetime.now(timezone.utc)
        # Only coingecko has data; no SourceStatus rows → not fresh
        prices = {"coingecko": 1.0001, "dexscreener": None}
        resolver = ConflictResolver(r)
        result = resolver.resolve_with_fallback("price", prices, db=db_session)
        assert result["source"] == "coingecko"
        assert result["stale"] is True

    def test_consensus_reaches_agreement(self) -> None:
        r = _source_registry()
        resolver = ConflictResolver(r)
        prices = {"coingecko": 1.0001, "dexscreener": 1.0002, "defillama": 1.0000}
        result = resolver.resolve_with_consensus("price", prices, min_agreement=2)
        assert result["consensus"] is True
        assert result["agreeing"] >= 2
        assert result["total"] == 3
        assert result["value"] == 1.0001  # median

    def test_consensus_rejects_outlier(self) -> None:
        r = _source_registry()
        resolver = ConflictResolver(r)
        prices = {"coingecko": 1.00, "dexscreener": 1.01, "defillama": 2.50}
        result = resolver.resolve_with_consensus("price", prices, min_agreement=2, tolerance_pct=2.0)
        assert result["consensus"] is True
        assert result["agreeing"] == 2
        assert "defillama" not in result["sources"]

    def test_consensus_fails_with_insufficient_agreement(self) -> None:
        r = _source_registry()
        resolver = ConflictResolver(r)
        prices = {"coingecko": 1.00, "dexscreener": 2.00, "defillama": 3.00}
        result = resolver.resolve_with_consensus("price", prices, min_agreement=3, tolerance_pct=1.0)
        assert result["consensus"] is False

    def test_consensus_empty_sources(self) -> None:
        r = _source_registry()
        resolver = ConflictResolver(r)
        result = resolver.resolve_with_consensus("price", {})
        assert result["consensus"] is False
        assert result["value"] is None

    def test_fallback_with_dict_values(self) -> None:
        r = _source_registry()
        r.register("groq", "ai_insight", priority=90)
        resolver = ConflictResolver(r)
        sources = {
            "groq": {"provider": "groq", "summary": "All stable", "value": 0.95},
        }
        result = resolver.resolve_with_consensus("ai_insight", sources, min_agreement=1)
        # Should extract numeric from dict via _extract_numeric
        # "value": 0.95 matches
        assert result["consensus"] is True
