# Signal Engine Components

This directory contains modular components for the signal engine, each responsible for a specific aspect of risk analysis and scoring.

## Component Overview

### `peg_analysis.py`
Functions for analyzing peg stability and deviation metrics.
- `peg_deviation()` - Calculate absolute and percentage deviation from 1:1 peg
- `peg_status_label()` - Convert price to status label (Healthy/Watch/Alert)
- `depeg_index_score()` - Calculate depeg risk score (0-100)

### `concentration.py`
Functions for measuring and scoring concentration risk.
- `concentration_component()` - Calculate concentration score using Herfindahl-Hirschman Index
- `composite_band()` - Convert concentration score to risk band

### `supply_momentum.py`
Functions for analyzing supply velocity and momentum.
- `supply_momentum_component()` - Calculate supply momentum score
- `chain_supply_momentum()` - Calculate chain-level supply momentum metrics
- `_momentum_label()` - Convert momentum percentages to descriptive labels

### `data_confidence.py`
Functions for measuring data quality and confidence levels.
- `chain_data_confidence()` - Calculate data confidence score based on freshness
- `composite_confidence_band()` - Convert confidence score to band label

### `composite_scoring.py`
Functions for combining individual scores into composite risk assessments.
- `compute_risk_score()` - Calculate overall risk score from component metrics
- `compute_freshness()` - Calculate data freshness metrics
- `_score_to_band()` - Convert risk score to descriptive band

## Benefits

- **Modularity**: Each component has a single responsibility
- **Testability**: Components can be tested independently
- **Maintainability**: Changes to one component don't affect others
- **Reusability**: Components can be used in different contexts
- **Clarity**: Clear interfaces make code easier to understand

## Usage

Each component exports functions that can be imported directly:

```python
from signal_engine.components.peg_analysis import peg_deviation, depeg_index_score
from signal_engine.components.concentration import concentration_component

# Calculate peg deviation
deviation, percentage = peg_deviation(1.0002)

# Calculate depeg score
score = depeg_index_score(1.0002)

# Calculate concentration metrics
chain_shares = [0.4, 0.3, 0.2, 0.1]  # 40%, 30%, 20%, 10%
concentration_score, details = concentration_component(chain_shares)
```