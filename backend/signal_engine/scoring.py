"""Signal engine scoring components.

This module has been refactored to use componentized functions from
signal_engine/components/ for better maintainability and testability.
"""

from __future__ import annotations

from typing import Any


# Import component modules
from signal_engine.components.peg_analysis import (
    peg_deviation, peg_status_label, depeg_index_score
)
from signal_engine.components.concentration import (
    concentration_component, composite_band
)
from signal_engine.components.supply_momentum import (
    supply_momentum_component, chain_supply_momentum
)
from signal_engine.components.data_confidence import (
    chain_data_confidence, composite_confidence_band
)
from signal_engine.components.composite_scoring import (
    compute_risk_score, compute_freshness
)

def chain_row_signal(
    chain_share_pct: float | None, 
    peg_price: float | None, *, 
    momentum_score_hint: int | None = None
) -> dict[str, Any]:
    """Calculate chain row signal score.
    
    Args:
        chain_share_pct: Chain share percentage
        peg_price: Current peg price
        momentum_score_hint: Optional momentum score hint
        
    Returns:
        Dictionary with score and band
    """
    if chain_share_pct is None:
        chain_score = 0
    elif chain_share_pct >= 50:
        chain_score = 100
    elif chain_share_pct >= 25:
        chain_score = 75
    elif chain_share_pct >= 10:
        chain_score = 50
    elif chain_share_pct >= 5:
        chain_score = 25
    else:
        chain_score = 0

    depeg_score = depeg_index_score(peg_price)
    
    momentum_score = momentum_score_hint if momentum_score_hint is not None else 0

    composite = int((chain_score * 0.4 + depeg_score * 0.4 + momentum_score * 0.2))
    band = composite_band(composite)

    return {"score": composite, "band": band}

# Maintain backwards compatibility by exporting the original functions
__all__ = [
    'peg_deviation', 'peg_status_label', 'depeg_index_score',
    'concentration_component', 'composite_band',
    'supply_momentum_component', 'chain_supply_momentum',
    'chain_data_confidence', 'composite_confidence_band',
    'compute_risk_score', 'compute_freshness', 'chain_row_signal'
]