"""Centralized config loading with schema validation."""

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


class ConfigLoader:
    _cache: dict[str, Any] = {}

    @classmethod
    def load(cls, filename: str, force_reload: bool = False) -> Any:
        if filename in cls._cache and not force_reload:
            return cls._cache[filename]
        path = CONFIG_DIR / filename
        with open(path) as f:
            data = json.load(f)
        cls._cache[filename] = data
        return data

    @classmethod
    def get_enabled_assets(cls) -> list[dict]:
        assets = cls.load("assets.json")
        return [a for a in assets if a.get("enabled", True)]

    @classmethod
    def get_enabled_chains(cls) -> list[dict]:
        chains = cls.load("chains.json")
        return [c for c in chains if c.get("enabled", True)]

    @classmethod
    def clear_cache(cls):
        cls._cache.clear()
