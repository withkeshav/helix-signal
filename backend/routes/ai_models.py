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
    """Model information structure."""
    id: str
    name: str
    description: Optional[str] = None
    capabilities: Optional[List[str]] = None
    max_tokens: Optional[int] = None
    cost_per_million_tokens: Optional[float] = None


class ProviderInfo(BaseModel):
    """Provider information structure."""
    id: str
    name: str
    description: Optional[str] = None
    models: List[ModelInfo] = []


_PROVIDER_ALIASES: dict[str, str] = {
    "ollama_cloud": "ollama",
    "openrouter_free": "openrouter",
    "openrouter_paid": "openrouter",
}


@router.get("/ai/providers")
@limiter.limit("30/minute")
def list_providers(
    request: Request,
    _auth=Depends(require_admin_token),
) -> List[Dict[str, Any]]:
    """List all available AI providers."""
    providers = [
        {
            "id": "ollama",
            "name": "Ollama",
            "description": "Local and cloud AI models"
        },
        {
            "id": "ollama_cloud",
            "name": "Ollama Cloud",
            "description": "Cloud-hosted Ollama models"
        },
        {
            "id": "groq",
            "name": "Groq",
            "description": "Fast inference with Llama models"
        },
        {
            "id": "openrouter",
            "name": "OpenRouter",
            "description": "Access to multiple AI models"
        },
        {
            "id": "openrouter_free",
            "name": "OpenRouter Free",
            "description": "OpenRouter free-tier models"
        },
        {
            "id": "openrouter_paid",
            "name": "OpenRouter Paid",
            "description": "OpenRouter paid-tier models"
        },
        {
            "id": "cloudflare",
            "name": "Cloudflare Workers AI",
            "description": "Cloudflare's AI inference platform"
        }
    ]
    return providers


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
        if resolved_id == "ollama":
            return _get_ollama_models(db)
        elif resolved_id == "groq":
            return _get_groq_models(db)
        elif resolved_id == "openrouter":
            return _get_openrouter_models(db)
        elif resolved_id == "cloudflare":
            return _get_cloudflare_models(db)
        else:
            raise HTTPException(status_code=404, detail=f"Provider {provider_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch models: {str(e)}")


def _resolve_api_key_from_settings(db: Session | None, secret_key: str, env_key: str) -> str:
    from providers.settings import get_setting
    return str(get_setting(secret_key, db) or os.getenv(env_key, "")).strip()


def _get_ollama_models(db: Session | None = None) -> List[Dict[str, Any]]:
    """Get models from Ollama."""
    api_key = _resolve_api_key_from_settings(db, "secret_ollama_api_key", "OLLAMA_API_KEY")
    if not api_key:
        # Fallback to local Ollama
        try:
            with httpx.Client() as client:
                response = client.get("http://localhost:11434/api/tags", timeout=10.0)
                response.raise_for_status()
                data = response.json()
                models = []
                for model in data.get("models", []):
                    models.append({
                        "id": model.get("name", ""),
                        "name": model.get("name", ""),
                        "description": "Ollama local model"
                    })
                return models
        except Exception:
            return []

    # Use Ollama Cloud API
    try:
        with httpx.Client() as client:
            response = client.get(
                "https://ollama.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            models = []
            for model in data.get("data", []):
                models.append({
                    "id": model.get("id", ""),
                    "name": model.get("id", ""),
                    "description": model.get("description", "")
                })
            return models
    except Exception:
        return []


def _get_groq_models(db: Session | None = None) -> List[Dict[str, Any]]:
    """Get models from Groq."""
    api_key = _resolve_api_key_from_settings(db, "secret_groq_api_key", "GROQ_API_KEY")
    if not api_key:
        return []

    try:
        with httpx.Client() as client:
            response = client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            models = []
            for model in data.get("data", []):
                models.append({
                    "id": model.get("id", ""),
                    "name": model.get("id", ""),
                    "description": model.get("description", ""),
                    "max_tokens": model.get("context_window", {}).get("max", None)
                })
            return models
    except Exception:
        return []


def _get_openrouter_models(db: Session | None = None) -> List[Dict[str, Any]]:
    """Get models from OpenRouter."""
    api_key = _resolve_api_key_from_settings(db, "secret_openrouter_api_key", "OPENROUTER_API_KEY")
    if not api_key:
        return []

    try:
        with httpx.Client() as client:
            response = client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            models = []
            for model in data.get("data", []):
                models.append({
                    "id": model.get("id", ""),
                    "name": model.get("id", ""),
                    "description": model.get("description", ""),
                    "max_tokens": model.get("max_context_length", None)
                })
            return models
    except Exception:
        return []


def _get_cloudflare_models(db: Session | None = None) -> List[Dict[str, Any]]:
    """Get models from Cloudflare."""
    from providers.settings import get_setting
    api_token = _resolve_api_key_from_settings(db, "secret_cloudflare_api_token", "CLOUDFLARE_API_TOKEN")
    account_id = str(get_setting("cloudflare_account_id", db) or os.getenv("CLOUDFLARE_ACCOUNT_ID", "")).strip()

    if not api_token or not account_id:
        return []

    try:
        with httpx.Client() as client:
            response = client.get(
                f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/models/search",
                headers={
                    "Authorization": f"Bearer {api_token}",
                    "Content-Type": "application/json"
                },
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            models = []
            for model in data.get("result", []):
                models.append({
                    "id": model.get("name", ""),
                    "name": model.get("name", ""),
                    "description": model.get("description", "")
                })
            return models
    except Exception:
        return []
