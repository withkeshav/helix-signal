"""Cloudflare AI provider implementation."""

import os
from typing import Any, Dict, Optional

import httpx


def cloudflare_ai(
    prompt: str, max_tokens: int, system: Optional[str] = None, model: Optional[str] = None, **kwargs
) -> Optional[Dict[str, Any]]:
    """Call Cloudflare AI API."""
    api_key = kwargs.get("_resolved_api_key") or os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    account_id = kwargs.get("_resolved_account_id") or os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if not api_key or not account_id:
        return None
    model = model or os.getenv("CLOUDFLARE_AI_MODEL", "@cf/meta/llama-3.1-8b-instruct")
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1/chat/completions"
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": messages, "max_tokens": max_tokens},
        )
        resp.raise_for_status()
        data = resp.json()
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    return {"provider": "cloudflare", "model": model, "text": text, "tokens": usage.get("total_tokens", 0)}