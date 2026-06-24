"""Peg analysis components for stablecoin monitoring."""

from typing import Tuple


def peg_deviation(price: float | None) -> Tuple[float, float]:
    """Calculate peg deviation metrics."""
    if price is None or price <= 0:
        return (1.0, 100.0)
    dev = abs(float(price) - 1.0)
    pct = dev * 100.0
    return (dev, pct)


def peg_status_label(price: float | None) -> str:
    """Get peg status label based on price."""
    dev, _ = peg_deviation(price)
    if dev <= 0.001:
        return "Healthy"
    if dev <= 0.005:
        return "Watch"
    return "Alert"


# Breakpoints for continuous depeg index interpolation: (deviation_pct, score)
_DEPEG_BREAKPOINTS = [(0, 0), (0.1, 0), (0.5, 25), (1.0, 50), (2.0, 75), (4.0, 100)]


def _interpolate_breakpoints(pct: float, breakpoints: list[tuple[float, float]]) -> float:
    if pct <= breakpoints[0][0]:
        return float(breakpoints[0][1])
    for i in range(1, len(breakpoints)):
        x0, y0 = breakpoints[i - 1]
        x1, y1 = breakpoints[i]
        if pct <= x1:
            if x1 == x0:
                return float(y1)
            t = (pct - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return float(breakpoints[-1][1])


def depeg_index_score(price: float | None) -> int:
    """Calculate depeg index score via linear interpolation between breakpoints."""
    if price is None:
        return 100
    _, pct = peg_deviation(price)
    return int(round(_interpolate_breakpoints(pct, _DEPEG_BREAKPOINTS)))
