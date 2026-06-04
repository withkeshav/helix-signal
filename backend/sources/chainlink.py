"""Legacy stub — replaced by plugins/chainlink.py.

This file exists only as a graceful fallback. The real implementation
is auto-discovered via @register_source("chainlink") in the plugins
directory. This stub logs a warning and delegates to the plugin.
"""

from __future__ import annotations

import warnings
from typing import Any

from sources.base import AbstractSource


class ChainlinkSource(AbstractSource):
    name = "chainlink"

    def fetch(self, **kwargs: Any) -> dict[str, Any]:
        warnings.warn(
            "Using legacy ChainlinkSource stub — plugin-based source at "
            "sources/plugins/chainlink.py is preferred",
            UserWarning,
            stacklevel=2,
        )

        from core.registry import get_source
        plugin = get_source("chainlink")
        if plugin is not None:
            return plugin.fetch(**kwargs)
        return {
            "source": "chainlink",
            "status": "unavailable",
            "note": "Chainlink plugin not loaded. Set CHAINLINK_RPC_URL in .env",
        }

    def transform(self, raw: dict[str, Any]) -> dict[str, Any]:
        return raw
