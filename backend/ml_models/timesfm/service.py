"""Standalone FastAPI service for TimesFM forecasting."""

from datetime import datetime, timedelta, timezone
from typing import List

import numpy as np
import timesfm
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="TimesFM Forecast Service")

_model = None
_start_time = None


@app.on_event("startup")
def load_model():
    global _model, _start_time
    _start_time = datetime.now(timezone.utc)
    _model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(
        "google/timesfm-2.5-200m-pytorch"
    )
    _model.compile(timesfm.ForecastConfig(
        max_context=1024,
        max_horizon=256,
        normalize_inputs=True,
        use_continuous_quantile_head=True,
        force_flip_invariance=True,
        infer_is_positive=True,
        fix_quantile_crossing=True,
    ))


class ForecastRequest(BaseModel):
    series_id: str
    values: List[float]
    timestamps: List[str]
    horizon: int = 24
    frequency: str = "5min"


class ForecastResponse(BaseModel):
    series_id: str
    model: str = "timesfm_2_5_200m"
    version: str = "2.5.0"
    horizon: int
    point: List[float]
    forecast_timestamps: List[str]
    quantiles: dict
    generated_at: str


@app.post("/forecast", response_model=ForecastResponse)
def forecast(req: ForecastRequest):
    effective_horizon = min(req.horizon, 256)
    point, quantiles = _model.forecast(
        horizon=effective_horizon,
        inputs=[req.values],
    )

    last_ts = datetime.fromisoformat(req.timestamps[-1])
    if req.frequency == "5min":
        delta = timedelta(minutes=5)
    elif req.frequency == "hourly":
        delta = timedelta(hours=1)
    elif req.frequency == "daily":
        delta = timedelta(days=1)
    else:
        delta = timedelta(minutes=5)
    forecast_timestamps = [(last_ts + delta * (i + 1)).isoformat() for i in range(effective_horizon)]

    return ForecastResponse(
        series_id=req.series_id,
        horizon=effective_horizon,
        point=point[0].tolist(),
        forecast_timestamps=forecast_timestamps,
        quantiles={
            "q10": quantiles[0, :, 1].tolist(),
            "q20": quantiles[0, :, 2].tolist(),
            "q30": quantiles[0, :, 3].tolist(),
            "q40": quantiles[0, :, 4].tolist(),
            "q50": quantiles[0, :, 5].tolist(),
            "q60": quantiles[0, :, 6].tolist(),
            "q70": quantiles[0, :, 7].tolist(),
            "q80": quantiles[0, :, 8].tolist(),
            "q90": quantiles[0, :, 9].tolist(),
        },
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    uptime_seconds: float


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok" if _model else "error",
        model_loaded=_model is not None,
        uptime_seconds=(datetime.now(timezone.utc) - _start_time).total_seconds(),
    )
