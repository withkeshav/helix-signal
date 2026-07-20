"""Generic OpenAI-compatible LLM client backed by the ai_providers registry."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import AiProvider
from providers.settings_crypto import decrypt_secret, encrypt_secret

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 60.0

_SEED_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "ollama_cloud",
        "label": "Ollama Cloud",
        "base_url": "https://ollama.com/v1",
        "secret_setting": "secret_ollama_api_key",
        "env_key": "OLLAMA_API_KEY",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "secret_setting": "secret_openrouter_api_key",
        "env_key": "OPENROUTER_API_KEY",
    },
)


def _completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _models_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/models"):
        return base
    return f"{base}/models"


def decrypt_provider_key(api_key_enc: str) -> str:
    if not api_key_enc:
        return ""
    return decrypt_secret(api_key_enc) or ""


def get_provider(db: Session, provider_id: str) -> AiProvider | None:
    if not provider_id:
        return None
    return db.get(AiProvider, provider_id)


def get_enabled_provider(db: Session, provider_id: str) -> AiProvider | None:
    row = get_provider(db, provider_id)
    if not row or not row.enabled:
        return None
    if not decrypt_provider_key(row.api_key_enc).strip():
        return None
    return row


def seed_default_providers(db: Session) -> None:
    """Create ollama_cloud / openrouter registry rows from existing secrets when missing."""
    from providers.settings import get_secret

    created = False
    for spec in _SEED_SPECS:
        if db.get(AiProvider, spec["id"]) is not None:
            continue
        api_key = str(get_secret(spec["secret_setting"], db) or os.getenv(spec["env_key"], "")).strip()
        if not api_key:
            continue
        db.add(
            AiProvider(
                id=spec["id"],
                label=spec["label"],
                base_url=spec["base_url"],
                api_key_enc=encrypt_secret(api_key),
                enabled=True,
            )
        )
        created = True
    if created:
        db.commit()


def chat_completion(
    db: Session,
    provider_id: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 256,
    temperature: float | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any] | None:
    """POST {base_url}/chat/completions for a registered provider."""
    row = get_enabled_provider(db, provider_id)
    if not row or not model:
        return None

    api_key = decrypt_provider_key(row.api_key_enc).strip()
    if not api_key:
        return None

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if temperature is not None:
        payload["temperature"] = temperature

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                _completions_url(row.base_url),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        log.warning("llm.chat_completion_failed", extra={"provider_id": provider_id, "model": model}, exc_info=True)
        return None

    choices = data.get("choices") or []
    if not choices:
        return None
    text = (choices[0].get("message") or {}).get("content") or ""
    usage = data.get("usage") or {}
    return {
        "provider": provider_id,
        "model": model,
        "text": text,
        "tokens": int(usage.get("total_tokens") or 0),
    }


def test_provider_connection(db: Session, provider_id: str) -> dict[str, Any]:
    """Verify provider credentials via GET /models and persist last_test_*."""
    row = get_provider(db, provider_id)
    if not row:
        return {"ok": False, "error": "provider_not_found"}

    now = datetime.now(timezone.utc)
    api_key = decrypt_provider_key(row.api_key_enc).strip()
    if not api_key:
        row.last_test_at = now
        row.last_test_ok = False
        row.last_test_error = "no_api_key"
        db.commit()
        return {"ok": False, "error": "no_api_key"}

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                _models_url(row.base_url),
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
        row.last_test_at = now
        row.last_test_ok = True
        row.last_test_error = None
        db.commit()
        return {"ok": True}
    except Exception as exc:
        err = f"{type(exc).__name__}:{exc}"[:512]
        row.last_test_at = now
        row.last_test_ok = False
        row.last_test_error = err
        db.commit()
        return {"ok": False, "error": err}


def list_provider_models(db: Session, provider_id: str) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch model catalog from provider base_url/models."""
    row = get_enabled_provider(db, provider_id)
    if not row:
        return [], "no_api_key"

    api_key = decrypt_provider_key(row.api_key_enc).strip()
    if not api_key:
        return [], "no_api_key"

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                _models_url(row.base_url),
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code >= 400:
                return [], f"provider_http_{resp.status_code}"
            data = resp.json()
    except Exception as exc:
        return [], f"provider_error:{type(exc).__name__}"

    models: list[dict[str, Any]] = []
    for model in data.get("data", []) or []:
        mid = model.get("id", "")
        if not mid:
            continue
        models.append(
            {
                "id": mid,
                "name": mid,
                "description": model.get("description", ""),
                "max_tokens": model.get("max_context_length"),
            }
        )
    return models, None
