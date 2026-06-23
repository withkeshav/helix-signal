# Scoring Design

Helix Signal uses two distinct scoring formulas depending on the level of granularity.

## Asset-Level Score

Used in `compute_risk_score()` (`signal_engine/components/composite_scoring.py`). Applied per asset (e.g., USDT, USDC).

| Component       | Weight | Source |
|-----------------|--------|--------|
| Depeg index     | 0.35   | `peg_analysis.py` (continuous interpolation) |
| Concentration   | 0.20   | `concentration.py` (crypto HHI + DEX pool share) |
| Supply velocity | 0.15   | `risk_inputs.inject_velocity()` → `composite_scoring.py` |
| Liquidity depth | 0.10   | `liquidity_depth_score()` from `slippage_100k_bps` |
| Age penalty     | 0.20   | 4-tier freshness model in `composite_scoring.py` |

**Velocity:** Contracting supply (negative %) contributes via `abs(velocity)` — no directional guard.

**Depeg index:** Linear interpolation between breakpoints `[(0,0), (0.1,0), (0.5,25), (1.0,50), (2.0,75), (4.0,100)]`.

**Age penalty tiers:** fresh (<1h)=0, aging (<2h)=10, stale (<24h)=15, very stale (≥24h)=20.

**Band thresholds:** ≤20 Normal, ≤60 Watch, >60 Alert (from `_score_to_band` in composite_scoring.py).

## Chain-Level Score

Used in `chain_row_signal()` (`signal_engine/scoring.py`). Applied per chain within an asset.

| Component       | Weight | Source |
|-----------------|--------|--------|
| Chain share     | 0.40   | supply share % binned into tiers |
| Depeg index     | 0.40   | `peg_analysis.py` |
| Momentum        | 0.20   | `supply_momentum_component()` via `momentum_score_hint` |

**Band thresholds:** same as asset-level — ≤20 Normal, ≤60 Watch, >60 Alert (via `composite_band()`).

## Health Flag

`source_health` is returned as a string (`"OK"` or `"DEGRADED"`) in the `components` dict. It is **not** a weighted score component.

## Regime Classification (Predictive)

`services/predictive.py` `_regime_state`: stable / volatile (≥40) / alert (≥61) / crisis (≥80).

## Webhook Alerts

Signal events emitted during `persist_trends_and_events` can be forwarded to external webhooks. See [webhook-alerts.md](guides/webhook-alerts.md).
