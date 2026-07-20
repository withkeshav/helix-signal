# AI Configuration Guide

This guide is the **single source of truth** for AI configuration in Helix-Signal.

## Overview

AI features are gated by `ai_mode`:

- **ai_off** (default): All AI disabled; UI shows deterministic STATUS/drivers.
- **ai_lite** / **ai_full**: Features run through the provider registry with 3-tier fallback.

## Provider registry

Named OpenAI-compatible providers live in the `ai_providers` table (Control Room → AI, or `/api/v1/ai-providers`):

| Field | Meaning |
|-------|---------|
| `id` | Stable id used in settings (e.g. `ollama_cloud`, `openrouter`, or custom) |
| `base_url` | OpenAI-compatible root (client calls `{base_url}/chat/completions`) |
| `api_key` | Encrypted; never returned in list responses |
| `enabled` | Soft disable |

On first use, Helix **seeds** `ollama_cloud` and `openrouter` from existing secrets/env if missing.

Model ids are **free text** (no maintained catalog required). Feature settings use `provider_id:model_id`, e.g. `ollama_cloud:ministral-3:8b-cloud`.

## 3-tier fallback

For each task (e.g. `risk_explain`):

1. **Primary** - `ai_model_{feature}` → `provider_id:model_id`
2. **Task fallback** - `ai_fallback_provider` + `ai_fallback_model` (legacy)
3. **Global default** - `ai_default_fallback_provider` + `ai_default_fallback_model_id`

Each attempt logs the tier used. If all fail, the response includes a clear `all_providers_failed` reason. Usage is recorded in `AiUsage`.

Admin: `GET /api/settings/ai-health` for last test status and today's usage.

## Web search (optional, scheduled cache)

AI can include a **cached** `WEB_CONTEXT` block from external search. This is **not** live search on every AI click.

| Rule | Behavior |
|------|----------|
| **Opt-in** | Add **Tavily** and/or **Exa** API key in Control Room secrets |
| **Also required** | `ai_mode` is `ai_lite` or `ai_full` |
| **Chain** | Tavily → Exa → Ollama `web_search` |
| **Cadence** | Scheduler ~12h; manual `POST /api/settings/web-search/run` |
| **Status** | `GET /api/settings/web-search-status` (admin) |
| **Alerts** | Consecutive failures / stale cache emit SignalEvents into `alert_router` |

## Control Room

- AI & Models: mode, per-feature provider+model text, fallbacks, provider CRUD/test
- Overview: AI health + web search cards

See also `docs/api.md` and `docs/guides/alert-routing.md`.
