"""Public AI facade — stable surface for callers outside the AI subsystem."""

from __future__ import annotations

from services.ai_router import _ollama_cloud as ollama_cloud

__all__ = ["ollama_cloud"]
