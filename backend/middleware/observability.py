"""Observability middleware — structured logging, request tracking."""

from __future__ import annotations

import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from middleware.security import sanitize_query_params

from structlog import get_logger

log = get_logger(__name__)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.monotonic()
        response: Response = await call_next(request)
        duration = time.monotonic() - start
        endpoint = getattr(request.scope.get("route"), "path", request.url.path)
        log.info(
            "request",
            method=request.method,
            path=endpoint,
            status=response.status_code,
            duration_ms=round(duration * 1000, 2),
            query=sanitize_query_params(dict(request.query_params)),
        )
        return response
