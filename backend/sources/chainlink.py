from __future__ import annotations

from typing import Any

from sources.base import AbstractSource


class ChainlinkSource(AbstractSource):
    name = "chainlink"

    def fetch(self, **kwargs: Any) -> dict[str, Any]:
        return {}

    def transform(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {}
