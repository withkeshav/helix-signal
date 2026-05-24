"""Security middleware — input validation, sanitization, rate limiting."""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

VALID_SYMBOL = re.compile(r"^[A-Z0-9]{2,16}$")
VALID_WINDOWS = frozenset({"24h", "7d", "30d", "90d"})


def validate_asset_symbol(symbol: str) -> str:
    cleaned = symbol.strip().upper()
    if not VALID_SYMBOL.match(cleaned):
        raise HTTPException(status_code=400, detail=f"Invalid asset symbol: {symbol}")
    return cleaned


def validate_window(window: str) -> str:
    w = window.strip().lower()
    if w not in VALID_WINDOWS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid window: {window}. Use one of {sorted(VALID_WINDOWS)}",
        )
    return w


_SENSITIVE_PARAMS = re.compile(r"(api_key|token|secret|password|key|auth)", re.IGNORECASE)


def sanitize_query_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        k: ("[REDACTED]" if _SENSITIVE_PARAMS.search(k) else v)
        for k, v in params.items()
    }


class SecurityValidationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        if path.startswith(("/api/", "/metrics")):
            for key, val in request.query_params.items():
                if key in ("asset",):
                    try:
                        validate_asset_symbol(val)
                    except HTTPException as e:
                        return JSONResponse(
                            status_code=400,
                            content={"detail": e.detail},
                        )
                if key == "window":
                    try:
                        validate_window(val)
                    except HTTPException as e:
                        return JSONResponse(
                            status_code=400,
                            content={"detail": e.detail},
                        )

        return await call_next(request)
