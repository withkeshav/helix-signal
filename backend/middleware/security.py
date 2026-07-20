"""Security middleware — input validation, sanitization, CSP, rate limiting."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

VALID_SYMBOL = re.compile(r"^[A-Z0-9]{2,16}$")
VALID_WINDOWS = frozenset({"6h", "24h", "7d", "30d", "90d"})

_HTML_TAG = re.compile(r"<[^>]*>")


def strip_html(text: str) -> str:
    return _HTML_TAG.sub("", text)


def sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return strip_html(value)
    if isinstance(value, dict):
        return {k: sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_value(v) for v in value]
    return value

_CSP = os.getenv(
    "CONTENT_SECURITY_POLICY",
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-eval' 'sha256-9RZrN3RExF+0bvaRfEqFGDB1AuQYP7U9C++sm12qeCQ=' 'sha256-YY7B1+ExoluQx0JdcMuQ3KniZujV85d3RORaBWuEbAE='; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
    "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'",
)


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
            safe_params = sanitize_query_params(dict(request.query_params))
            for key, val in request.query_params.items():
                if key in ("asset",):
                    try:
                        validate_asset_symbol(val)
                    except HTTPException as e:
                        return JSONResponse(
                            status_code=400,
                            content={"detail": e.detail},
                        )
                if key == "assets":
                    for sym in val.split(","):
                        sym = sym.strip()
                        if sym:
                            try:
                                validate_asset_symbol(sym)
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

        body = await request.body()
        if body and request.headers.get("content-type", "").startswith("application/json"):
            try:
                data = json.loads(body)
                sanitized = sanitize_value(data)
                if sanitized != data:
                    sanitized_body = json.dumps(sanitized).encode()

                    async def sanitized_receive():
                        return {"type": "http.request", "body": sanitized_body, "more_body": False}

                    request = Request(scope=request.scope, receive=sanitized_receive)
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        response = await call_next(request)
        if _CSP:
            response.headers["Content-Security-Policy"] = _CSP
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        if request.url.scheme == "https" or os.getenv("HELIX_ENABLE_HSTS", "").lower() in (
            "1",
            "true",
            "yes",
        ):
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
