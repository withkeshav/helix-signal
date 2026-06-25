from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from providers.rate_limiter import TokenBucket


@dataclass
class ProviderConfig:
    """Metadata and runtime config for a data provider."""
    name: str
    label: str
    description: str
    requires_key: bool = False
    key_env_var: str | None = None
    free_tier: dict | None = None
    always_active: bool = False
    refresh_interval_seconds: int = 300
    enabled: bool = True


class DataProvider(ABC):
    """Abstract base for all data providers.

    Core data sources (DefiLlama, DexScreener, CoinGecko) are always
    active. Optional providers (CoinMarketCap, Moralis, etc.) can be
    toggled from the Settings page and require API keys.
    """

    @property
    @abstractmethod
    def config(self) -> ProviderConfig:
        ...

    @abstractmethod
    def fetch(self, metric: str, **kwargs: Any) -> dict[str, Any] | None:
        ...

    def rate_limiter(self) -> TokenBucket | None:
        ft = self.config.free_tier
        if ft and "rate_per_second" in ft:
            return TokenBucket(
                rate=ft["rate_per_second"],
                burst=ft.get("burst", int(ft["rate_per_second"])),
            )
        return None
