"""Circuit breaker pattern for external API calls.
Prevents cascading failures when a data source goes down."""

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 3
    recovery_timeout: int = 60
    half_open_max_requests: int = 1

    def __post_init__(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.half_open_requests = 0
        self._lock = threading.Lock()

    def call(self, fn: Callable, fallback: Optional[Callable] = None, *args, **kwargs) -> Any:
        with self._lock:
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_requests = 0
                else:
                    return fallback() if fallback else None

            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_requests >= self.half_open_max_requests:
                    return fallback() if fallback else None
                self.half_open_requests += 1

        try:
            result = fn(*args, **kwargs)
            with self._lock:
                if self.state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
            return result
        except Exception as e:
            with self._lock:
                self.failure_count += 1
                self.last_failure_time = time.time()
                if self.failure_count >= self.failure_threshold:
                    self.state = CircuitState.OPEN
            return fallback() if fallback else None

    def to_dict(self) -> dict:
        return {
            "source": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
        }
