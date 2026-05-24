"""Unified caching layer — Redis with automatic fallback when unavailable."""

import hashlib
import json
import os
from functools import wraps
from typing import Any, Callable, Optional


class CacheManager:
    def __init__(self):
        self._redis = None
        self._init_redis()

    def _init_redis(self):
        redis_url = os.getenv("REDIS_URL", "")
        if redis_url:
            try:
                import redis
                self._redis = redis.from_url(redis_url)
            except Exception:
                self._redis = None

    @property
    def available(self) -> bool:
        return self._redis is not None

    def get(self, key: str) -> Optional[Any]:
        if self._redis:
            try:
                val = self._redis.get(key)
                return json.loads(val) if val else None
            except Exception:
                return None
        return None

    def set(self, key: str, value: Any, ttl: int = 300):
        if self._redis:
            try:
                self._redis.setex(key, ttl, json.dumps(value))
            except Exception:
                pass

    def delete(self, key: str):
        if self._redis:
            try:
                self._redis.delete(key)
            except Exception:
                pass

    def delete_pattern(self, pattern: str):
        if self._redis:
            try:
                cursor = 0
                while True:
                    cursor, keys = self._redis.scan(cursor=cursor, match=pattern, count=100)
                    if keys:
                        self._redis.delete(*keys)
                    if cursor == 0:
                        break
            except Exception:
                pass

    def cached(self, ttl: int = 300):
        """Decorator: cache function results in Redis."""
        def decorator(func: Callable):
            @wraps(func)
            def wrapper(*args, **kwargs):
                key = f"{func.__name__}:{hashlib.sha256(f'{args}:{kwargs}'.encode()).hexdigest()}"
                cached = self.get(key)
                if cached is not None:
                    return cached
                result = func(*args, **kwargs)
                self.set(key, result, ttl)
                return result
            return wrapper
        return decorator


cache = CacheManager()
