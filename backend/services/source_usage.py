"""Source usage tracking — persistent per-source API call counters."""

from datetime import datetime, timezone, date
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import func

from database import SourceUsage


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