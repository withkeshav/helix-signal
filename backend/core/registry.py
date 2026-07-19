"""Plugin registry system — auto-discovers sources, models, loaders."""

import importlib
import pkgutil
from typing import Any

from structlog import get_logger

SOURCES_REGISTRY: dict[str, type] = {}
SOURCE_INSTANCES: dict[str, Any] = {}
ML_MODELS_REGISTRY: dict[str, type] = {}
CHAIN_LOADERS: dict[str, type] = {}

log = get_logger(__name__)


def register_source(name: str):
    """Decorator: register a source plugin."""
    def wrapper(cls):
        SOURCES_REGISTRY[name] = cls
        return cls
    return wrapper


def register_model(name: str):
    """Decorator: register an ML model plugin."""
    def wrapper(cls):
        ML_MODELS_REGISTRY[name] = cls
        return cls
    return wrapper


def register_chain(chain_key: str):
    """Decorator: register a chain loader."""
    def wrapper(cls):
        CHAIN_LOADERS[chain_key] = cls
        return cls
    return wrapper


def get_source(name: str):
    """Return a singleton instance of the source plugin.
    Circuit breaker state is preserved across requests because the same
    instance is reused. Never call source_cls() directly from routes.
    """
    if name not in SOURCES_REGISTRY:
        return None
    if name not in SOURCE_INSTANCES:
        SOURCE_INSTANCES[name] = SOURCES_REGISTRY[name]()
    return SOURCE_INSTANCES[name]


def discover_plugins():
    """Auto-discover all plugins in sources/plugins/ and ml_models/."""
    try:
        import backend.sources.plugins
        pkg_path = backend.sources.plugins.__path__
        prefix = "backend.sources.plugins."
    except ModuleNotFoundError:
        try:
            import sources.plugins
            pkg_path = sources.plugins.__path__
            prefix = "sources.plugins."
        except ModuleNotFoundError:
            log.warning("plugins_module_not_found", module="sources.plugins")
            return

    for importer, name, is_pkg in pkgutil.iter_modules(pkg_path):
        importlib.import_module(f"{prefix}{name}")

    try:
        import backend.ml_models
        for importer, name, is_pkg in pkgutil.iter_modules(backend.ml_models.__path__):
            try:
                importlib.import_module(f"backend.ml_models.{name}")
            except Exception as exc:
                log.warning("ml_plugin_import_failed", module=name, exc_info=True)
    except ModuleNotFoundError:
        log.warning("plugins_module_not_found", module="ml_models")
