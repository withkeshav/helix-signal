"""Model registry with health checks — queries remote inference services."""

import os
from typing import Any

import requests

from backend.core.registry import ML_MODELS_REGISTRY


class ModelService:
    def __init__(self, name: str, endpoint: str | None = None):
        self.name = name
        self.endpoint = endpoint or os.getenv(f"{name.upper()}_ENDPOINT", f"http://{name}:8100")

    def health_check(self) -> dict[str, Any]:
        try:
            resp = requests.get(f"{self.endpoint}/health", timeout=5)
            return resp.json()
        except Exception:
            return {"status": "unreachable"}

    def forecast(self, series_id: str, values: list[float], timestamps: list[str], horizon: int = 24) -> dict[str, Any]:
        resp = requests.post(
            f"{self.endpoint}/forecast",
            json={
                "series_id": series_id,
                "values": values,
                "timestamps": timestamps,
                "horizon": horizon,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


def get_model_service(name: str) -> ModelService | None:
    if name not in ML_MODELS_REGISTRY:
        return None
    return ModelService(name)
