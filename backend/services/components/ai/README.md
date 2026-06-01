# AI Service Components

This directory contains modular components for the AI service, providing cache management, budget tracking, and token management.

## Component Overview

### `cache.py`
Cache management for AI responses with both exact-match and semantic caching.

Key features:
- LRU eviction for exact-match cache
- Trigram similarity for semantic caching
- Configurable TTL and size limits
- Cache statistics tracking

Functions:
- `cache_get()` - Retrieve exact-match cached response
- `cache_set()` - Store response in exact-match cache
- `semantic_cache_search()` - Find semantically similar cached responses
- `get_cache_stats()` - Get cache usage statistics

### `budget.py`
AI token budget management and tracking.

Functions:
- `_deduct_tokens()` - Deduct tokens from daily budget
- `_within_budget()` - Check if operation would exceed budget (non-deducting)
- `get_budget_status()` - Get current budget utilization

## Benefits

- **Modularity**: Clear separation of caching and budget concerns
- **Configurability**: All limits and thresholds are environment-configurable
- **Performance**: Efficient cache algorithms with LRU eviction
- **Observability**: Comprehensive statistics and monitoring
- **Flexibility**: Semantic caching can be enabled/disabled

## Configuration

The components read configuration from environment variables:

- `AI_CACHE_TTL_SECONDS` - Cache entry TTL (default: 3600)
- `AI_CACHE_MAX_ENTRIES` - Maximum exact-match cache entries (default: 1000)
- `AI_CACHE_SEMANTIC_ENABLED` - Enable semantic caching (default: false)
- `AI_CACHE_SEMANTIC_THRESHOLD` - Semantic similarity threshold (default: 0.90)
- `AI_CACHE_MAX_SEMANTIC_ENTRIES` - Maximum semantic cache entries (default: 200)
- `AI_DAILY_TOKEN_BUDGET` - Daily token budget limit (default: 50000)

## Usage

The components are used internally by the AI router service:

```python
from services.components.ai.cache import cache_get, cache_set
from services.components.ai.budget import get_budget_status

# Check cache
cached_response = cache_get(cache_key)
if cached_response:
    return cached_response

# Check budget
budget = get_budget_status()
if not budget["within_budget"]:
    raise Exception("AI budget exceeded")

# Store in cache
cache_set(cache_key, feature, prompt, response)
```