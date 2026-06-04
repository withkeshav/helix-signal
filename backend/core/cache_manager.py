"""Unified caching layer — Redis with automatic fallback, health checks, and reconnection logic."""

import hashlib
import json
import os
import time
from functools import wraps
from typing import Any, Callable, Optional, Dict
from datetime import datetime


class CacheManager:
    def __init__(self):
        self._redis = None
        self._redis_url = None
        self._last_health_check = 0
        self._health_check_interval = 30  # seconds
        self._connection_errors = 0
        self._initialized = False
        self._init_redis()

    def _init_redis(self):
        """Initialize Redis connection with error handling."""
        self._redis_url = os.getenv("REDIS_URL", "")
        if self._redis_url:
            try:
                import redis
                self._redis = redis.from_url(self._redis_url)
                self._initialized = True
                self._connection_errors = 0
            except Exception as e:
                self._redis = None
                self._initialized = False
                self._connection_errors += 1

    def _reconnect(self) -> bool:
        """Attempt to reconnect to Redis."""
        try:
            import redis
            self._redis = redis.from_url(self._redis_url)
            self._connection_errors = 0
            return True
        except Exception as e:
            self._redis = None
            self._connection_errors += 1
            return False

    def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check of Redis connection."""
        now = time.time()
        
        # Don't check too frequently
        if now - self._last_health_check < self._health_check_interval:
            return {
                "status": "cached",
                "available": self._redis is not None,
                "initialized": self._initialized,
                "connection_errors": self._connection_errors,
                "last_check": datetime.fromtimestamp(self._last_health_check).isoformat() if self._last_health_check else None
            }
        
        self._last_health_check = now
        status = "unknown"
        
        if not self._redis_url:
            status = "no_config"
        elif self._redis is None:
            status = "disconnected"
            # Try to reconnect
            if self._reconnect():
                status = "reconnected"
            else:
                status = "unreachable"
        else:
            try:
                # Ping Redis to check connectivity
                self._redis.ping()
                status = "healthy"
            except Exception as e:
                status = "unhealthy"
                # Try to reconnect on failure
                if self._reconnect():
                    status = "reconnected_after_failure"
                else:
                    self._redis = None
                    status = "connection_lost"
        
        return {
            "status": status,
            "available": self._redis is not None,
            "initialized": self._initialized,
            "connection_errors": self._connection_errors,
            "timestamp": datetime.now().isoformat()
        }

    @property
    def available(self) -> bool:
        """Check if Redis is available with health check."""
        if not self._initialized:
            return False
        if self._redis is None:
            # Try to reconnect if disconnected
            return self._reconnect()
        return True

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache with error handling."""
        if not self.available:
            return None
        try:
            val = self._redis.get(key)
            return json.loads(val) if val else None
        except Exception:
            # Connection might be broken, try to reconnect
            if self._reconnect():
                try:
                    val = self._redis.get(key)
                    return json.loads(val) if val else None
                except Exception:
                    pass
            return None

    def set(self, key: str, value: Any, ttl: int = 300):
        """Set value in cache with error handling."""
        if not self.available:
            return
        try:
            self._redis.setex(key, ttl, json.dumps(value))
        except Exception:
            # Connection might be broken, try to reconnect
            if self._reconnect():
                try:
                    self._redis.setex(key, ttl, json.dumps(value))
                except Exception:
                    pass

    def delete(self, key: str):
        """Delete key from cache with error handling."""
        if not self.available:
            return
        try:
            self._redis.delete(key)
        except Exception:
            # Connection might be broken, try to reconnect
            if self._reconnect():
                try:
                    self._redis.delete(key)
                except Exception:
                    pass

    def delete_pattern(self, pattern: str):
        """Delete keys matching pattern with error handling."""
        if not self.available:
            return
        try:
            cursor = 0
            while True:
                cursor, keys = self._redis.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    self._redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception:
            # Connection might be broken, try to reconnect
            if self._reconnect():
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
        """Decorator: cache function results in Redis with automatic fallback."""
        def decorator(func: Callable):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Generate cache key
                key = f"{func.__name__}:{hashlib.sha256(f'{args}:{kwargs}'.encode()).hexdigest()}"
                
                # Try to get from cache
                cached = self.get(key)
                if cached is not None:
                    cached["_cache"] = "hit"
                    return cached
                
                # Execute function and cache result
                try:
                    result = func(*args, **kwargs)
                    self.set(key, result, ttl)
                    if isinstance(result, dict):
                        result["_cache"] = "miss"
                    return result
                except Exception as e:
                    # If function fails, try cache as fallback if available
                    cached_fallback = self.get(key)
                    if cached_fallback is not None:
                        cached_fallback["_cache"] = "fallback"
                        return cached_fallback
                    # Re-raise the exception if no fallback available
                    raise e
            return wrapper
        return decorator

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "available": self.available,
            "initialized": self._initialized,
            "connection_errors": self._connection_errors,
            "last_health_check": datetime.fromtimestamp(self._last_health_check).isoformat() if self._last_health_check else None
        }


# Global cache instance
cache = CacheManager()
