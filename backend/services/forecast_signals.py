"""Generate risk signals from TimesFM forecast quantiles."""

from datetime import datetime, timezone


def evaluate_forecast_risk(asset_symbol: str, metric: str, forecast_points: list) -> list[dict]:
    """Evaluate forecast quantiles and generate risk signals."""
    signals = []

    if metric == "price":
        for fp in forecast_points:
            if fp.q10 is not None and fp.q10 < 0.985:
                signals.append({
                    "asset_symbol": asset_symbol,
                    "event_type": "forecast_depeg_risk",
                    "severity": "critical" if fp.q10 < 0.97 else "warning",
                    "title": f"Depeg risk detected for {asset_symbol}",
                    "summary": f"q10 forecast at step {fp.horizon_step}: ${fp.q10:.4f}",
                    "threshold": "0.985",
                    "forecast_value": fp.q10,
                    "horizon_step": fp.horizon_step,
                    "timestamp": datetime.now(timezone.utc),
                })

    elif metric == "total_supply":
        for fp in forecast_points:
            if fp.q10 is not None and fp.q90 is not None:
                spread = abs(fp.q90 - fp.q10) / max(abs(fp.q50 or 1), 1)
                if spread > 0.05:
                    signals.append({
                        "asset_symbol": asset_symbol,
                        "event_type": "forecast_supply_uncertainty",
                        "severity": "warning",
                        "title": f"Supply forecast uncertainty for {asset_symbol}",
                        "summary": f"q10-q90 spread at step {fp.horizon_step}: {spread:.2%}",
                        "threshold": "5%",
                        "forecast_value": spread,
                        "horizon_step": fp.horizon_step,
                        "timestamp": datetime.now(timezone.utc),
                    })

    elif metric == "concentration_score":
        for fp in forecast_points:
            if fp.q50 is not None and fp.q50 > 70:
                signals.append({
                    "asset_symbol": asset_symbol,
                    "event_type": "forecast_concentration_risk",
                    "severity": "warning",
                    "title": f"Concentration risk forecast for {asset_symbol}",
                    "summary": f"q50 forecast at step {fp.horizon_step}: {fp.q50:.1f}",
                    "threshold": "70",
                    "forecast_value": fp.q50,
                    "horizon_step": fp.horizon_step,
                    "timestamp": datetime.now(timezone.utc),
                })

    return signals
