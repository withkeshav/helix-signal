# AI Configuration Guide

This guide is the **single source of truth** for AI configuration in Helix-Signal. It reflects the simplified model introduced after v4.0.5: only two AI providers are supported, every feature resolves its own `provider:model_id`, and there is **no token budget enforcement** — only usage tracking via the `AiUsage` table.

## Overview

AI features are gated by the `ai_mode` setting:

- **ai_off** (default): All AI features disabled.
- **ai_lite**: Basic features via the primary provider.
- **ai_full**: All features via the primary provider, with fallback to the secondary provider on failure.

Supported providers:

1. **Ollama Cloud** — default for cost-conscious / open-source deployments.
2. **OpenRouter** — fallback and powerful-model option.

No other providers are supported. Legacy settings for Groq, Cloudflare, provider priority chains, and token budgets have been removed.

## AI Mode Configuration

Set `ai_mode` in the Settings UI under the **AI & Intelligence** group, or via the settings API.

| Mode | Effect |
|------|--------|
| `ai_off` | Every AI route returns a clear unavailable response. |
| `ai_lite` | Enables `risk_explain`, `market_narrative`, and `insight_summary`. |
| `ai_full` | Enables all AI features, including predictive analytics. |

## Per-Feature Model Settings

Each AI feature resolves its own model in the format `provider:model_id`:

| Setting Key | Feature | Default | Example |
|-------------|---------|---------|---------|
| `ai_model_risk_explain` | Risk explanation | `ollama_cloud:ministral-3:8b-cloud` | `openrouter:openai/gpt-4o-mini` |
| `ai_model_market_narrative` | Market narrative | `ollama_cloud:ministral-3:8b-cloud` | `openrouter:openai/gpt-4o-mini` |
| `ai_model_insight_summary` | Multi-asset insight | `ollama_cloud:ministral-3:8b-cloud` | `openrouter:openai/gpt-4o-mini` |
| `ai_model_predictive` | Predictive analytics | `ollama_cloud:ministral-3:8b-cloud` | `openrouter:openai/gpt-4o-mini` |

### Setting the model string

Use exactly `provider:model_id`:

```text
ollama_cloud:ministral-3:8b-cloud
openrouter:openai/gpt-4o-mini
```

The application code never hardcodes a model ID. It reads the setting, splits on `:`, resolves the provider API key, and calls the model. If a setting is missing or malformed, the feature returns `{"available": False, "reason": "model_not_configured"}` and logs an error.

### Fallback provider

Set `ai_fallback_provider` to `ollama_cloud` or `openrouter`. When the primary provider for a feature fails, the system retries using the fallback provider's configured model. If no fallback is set, the call stops after the primary failure.

| Setting Key | Purpose | Default |
|-------------|---------|---------|
| `ai_fallback_provider` | Provider to use on primary failure | `openrouter` |
| `ai_fallback_model` | Model ID to use on fallback | `openai/gpt-4o-mini` |

## Provider API Keys

Configure keys in the Settings UI under **API Keys**. The runtime reads DB settings before environment variables.

| Provider | Setting Key | Environment Variable (fallback only) |
|----------|-------------|--------------------------------------|
| Ollama Cloud | `secret_ollama_api_key` | `OLLAMA_API_KEY` |
| OpenRouter | `secret_openrouter_api_key` | `OPENROUTER_API_KEY` |

The application never falls back to a hardcoded key or model.

## Feature Toggles

Each feature can be enabled/disabled independently:

| Setting Key | Default | Effect |
|-------------|---------|--------|
| `feature_ai_risk_explain` | `true` | Risk explanation panel on Signal tab |
| `feature_ai_market_narrative` | `true` | Market narrative on Market tab |
| `feature_ai_insight_summary` | `true` | Asset insight summary |
| `feature_ai_predictive` | `true` | Predictive analytics (regime / depeg) |

These toggles are evaluated only when `ai_mode` is `ai_lite` or `ai_full`.

## Cache Settings

Semantic caching is controlled by:

| Setting Key | Default | Description |
|-------------|---------|-------------|
| `ai_cache_semantic_enabled` | `false` | Enable semantic prompt caching |
| `ai_cache_semantic_threshold` | `0.92` | Cosine-similarity threshold for cache hits |
| `ai_cache_hit_ttl_minutes` | `30` | TTL for successful cache entries |
| `ai_cache_error_ttl_minutes` | `5` | TTL for error cache entries |

If the DB settings read fails, the cache falls back to conservative defaults and logs a warning.

## Cost and Usage Tracking

Token budgets have been removed. There is **no enforcement** of daily or per-feature spend limits.

Cost awareness is maintained via:

- The `AiUsage` table records every provider call: feature, provider, model, prompt tokens, completion tokens, and cost.
- `/api/ai/usage` exposes recent usage for monitoring.
- Operators review usage weekly.

If usage tracking insertion fails, the AI call still completes, but an error is logged.

## Logging Format

Set `LOG_FORMAT=json` in `.env` to emit structured logs. This is required for weekly error reviews.

With JSON logging, every exception should be logged with `exc_info=True` so the full traceback is captured. The application no longer silently swallows errors with `except: pass`.

## Model Discovery

The model-discovery API lists known providers and, when an API key is present, fetches available models from OpenRouter:

```bash
GET /api/admin/ai/providers
GET /api/admin/ai/providers/openrouter/models
GET /api/admin/ai/providers/ollama_cloud/models
```

The Ollama Cloud provider returns a static list; OpenRouter queries the OpenRouter API.

## Best Practices

1. **Start with `ai_lite`.** Enable Ollama Cloud with `ministral-3:8b-cloud` for low-cost explanations.
2. **Use OpenRouter as fallback.** Set `ai_fallback_provider=openrouter` and a reliable model such as `openai/gpt-4o-mini`.
3. **Configure per-feature models.** Use a smaller model for summaries and a larger model for predictive / regime tasks.
4. **Set `LOG_FORMAT=json`.** This is the only supported format for production error triage.
5. **Review `/api/ai/usage` weekly.** There is no automatic budget cutoff, so operators must monitor spend manually.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| AI panel shows "unavailable" | `ai_mode` is `ai_off` | Set `ai_mode` to `ai_lite` or `ai_full` |
| AI panel shows "model not configured" | Feature model setting missing or malformed | Set `ai_model_<feature>` to `provider:model_id` |
| Empty model dropdowns | API keys not configured | Add `secret_ollama_api_key` or `secret_openrouter_api_key` |
| High latency | Primary provider slow or rate-limited | Enable fallback provider or switch the feature model |
| No cost controls | Token budgets removed | Monitor `/api/ai/usage` weekly and adjust model choices |

## Migration from pre-v4.0.5 settings

If you previously used settings such as:

- `groq_model`, `cloudflare_ai_model`
- `ai_provider_priority`
- `ai_daily_token_budget`, `ai_monthly_token_budget`
- `ai_token_budget_enabled`

Delete them and replace with the per-feature `ai_model_<feature>` settings above. Provider-specific model settings are no longer used.

## Canonical References

- Runtime behavior: `backend/services/ai_router.py`
- Provider implementations: `backend/services/components/ai/providers/`
- Settings defaults: `backend/providers/settings_registry.py`
- This guide: `docs/guides/ai-configuration.md`
