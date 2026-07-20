# Plugin Development

Three plugin types: **Source**, **Model**, and **Chain Loader**. Each registers into a central registry via decorators.

## Source Plugin

Create `backend/sources/plugins/my_source.py`:

```python
from backend.core.registry import register_source
from backend.sources.base import AbstractSource
from backend.core.circuit_breaker import CircuitBreaker

@register_source("my_source")
class MySource(AbstractSource):
    name = "my_source"
    config_schema = {
        "api_key": {"type": str, "required": False},
        "base_url": {"type": str, "required": True},
    }

    def __init__(self):
        super().__init__()
        self.circuit_breaker = CircuitBreaker(name="my_source")

    def fetch(self, **kwargs) -> dict:
        def _do_fetch():
            return {"data": "real data here"}
        def _fallback():
            return {"status": "degraded", "data": None}
        return self.circuit_breaker.call(_do_fetch, fallback=_fallback)

    def health_check(self) -> dict:
        return {
            "source": self.name,
            "state": self.circuit_breaker.state.value,
            "failure_count": self.circuit_breaker.failure_count,
        }
```

Auto-discovered on startup - no import registration needed.

## ML Model Plugin

Create `backend/ml_models/my_model/__init__.py`:

```python
from backend.core.registry import register_model
from backend.core.plugin_base import AbstractModel

@register_model("my_model")
class MyModel(AbstractModel):
    name = "my_model"
    version = "1.0.0"

    def predict(self, features: dict) -> dict:
        return {"prediction": 0.5, "confidence": 0.9}
```

For remote inference services (like TimesFM), create a `service.py` and Dockerfile in the same directory.

## Chain Loader Plugin

Create `backend/sources/loaders/my_loader.py`:

```python
from backend.core.registry import register_chain

@register_chain("my_loader")
class MyChainLoader:
    def fetch_block(self, rpc_url: str, block_number: int) -> dict:
        ...
    def fetch_transaction(self, tx_hash: str) -> dict:
        ...
```

## Registry API

```python
from backend.core.registry import (
    SOURCES_REGISTRY,     # dict[str, type[AbstractSource]]
    SOURCE_INSTANCES,     # dict[str, AbstractSource] - singletons
    ML_MODELS_REGISTRY,   # dict[str, type[AbstractModel]]
    CHAIN_LOADERS,        # dict[str, type[ChainLoader]]
    get_source,           # -> singleton instance (preserves circuit breaker state)
)
```
