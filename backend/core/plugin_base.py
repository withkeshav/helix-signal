"""Abstract base classes for source and model plugins."""

from abc import ABC, abstractmethod
from typing import Any


class AbstractModel(ABC):
    name: str = "abstract"
    version: str = "0.0.0"

    @abstractmethod
    def predict(self, features: dict) -> dict:
        ...
