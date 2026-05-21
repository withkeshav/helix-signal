"""MLflow logging for predictive runs (optional; failures are non-fatal)."""

from __future__ import annotations

import os
from typing import Any


def log_predictive_run(*, asset_symbol: str, metrics: dict[str, Any], params: dict[str, Any] | None = None) -> None:
    if os.getenv("ENABLE_MLFLOW", "true").strip().lower() in ("0", "false", "no"):
        return
    uri = os.getenv("MLFLOW_TRACKING_URI", "").strip()
    if not uri:
        return
    try:
        import mlflow

        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment(os.getenv("MLFLOW_EXPERIMENT", "helix-predictive"))
        with mlflow.start_run(run_name=f"predictive-{asset_symbol}", nested=True):
            if params:
                mlflow.log_params({k: str(v) for k, v in params.items()})
            flat: dict[str, float] = {}
            for k, v in metrics.items():
                if isinstance(v, (int, float)):
                    flat[k] = float(v)
                elif k == "depeg_probability" and isinstance(v, dict):
                    for hk, hv in v.items():
                        if isinstance(hv, (int, float)):
                            flat[f"depeg_{hk}"] = float(hv)
            if flat:
                mlflow.log_metrics(flat)
    except Exception:
        pass
