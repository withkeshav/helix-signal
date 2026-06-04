"""Ollama Cloud provider implementation."""

import os
from typing import Any, Dict, Optional

import httpx


def ollama_cloud(
    prompt: str, max_tokens: int, system: Optional[str] = None, model: Optional[str] = None, **kwargs
) -> Optional[Dict[str, Any]]:
    """Call Ollama Cloud API."""
    api_key = kwargs.get("_resolved_api_key", "").strip()
    if not api_key:
        return None
    model = model or os.getenv("OLLAMA_CLOUD_MODEL", "ministral-3:8b-cloud")
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            "https://ollama.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": messages, "max_tokens": max_tokens},
        )
        resp.raise_for_status()
        data = resp.json()
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    return {"provider": "ollama_cloud", "model": model, "text": text, "tokens": usage.get("total_tokens", 0)}