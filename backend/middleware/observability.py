"""Observability middleware — structured logging, Prometheus metrics, request tracking."""

from __future__ import annotations

import time

from fastapi import Request
from prometheus_client import Counter, Histogram, Gauge
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from middleware.security import sanitize_query_params

from structlog import get_logger

log = get_logger(__name__)

METRIC_REQUEST_COUNT = Counter(
    "helix_http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)
METRIC_REQUEST_LATENCY = Histogram(
    "helix_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
METRIC_SOURCE_HEALTH = Gauge(
    "helix_source_health", "Source health status", ["source"]
)
METRIC_MODEL_LATENCY = Histogram(
    "helix_model_inference_seconds",
    "Model inference latency",
    ["model"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
METRIC_CACHE_HIT_RATIO = Gauge(
    "helix_cache_hit_ratio", "Cache hit ratio per data type", ["data_type"]
)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.monotonic()
        try:
            response: Response = await call_next(request)
        except Exception:
            METRIC_REQUEST_COUNT.labels(method=request.method, endpoint=getattr(request.scope.get("route"), "path", request.url.path), status="500").inc()
            raise
        duration = time.monotonic() - start
        endpoint = getattr(request.scope.get("route"), "path", request.url.path)
        METRIC_REQUEST_COUNT.labels(
            method=request.method,
            endpoint=endpoint,
            status=str(response.status_code),
        ).inc()
        METRIC_REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=endpoint,
        ).observe(duration)
        log.info(
            "request",
            method=request.method,
            path=endpoint,
            status=response.status_code,
            duration_ms=round(duration * 1000, 2),
            query=sanitize_query_params(dict(request.query_params)),
        )
        return response
