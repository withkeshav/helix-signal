"""High-level cache service wrapper around redis-py with enhanced functionality."""

from __future__ import annotations

from typing import Any, Optional, Dict
from datetime import datetime

from core.cache_manager import cache


class CacheService:
    """Enhanced cache service with monitoring, metrics, and robust error handling."""
    
    def __init__(self):
        self._hit_count = 0
        self._miss_count = 0
        self._error_count = 0
        self._fallback_count = 0

    def get(self, key: str, default: Any = None) -> Any:
        """Get value from cache with default fallback."""
        try:
            result = cache.get(key)
            if result is not None:
                self._hit_count += 1
                return result
            self._miss_count += 1
            return default
        except Exception as e:
            self._error_count += 1
            return default

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Set value in cache with error handling."""
        try:
            cache.set(key, value, ttl)
            return True
        except Exception as e:
            self._error_count += 1
            return False

    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        try:
            cache.delete(key)
            return True
        except Exception as e:
            self._error_count += 1
            return False

    def delete_pattern(self, pattern: str) -> bool:
        """Delete keys matching pattern."""
        try:
            cache.delete_pattern(pattern)
            return True
        except Exception as e:
            self._error_count += 1
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            if not cache.available:
                return False
            return cache._redis.exists(key) > 0
        except Exception:
            return False

    def increment(self, key: str, amount: int = 1, ttl: int = 3600) -> Optional[int]:
        """Increment a counter in cache."""
        try:
            if not cache.available:
                return None
            value = cache._redis.incrby(key, amount)
            if ttl:
                cache._redis.expire(key, ttl)
            return value
        except Exception as e:
            self._error_count += 1
            return None

    def get_or_set(self, key: str, factory_func, ttl: int = 300) -> Any:
        """Get value from cache or compute it using factory function."""
        try:
            result = self.get(key)
            if result is not None:
                return result
            
            # Compute value
            result = factory_func()
            self.set(key, result, ttl)
            return result
        except Exception as e:
            self._error_count += 1
            # Try to return cached value as fallback
            fallback = self.get(key)
            if fallback is not None:
                self._fallback_count += 1
                return fallback
            raise e

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        cache_stats = cache.stats()
        return {
            "cache_manager": cache_stats,
            "service_stats": {
                "hits": self._hit_count,
                "misses": self._miss_count,
                "errors": self._error_count,
                "fallbacks": self._fallback_count,
                "hit_rate": self._hit_count / max(1, self._hit_count + self._miss_count),
            },
            "timestamp": datetime.now().isoformat()
        }

    def clear_stats(self):
        """Reset statistics counters."""
        self._hit_count = 0
        self._miss_count = 0
        self._error_count = 0
        self._fallback_count = 0

    def health_check(self) -> Dict[str, Any]:
        """Perform health check on cache service."""
        return cache.health_check()

    def invalidate_dashboard(self, asset: str | None = None) -> bool:
        """Invalidate dashboard cache for specific asset or all."""
        try:
            pattern = f"helix:dashboard:{(asset or '*').upper()}"
            return self.delete_pattern(pattern)
        except Exception:
            return False

    def invalidate_pattern(self, pattern: str) -> bool:
        """Invalidate all keys matching pattern."""
        return self.delete_pattern(pattern)


# Global cache service instance
cache_service = CacheService()
