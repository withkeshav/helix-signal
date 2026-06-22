# Scoring Design

Helix Signal uses two distinct scoring formulas depending on the level of granularity.

## Asset-Level Score

Used in `compute_risk_score()` (`signal_engine/components/composite_scoring.py`). Applied per asset (e.g., USDT, USDC).

| Component       | Weight | Source |
|-----------------|--------|--------|
| Depeg index     | 0.35   | `peg_analysis.py` |
| Concentration   | 0.25   | `concentration.py` |
| Supply velocity | 0.20   | `supply_momentum.py` |
| Age penalty     | 0.20   | inline in `composite_scoring.py` |

**Band thresholds:** ≤20 Normal, ≤60 Watch, >60 Alert.

## Chain-Level Score

Used in `chain_row_signal()` (`signal_engine/scoring.py`). Applied per chain within an asset.

| Component       | Weight | Source |
|-----------------|--------|--------|
| Chain share     | 0.40   | supply share % binned into tiers |
| Depeg index     | 0.40   | `peg_analysis.py` |
| Momentum        | 0.20   | `supply_momentum.py` |

**Why different weights?** At the chain level, concentration is expressed directly as `chain_share_pct` (if a single chain holds 50%+ of supply, it contributes maximum risk). The asset-level concentration component aggregates across all chains using the Herfindahl-style `concentration_component()`. Asset-level age penalty is omitted at the chain level because chain snapshots are fresher by nature.

**Band thresholds:** same as asset-level — ≤20 Normal, ≤60 Watch, >60 Alert (via `composite_band()`).
