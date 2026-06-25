"""AI provider usage tracking — persistent per-provider call, token, and cost counters."""

from datetime import datetime, timezone, date
from typing import Any

from sqlalchemy.orm import Session

from database import AiUsage


def increment_ai_usage(
    db: Session,
    provider: str,
    model: str = "",
    tokens: int = 0,
    cost: float = 0.0,
) -> None:
    """Increment usage counters for an AI provider for today."""
    today = date.today().isoformat()
    now = datetime.now(timezone.utc)

    usage = db.query(AiUsage).filter(
        AiUsage.provider == provider,
        AiUsage.model == model,
        AiUsage.usage_date == today,
    ).first()

    if usage:
        usage.calls += 1
        usage.tokens += tokens
        usage.estimated_cost += cost
        usage.updated_at = now
    else:
        usage = AiUsage(
            provider=provider,
            model=model,
            usage_date=today,
            calls=1,
            tokens=tokens,
            estimated_cost=cost,
        )
        db.add(usage)

    db.commit()


def get_ai_usage(db: Session, provider: str | None = None) -> list[dict[str, Any]]:
    """Get today's AI usage per provider."""
    today = date.today().isoformat()
    query = db.query(AiUsage).filter(AiUsage.usage_date == today)

    if provider:
        query = query.filter(AiUsage.provider == provider)

    records = query.all()
    result = []
    for r in records:
        result.append({
            "provider": r.provider,
            "model": r.model,
            "usage_date": r.usage_date,
            "calls": r.calls,
            "tokens": r.tokens,
            "estimated_cost": round(r.estimated_cost, 6),
        })
    return result


def get_ai_usage_summary(db: Session) -> dict[str, Any]:
    """Get a summary of today's AI usage across all providers."""
    today = date.today().isoformat()
    records = db.query(AiUsage).filter(AiUsage.usage_date == today).all()

    providers = {}
    total_calls = 0
    total_tokens = 0
    total_cost = 0.0

    for r in records:
        providers[r.provider] = {
            "model": r.model,
            "calls": r.calls,
            "tokens": r.tokens,
            "estimated_cost": round(r.estimated_cost, 6),
        }
        total_calls += r.calls
        total_tokens += r.tokens
        total_cost += r.estimated_cost

    return {
        "date": today,
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "total_estimated_cost": round(total_cost, 6),
        "providers": providers,
    }
