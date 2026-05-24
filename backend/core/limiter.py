"""Shared rate limiter instance — imported by route modules to avoid circular imports."""

import os

from slowapi import Limiter
from slowapi.util import get_remote_address

_storage_uri = os.getenv("RATE_LIMITER_STORAGE_URI", "")
_storage_opts = {"storage_uri": _storage_uri} if _storage_uri else {}
limiter = Limiter(key_func=get_remote_address, **_storage_opts)
