"""AI model discovery endpoints."""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.admin_auth import require_admin_token
from core.limiter import limiter
from database import AiProvider, get_db
from services.llm_client import list_provider_models, seed_default_providers

router = APIRouter()


class ModelInfo(BaseModel):
    id: str
    name: str
    description: str | None = None
    capabilities: list[str] | None = None
    max_tokens: int | None = None
    cost_per_million_tokens: float | None = None


class ProviderInfo(BaseModel):
    id: str
    name: str
    description: str | None = None
    models: list[ModelInfo] = []


_PROVIDER_ALIASES: dict[str, str] = {
    "ollama_cloud": "ollama",
}


@router.get("/ai/providers")
@limiter.limit("30/minute")
def list_providers(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> list[dict[str, Any]]:
    """List registered AI providers (registry + built-in metadata)."""
    seed_default_providers(db)
    rows = db.execute(select(AiProvider).order_by(AiProvider.id.asc())).scalars().all()
    if rows:
        return [{"id": r.id, "name": r.label, "description": r.base_url, "enabled": r.enabled} for r in rows]
    return [
        {"id": "ollama_cloud", "name": "Ollama Cloud", "description": "Cloud-hosted Ollama models"},
        {"id": "openrouter", "name": "OpenRouter", "description": "Access to multiple AI models via OpenRouter"},
    ]


@router.get("/ai/providers/{provider_id}/models")
@limiter.limit("30/minute")
def list_models(
    request: Request,
    provider_id: str,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict[str, Any]:
    """List models for a provider.

    Response shape distinguishes empty catalog from errors:
    ``{"models": [...], "error": null | "no_api_key" | "provider_http_error" | ...}``
    """
    resolved_id = _PROVIDER_ALIASES.get(provider_id, provider_id)
    seed_default_providers(db)

    try:
        if db.get(AiProvider, resolved_id):
            models, err = list_provider_models(db, resolved_id)
            return {"models": models, "error": err, "provider": resolved_id}
        if resolved_id in ("ollama", "ollama_cloud"):
            models, err = _get_ollama_models(db)
            return {"models": models, "error": err, "provider": "ollama_cloud"}
        if resolved_id == "openrouter":
            models, err = _get_openrouter_models(db)
            return {"models": models, "error": err, "provider": "openrouter"}
        raise HTTPException(status_code=404, detail=f"Provider {provider_id} not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch models: {str(e)}")


def _resolve_api_key_from_settings(db: Session | None, secret_key: str, env_key: str) -> str:
    from providers.settings import get_secret
    return str(get_secret(secret_key, db) or os.getenv(env_key, "")).strip()


def _get_ollama_models(db: Session | None = None) -> tuple[list[dict[str, Any]], str | None]:
    api_key = _resolve_api_key_from_settings(db, "secret_ollama_api_key", "OLLAMA_API_KEY")
    if not api_key:
        return [], "no_api_key"

    try:
        with httpx.Client() as client:
            response = client.get(
                "https://ollama.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )
            if response.status_code >= 400:
                return [], f"provider_http_{response.status_code}"
            data = response.json()
            models = []
            for model in data.get("data", []) or []:
                mid = model.get("id", "")
                if not mid:
                    continue
                models.append({
                    "id": mid,
                    "name": mid,
                    "description": model.get("description", ""),
                })
            return models, None
    except Exception as exc:
        return [], f"provider_error:{type(exc).__name__}"


def _get_openrouter_models(db: Session | None = None) -> tuple[list[dict[str, Any]], str | None]:
    api_key = _resolve_api_key_from_settings(db, "secret_openrouter_api_key", "OPENROUTER_API_KEY")
    if not api_key:
        return [], "no_api_key"

    try:
        with httpx.Client() as client:
            response = client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0,
            )
            if response.status_code >= 400:
                return [], f"provider_http_{response.status_code}"
            data = response.json()
            models = []
            for model in data.get("data", []) or []:
                mid = model.get("id", "")
                if not mid:
                    continue
                models.append({
                    "id": mid,
                    "name": mid,
                    "description": model.get("description", ""),
                    "max_tokens": model.get("max_context_length", None),
                })
            return models, None
    except Exception as exc:
        return [], f"provider_error:{type(exc).__name__}"
