# AI Configuration Guide

This guide explains how to configure and customize the AI features in Helix-Signal.

## Overview

Helix-Signal provides optional AI-powered intelligence features that can enhance your monitoring capabilities. These features include:

- **Risk Explanations**: LLM-generated explanations for risk scores
- **Market Narratives**: Summaries of market conditions and events
- **Insights**: Multi-asset analytical insights
- **Predictive Analytics**: Depeg probability and regime detection

All AI features are disabled by default and can be enabled through the Settings UI.

## AI Mode Configuration

The primary setting that controls AI functionality is `ai_mode`:

- **ai_off** (default): All AI features disabled
- **ai_lite**: Basic AI features with cost-effective providers
- **ai_full**: All AI features with full provider chain

You can change this setting in the Settings UI under the "AI & Intelligence" group.

## Per-Feature Model Overrides

Helix-Signal now supports specifying different AI models for different features. This allows you to:

- Use a lightweight model for simple tasks like summaries
- Use a more powerful model for complex analytical tasks
- Optimize costs by matching model capabilities to task requirements

### Available Model Settings

The following per-feature model settings are available in the Settings UI:

| Setting Key | Feature | Description |
|-------------|---------|-------------|
| `ai_model_risk_explain` | Risk Explanation | Model for generating risk explanations |
| `ai_model_market_narrative` | Market Narrative | Model for market condition summaries |
| `ai_model_insight_summary` | Insights | Model for multi-asset analytical insights |
| `ai_model_predictive` | Predictive Analytics | Model for predictive analytics features |

### Provider-Specific Model Settings

In addition to per-feature overrides, you can configure default models for each AI provider:

| Setting Key | Provider | Description |
|-------------|----------|-------------|
| `groq_model` | Groq | Default model for Groq provider |
| `ollama_cloud_model` | Ollama Cloud | Default model for Ollama Cloud provider |
| `openrouter_free_model` | OpenRouter Free | Default model for OpenRouter free tier |
| `openrouter_model` | OpenRouter Paid | Default model for OpenRouter paid tier |
| `cloudflare_ai_model` | Cloudflare | Default model for Cloudflare AI provider |

## Per-Feature Configuration Settings

Each AI feature can be configured with granular settings for optimal performance:

### Predictive Analytics Settings

| Setting Key | Type | Default | Description |
|-------------|------|---------|-------------|
| `predictive_enable_depeg` | Boolean | true | Enable depeg probability prediction |
| `predictive_enable_regime` | Boolean | true | Enable regime state detection |
| `predictive_depeg_horizons` | String | "1h,6h,24h" | Time horizons for depeg prediction |
| `predictive_confidence_threshold` | Float | 0.7 | Minimum confidence level (0.1-0.99) |

### AI Summary Settings

| Setting Key | Type | Default | Description |
|-------------|------|---------|-------------|
| `ai_summary_max_length` | Integer | 500 | Maximum character length for summaries |
| `ai_summary_detail_level` | String | "medium" | Detail level ("low", "medium", "high") |

### AI Risk Explanation Settings

| Setting Key | Type | Default | Description |
|-------------|------|---------|-------------|
| `ai_explain_max_factors` | Integer | 5 | Maximum risk factors to explain per signal |
| `ai_explain_confidence_min` | Float | 0.6 | Minimum confidence level (0.1-0.99) |

### AI Insights Settings

| Setting Key | Type | Default | Description |
|-------------|------|---------|-------------|
| `ai_insights_max_assets` | Integer | 10 | Maximum assets to analyze |
| `ai_insights_correlation_min` | Float | 0.3 | Minimum correlation coefficient (0.0-1.0) |

## Provider Configuration

Helix-Signal supports multiple AI providers with automatic fallback:

1. **Groq** - Fast inference with Llama models
2. **Ollama Cloud** - Cloud-based Ollama models
3. **OpenRouter** - Access to multiple model providers
4. **Cloudflare Workers AI** - Cloudflare's AI inference platform

### API Keys

To use each provider, you need to configure the corresponding API key in the Settings UI:

| Provider | Setting Key | Environment Variable |
|----------|-------------|---------------------|
| Groq | `secret_groq_api_key` | `GROQ_API_KEY` |
| Ollama Cloud | `secret_ollama_api_key` | `OLLAMA_API_KEY` |
| OpenRouter | `secret_openrouter_api_key` | `OPENROUTER_API_KEY` |
| Cloudflare | `secret_cloudflare_api_token` | `CLOUDFLARE_API_TOKEN` |

## Model Discovery API

Helix-Signal provides API endpoints to discover available models from each provider:

### List Providers
```
GET /api/admin/ai/providers
```

Returns information about all available AI providers.

### List Models for Provider
```
GET /api/admin/ai/providers/{provider_id}/models
```

Returns available models for a specific provider.

## Best Practices

### Cost Management

1. Use `ai_lite` mode for cost-conscious deployments
2. Configure appropriate token budgets via `ai_daily_token_budget`
3. Use per-feature model overrides to match model capability to task requirements
4. Monitor usage via the AI budget dashboard

### Performance Optimization

1. Configure appropriate cache TTL settings for your use case
2. Enable semantic caching for frequently repeated prompts
3. Use provider priority settings to optimize for speed vs. cost
4. Monitor provider performance via the provider stats dashboard

### Security

1. Always use the Settings UI for API key management rather than environment variables
2. Enable `ai_require_token` to add additional authentication for AI endpoints
3. Monitor AI usage via the settings audit log
4. Regularly review and rotate API keys

## Troubleshooting

### Common Issues

1. **AI features not working**: Check that `ai_mode` is not set to `ai_off`
2. **Empty model dropdowns**: Verify API keys are configured correctly
3. **Rate limiting**: Check provider-specific rate limits and configure appropriate budgets
4. **High costs**: Review token usage and adjust feature settings or model choices

### Logs and Monitoring

Check the application logs for AI-related messages:
- Provider initialization and configuration
- Model loading and inference
- Rate limit and budget tracking
- Error conditions and fallback behavior

The AI budget dashboard provides real-time monitoring of token usage and remaining budget.