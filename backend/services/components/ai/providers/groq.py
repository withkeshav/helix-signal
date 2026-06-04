"""Groq provider implementation."""

import os
from typing import Any, Dict, Optional

import httpx


def groq(
    prompt: str, max_tokens: int, model: Optional[str] = None, **kwargs
) -> Optional[Dict[str, Any]]:
    """Call Groq API."""
    api_key = kwargs.get("_resolved_api_key", "").strip()
    if not api_key:
        return None
    model = model or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            "https://api.groq.com/openai/v1/chat/completions",
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
    return {"provider": "groq", "model": model, "text": text, "tokens": usage.get("total_tokens", 0)}