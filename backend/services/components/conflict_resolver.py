"""Multi-source conflict resolution — priority + staleness + consensus.

Replaces ad-hoc cross_source_price_check with a generalised mechanism
for resolving overlapping data from multiple sources (price, sentiment,
AI insights).

Usage:
    registry = SourceRegistry()
    registry.register("coingecko", "price", priority=100, staleness_seconds=120)
    registry.register("dexscreener", "price", priority=80, staleness_seconds=60)
    registry.register("defillama", "price", priority=60, staleness_seconds=300)

    resolver = ConflictResolver(registry)
    best = resolver.resolve_with_fallback("price", prices, db=db)
    consensus = resolver.resolve_with_consensus("price", prices, min_agreement=2, db=db)
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from models.quality import SourceStatus


def _age_seconds(fetched: datetime | None) -> int | None:
    if fetched is None:
        return None
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return int((datetime.now(timezone.utc) - fetched).total_seconds())


def _extract_numeric(raw: Any) -> float | None:
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, dict):
        return raw.get("value") or raw.get("price") or None
    return None


class SourceRegistry:
    """Register data sources with priority + staleness per data type.

    Higher priority sources are preferred when fresh.  Staleness is
    determined from the existing ``SourceStatus.last_successful_fetch``
    table — no new schema required.
    """

    def __init__(self) -> None:
        self._sources: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        data_type: str,
        *,
        priority: int = 100,
        staleness_seconds: int = 300,
    ) -> None:
        self._sources[name] = {
            "name": name,
            "data_type": data_type,
            "priority": priority,
            "staleness_seconds": staleness_seconds,
        }

    def get(self, name: str) -> dict[str, Any] | None:
        return self._sources.get(name)

    def is_fresh(self, name: str, db: Session | None = None) -> bool:
        meta = self._sources.get(name)
        if not meta:
            return False
        if db is None:
            return True
        row = db.query(SourceStatus).filter(
            SourceStatus.source_name == name
        ).first()
        if not row or not row.last_successful_fetch:
            return False
        age = _age_seconds(row.last_successful_fetch)
        return age is not None and age <= meta["staleness_seconds"]

    def get_prioritized(
        self, data_type: str, *, db: Session | None = None
    ) -> list[dict[str, Any]]:
        sources = [
            s for s in self._sources.values()
            if s["data_type"] == data_type
        ]
        sources.sort(key=lambda s: s["priority"], reverse=True)
        if db is None:
            return sources
        fresh, stale = [], []
        for s in sources:
            (fresh if self.is_fresh(s["name"], db=db) else stale).append(s)
        return fresh + stale


class ConflictResolver:
    """Resolve conflicting data from multiple sources."""

    def __init__(self, registry: SourceRegistry) -> None:
        self._registry = registry

    def resolve_with_fallback(
        self,
        data_type: str,
        sources: dict[str, Any | None],
        *,
        db: Session | None = None,
    ) -> dict[str, Any]:
        """Priority-based resolution with staleness fallback.

        Returns the first fresh source that has non-None data.
        If no source is fresh, returns the highest-priority non-None
        result regardless of staleness.
        """
        ordered = self._registry.get_prioritized(data_type, db=db)
        best: dict[str, Any] | None = None
        for meta in ordered:
            name = meta["name"]
            value = sources.get(name)
            if value is None:
                continue
            if best is None:
                best = {"source": name, "value": value, "stale": True}
            if self._registry.is_fresh(name, db=db):
                return {"source": name, "value": value, "stale": False}
        return best or {"source": None, "value": None, "stale": True}

    def resolve_with_consensus(
        self,
        data_type: str,
        sources: dict[str, Any],
        *,
        min_agreement: int = 2,
        tolerance_pct: float = 1.0,
        db: Session | None = None,
    ) -> dict[str, Any]:
        """N-of-M consensus resolution.

        Collects numeric values from all available sources for
        *data_type*, then requires at least *min_agreement* sources
        to fall within *tolerance_pct* of the median.

        Returns the median as the canonical value when consensus is
        reached, along with metadata about which sources agreed.
        """
        ordered = self._registry.get_prioritized(data_type, db=db)
        values: list[tuple[str, float]] = []
        for meta in ordered:
            name = meta["name"]
            raw = sources.get(name)
            if raw is None:
                continue
            num = _extract_numeric(raw)
            if num is not None:
                values.append((name, num))
        if not values:
            return {"consensus": False, "source": None, "value": None,
                    "agreeing": 0, "total": 0}
        vals = [v for _, v in values]
        median = statistics.median(vals)
        agreeing = [(n, v) for n, v in values
                    if abs(v - median) / max(median, 1e-9) * 100 <= tolerance_pct]
        return {
            "consensus": len(agreeing) >= min_agreement,
            "source": agreeing[0][0] if agreeing else values[0][0],
            "value": median,
            "agreeing": len(agreeing),
            "total": len(values),
            "sources": [n for n, _ in agreeing],
        }
