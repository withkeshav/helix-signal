import json
from datetime import datetime, timedelta, timezone

from database import SignalEvent
from schemas import SignalEventOut


def utc_normalize(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def window_delta(window: str) -> timedelta:
    if window == "24h":
        return timedelta(hours=24)
    if window == "7d":
        return timedelta(days=7)
    if window == "90d":
        return timedelta(days=90)
    return timedelta(days=30)


def signal_event_rows_to_out(rows: list[SignalEvent]) -> list[SignalEventOut]:
    out: list[SignalEventOut] = []
    for r in rows:
        meta: dict | None = None
        if r.metadata_json:
            try:
                meta = json.loads(r.metadata_json)
            except json.JSONDecodeError:
                meta = None
        out.append(
            SignalEventOut(
                id=r.id,
                asset_symbol=r.asset_symbol,
                chain_key=r.chain_key,
                event_type=r.event_type,
                severity=r.severity,
                title=r.title,
                summary=r.summary,
                old_value=r.old_value,
                new_value=r.new_value,
                delta=r.delta,
                threshold=r.threshold,
                timestamp=r.timestamp,
                metadata=meta,
            )
        )
    return out


def chain_key_from_name(name: str) -> str:
    return str(name).strip().lower().replace(" ", "-")
