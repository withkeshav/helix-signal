"""AI model discovery endpoints."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.admin_auth import require_admin_token
from core.limiter import limiter
from database import get_db

router = APIRouter()


class ModelInfo(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    capabilities: Optional[List[str]] = None
    max_tokens: Optional[int] = None
    cost_per_million_tokens: Optional[float] = None


class ProviderInfo(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    models: List[ModelInfo] = []


_PROVIDER_ALIASES: dict[str, str] = {
    "ollama_cloud": "ollama",
}


@router.get("/ai/providers")
@limiter.limit("30/minute")
def list_providers(
    request: Request,
    _auth=Depends(require_admin_token),
) -> List[Dict[str, Any]]:
    """List supported AI providers (Ollama Cloud + OpenRouter only)."""
    return [
        {
            "id": "ollama_cloud",
            "name": "Ollama Cloud",
            "description": "Cloud-hosted Ollama models",
        },
        {
            "id": "openrouter",
            "name": "OpenRouter",
            "description": "Access to multiple AI models via OpenRouter",
        },
    ]


@router.get("/ai/providers/{provider_id}/models")
@limiter.limit("30/minute")
def list_models(
    request: Request,
    provider_id: str,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> List[Dict[str, Any]]:
    """List models available from a specific provider."""
    resolved_id = _PROVIDER_ALIASES.get(provider_id, provider_id)

    try:
        if resolved_id in ("ollama", "ollama_cloud"):
            return _get_ollama_models(db)
        if resolved_id == "openrouter":
            return _get_openrouter_models(db)
        raise HTTPException(status_code=404, detail=f"Provider {provider_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch models: {str(e)}")


def _resolve_api_key_from_settings(db: Session | None, secret_key: str, env_key: str) -> str:
    from providers.settings import get_secret
    return str(get_secret(secret_key, db) or os.getenv(env_key, "")).strip()


def _get_ollama_models(db: Session | None = None) -> List[Dict[str, Any]]:
    api_key = _resolve_api_key_from_settings(db, "secret_ollama_api_key", "OLLAMA_API_KEY")
    if not api_key:
        return []

    try:
        with httpx.Client() as client:
            response = client.get(
                "https://ollama.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            models = []
            for model in data.get("data", []):
                models.append({
                    "id": model.get("id", ""),
                    "name": model.get("id", ""),
                    "description": model.get("description", ""),
                })
            return models
    except Exception:
        return []


def _get_openrouter_models(db: Session | None = None) -> List[Dict[str, Any]]:
    api_key = _resolve_api_key_from_settings(db, "secret_openrouter_api_key", "OPENROUTER_API_KEY")
    if not api_key:
        return []

    try:
        with httpx.Client() as client:
            response = client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            models = []
            for model in data.get("data", []):
                models.append({
                    "id": model.get("id", ""),
                    "name": model.get("id", ""),
                    "description": model.get("description", ""),
                    "max_tokens": model.get("max_context_length", None),
                })
            return models
    except Exception:
        return []
