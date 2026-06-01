"""Source usage tracking — persistent per-source API call counters and rate limiting."""

import time
from datetime import datetime, timezone, date
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import func

from database import SourceUsage


# In-memory sliding-window rate limit tracker for data sources
_SOURCE_RATE_LIMITS: dict[str, list[float]] = {}


def _check_source_rate_limit(source_name: str) -> bool:
    """Return True if the source is within its configured rate limit.
    Reads rate_limit_rpm from settings metadata defaults.
    """
    from providers.settings import _DEFAULT_SETTINGS
    setting_key = f"provider_{source_name}"
    meta = _DEFAULT_SETTINGS.get(setting_key, {})
    rpm = meta.get("rate_limit_rpm", 0)
    if rpm <= 0:
        return True
    now = time.time()
    window = 60.0
    timestamps = _SOURCE_RATE_LIMITS.get(source_name, [])
    timestamps = [t for t in timestamps if now - t < window]
    _SOURCE_RATE_LIMITS[source_name] = timestamps
    return len(timestamps) < rpm


def _record_source_call(source_name: str) -> None:
    """Record a call timestamp for rate limit tracking."""
    if source_name not in _SOURCE_RATE_LIMITS:
        _SOURCE_RATE_LIMITS[source_name] = []
    _SOURCE_RATE_LIMITS[source_name].append(time.time())


def increment_source_usage(db: Session, source_name: str) -> None:
    """Increment the call count for a source for today."""
    today = date.today().isoformat()
    now = datetime.now(timezone.utc)

    usage = db.query(SourceUsage).filter(
        SourceUsage.source_name == source_name,
        SourceUsage.usage_date == today,
    ).first()

    if usage:
        usage.call_count += 1
        usage.last_call_at = now
        usage.updated_at = now
    else:
        usage = SourceUsage(
            source_name=source_name,
            usage_date=today,
            call_count=1,
            last_call_at=now,
        )
        db.add(usage)

    db.commit()


def get_source_usage(db: Session, source_name: str | None = None) -> list[dict[str, Any]]:
    """Get usage stats for all sources or a specific source."""
    today = date.today().isoformat()
    query = db.query(SourceUsage)

    if source_name:
        query = query.filter(SourceUsage.source_name == source_name)

    usage_records = query.filter(SourceUsage.usage_date == today).all()

    result = []
    for record in usage_records:
        result.append({
            "source_name": record.source_name,
            "usage_date": record.usage_date,
            "call_count": record.call_count,
            "last_call_at": record.last_call_at.isoformat() if record.last_call_at else None,
        })

    return result


def get_source_usage_summary(db: Session) -> dict[str, Any]:
    """Get a summary of all source usage for today."""
    today = date.today().isoformat()

    usage_records = db.query(SourceUsage).filter(SourceUsage.usage_date == today).all()

    sources = {}
    total_calls = 0

    for record in usage_records:
        sources[record.source_name] = {
            "call_count": record.call_count,
            "last_call_at": record.last_call_at.isoformat() if record.last_call_at else None,
        }
        total_calls += record.call_count

    return {
        "date": today,
        "total_calls": total_calls,
        "sources": sources,
    }