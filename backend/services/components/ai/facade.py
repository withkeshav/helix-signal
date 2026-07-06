"""Public AI facade — stable surface for callers outside the AI subsystem.

Re-exports the public (no-underscore) names that external code should import:
    from services.components.ai import ollama_cloud, within_budget, get_budget_status

The underscore-prefixed originals remain in `services.ai_router` and
`services.components.ai.budget` for backward compatibility; new code should
import from this facade instead.
"""

from __future__ import annotations

from typing import Any

from services.ai_router import _ollama_cloud as ollama_cloud
from services.components.ai.budget import _within_budget as within_budget
from services.components.ai.budget import get_budget_status

__all__ = ["ollama_cloud", "within_budget", "get_budget_status"]