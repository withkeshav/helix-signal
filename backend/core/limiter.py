"""Shared rate limiter instance — imported by route modules to avoid circular imports."""

import os

from fastapi import Request
from slowapi import Limiter

_storage_uri = os.getenv("RATE_LIMITER_STORAGE_URI", "")
_storage_opts = {"storage_uri": _storage_uri} if _storage_uri else {}


def _get_remote_address(request: Request) -> str:
    cidr = os.getenv("TRUSTED_PROXY_CIDR", "").strip()
    if cidr and request.client:
        from ipaddress import ip_address, ip_network
        if ip_address(request.client.host) not in ip_network(cidr, strict=False):
            return request.client.host
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


limiter = Limiter(key_func=_get_remote_address, **_storage_opts)

# For multi-worker deployments, set RATE_LIMITER_STORAGE_URI to a Redis URL:
#   RATE_LIMITER_STORAGE_URI=redis://redis:6379/0
