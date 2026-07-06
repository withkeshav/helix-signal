"""GET /api/v1/assets/{symbol}/narrative — AI risk assessment, cached in Redis.

Cache backend: core.cache (core/cache_manager.py) — Redis when REDIS_URL is set,
with automatic in-memory fallback. TTL: 1800s (30 min).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db

router = APIRouter()


class NarrativeResponse(BaseModel):
    symbol: str
    narrative: str
    generated_at: str
    cached: bool = False


@router.get("/assets/{symbol}/narrative", response_model=NarrativeResponse)
async def narrative(symbol: str, db: Session = Depends(get_db)):
    sym = symbol.upper()
    cache_key = f"narrative:{sym}"

    try:
        from core.cache import cache
        cached = cache.get(cache_key)
        if cached is not None:
            data = json.loads(cached)
            return NarrativeResponse(
                symbol=sym, narrative=data["narrative"],
                generated_at=data["generated_at"], cached=True,
            )
    except Exception:
        pass

    prompt = (
        f"You are a stablecoin risk analyst. In exactly 3 sentences, "
        f"describe the current risk status of {sym}. "
        f"Sentence 1: current risk score and primary risk driver. "
        f"Sentence 2: most recent signal event (if any in last 24h). "
        f"Sentence 3: recommended monitoring action. "
        f"Be specific and factual. Do not hedge."
    )
    narrative_text = ""
    try:
        from services.ai_router import _ollama_cloud
        from providers.settings import get_setting
        import asyncio
        api_key = get_setting("secret_ollama_api_key", db)
        result = await asyncio.to_thread(
            _ollama_cloud,
            prompt=prompt,
            max_tokens=200,
            system="You are a stablecoin risk analyst. Be factual and concise.",
            _resolved_api_key=str(api_key or ""),
        )
        if result and result.get("text"):
            narrative_text = result["text"].strip()
    except Exception:
        pass

    if not narrative_text:
        narrative_text = f"{sym} risk assessment temporarily unavailable."

    generated_at = datetime.now(timezone.utc).isoformat()
    try:
        from core.cache import cache
        cache.set(cache_key, json.dumps({"narrative": narrative_text, "generated_at": generated_at}), ex=1800)
    except Exception:
        pass

    return NarrativeResponse(symbol=sym, narrative=narrative_text, generated_at=generated_at, cached=False)
