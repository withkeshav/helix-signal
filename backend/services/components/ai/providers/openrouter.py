"""OpenRouter provider implementation."""

import os
from typing import Any, Dict, Optional

import httpx


def openrouter_lite(
    prompt: str, max_tokens: int, model: Optional[str] = None, **kwargs
) -> Optional[Dict[str, Any]]:
    """Call OpenRouter Lite API."""
    api_key = kwargs.get("_resolved_api_key", "").strip()
    if not api_key:
        return None
    model = model or os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    return {"provider": "openrouter", "model": model, "text": text, "tokens": usage.get("total_tokens", 0)}