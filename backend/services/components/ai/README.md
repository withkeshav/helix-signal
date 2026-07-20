# AI Service Components

Modular helpers used by `services/ai_router.py` and `services/llm_client.py`.

## Component Overview

### `cache.py`
Cache management for AI responses with exact-match and optional semantic caching.

- LRU eviction, configurable TTL/size limits
- `cache_get()` / `cache_set()` / `semantic_cache_search()` / `get_cache_stats()`

Settings keys: `ai_cache_semantic_enabled`, `ai_cache_ttl_seconds`, `ai_cache_max_entries`, etc. (Control Room Advanced allowlist).

### `providers/`
Legacy OpenRouter helper; production path is **`llm_client.chat_completion()`** against rows in `ai_providers`.

## Configuration

Provider credentials live in the **`ai_providers`** table (encrypted). Per-feature routing uses `ai_model_{feature}` as `provider_id:model_id` with 3-tier fallback documented in `docs/guides/ai-configuration.md`.

Usage tracking: `services/ai_usage.py` (`AiUsage` table) - incremented from `enrich_with_ai` after successful completions.

## Usage

```python
from services.llm_client import chat_completion

result = chat_completion(db, provider_id="ollama_cloud", model="ministral-3:8b-cloud", messages=[...])
```

Or the higher-level router:

```python
from services.ai_router import enrich_with_ai

out = enrich_with_ai(feature="risk_explain", context={...}, db=db)
```
