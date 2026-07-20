"""Scoped API resource bundles and route mapping (Phase 5).

Bundles grant access to groups of intelligence routes. Keys store bundle names
in ``ApiKey.scopes``; optional ``access_policy`` further restricts assets and
history depth.

Route mapping (conceptual — enforced via ``require_read_open`` /
``require_keyed_always`` on each router):

  core:read
    GET /api/health, /api/version (public)
    GET /api/dashboard, /api/dashboard/summary, /api/assets
    GET /api/sources/status, /api/sources/usage, /api/dews

  trends:read
    GET /api/trends, /api/trends/chains

  events:read
    GET /api/events, /api/event-labels

  osint:read
    GET /api/osint/feed, /api/osint/sentiment, /api/osint/attestation, /api/osint/correlate

  risk:read
    GET /api/predictive, /api/forecasts, /api/compare
    GET /api/analytics/*, /api/anomaly/*
    GET /api/onchain/whale-flow, /api/onchain/holder-concentration
    GET /api/v1/assets/*/yield, /api/v1/series/*

  forensics:read
    GET /api/v1/blacklist/events, /api/v1/blacklist/stats
    GET /api/v1/tags/{address}

  export:read
    GET /api/trends/export, /api/events/export

  investigate:write
    POST /api/v1/investigate

  admin
    GET/POST/DELETE /api/v1/api-keys, /api/v1/tags (write), /api/assets/catalog
    Settings, playbooks, and other operator routes

Back-compat: ``intelligence:read`` on a key is treated as the union of all
``*:read`` bundles (not ``investigate:write`` or ``admin``).
"""

from __future__ import annotations

READ_BUNDLES: frozenset[str] = frozenset(
    {
        "core:read",
        "trends:read",
        "events:read",
        "osint:read",
        "risk:read",
        "forensics:read",
        "export:read",
    }
)

WRITE_BUNDLES: frozenset[str] = frozenset({"investigate:write"})

ADMIN_BUNDLES: frozenset[str] = frozenset({"admin"})

ALL_BUNDLES: frozenset[str] = READ_BUNDLES | WRITE_BUNDLES | ADMIN_BUNDLES

# Legacy alias expanded at auth time.
LEGACY_READ_ALIAS = "intelligence:read"

VALID_SCOPES: frozenset[str] = ALL_BUNDLES | frozenset({LEGACY_READ_ALIAS})

DEFAULT_SCOPES: list[str] = ["core:read"]

WINDOW_HOURS: dict[str, int] = {
    "6h": 6,
    "24h": 24,
    "7d": 24 * 7,
    "30d": 24 * 30,
    "90d": 24 * 90,
}


def expand_legacy_scopes(scopes: set[str]) -> set[str]:
    """Expand intelligence:read to all read bundles."""
    out = set(scopes)
    if LEGACY_READ_ALIAS in out:
        out.discard(LEGACY_READ_ALIAS)
        out |= READ_BUNDLES
    return out


def window_to_hours(window: str) -> int | None:
    return WINDOW_HOURS.get((window or "").strip().lower())
