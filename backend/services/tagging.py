"""Auto-tagging engine — creates AddressTag entries from system events."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import AddressTag, BlacklistEvent, OsintArticle


def auto_tag_from_blacklist(db: Session, event: BlacklistEvent) -> AddressTag | None:
    if not event.frozen_address:
        return None
    stmt = select(AddressTag).where(
        AddressTag.address == event.frozen_address.lower(),
        AddressTag.source == "blacklist_monitor",
        AddressTag.label == "sanctioned",
    )
    existing = db.execute(stmt).scalar_one_or_none()
    if existing:
        return None

    tag = AddressTag(
        address=event.frozen_address.lower(),
        chain=event.chain.lower() if event.chain else None,
        source="blacklist_monitor",
        label="sanctioned",
        category="compliance",
        confidence=1.0,
    )
    db.add(tag)
    db.flush()
    return tag


def auto_tag_from_osint(db: Session, article: OsintArticle) -> list[AddressTag]:
    tags: list[AddressTag] = []
    if not article.entities:
        return tags

    import json
    try:
        entities = json.loads(article.entities) if isinstance(article.entities, str) else article.entities
    except (json.JSONDecodeError, TypeError):
        return tags

    if not isinstance(entities, list):
        return tags

    seen: set[str] = set()
    for ent in entities:
        if not isinstance(ent, str):
            continue
        addr = ent.strip().lower()
        if not addr or addr in seen:
            continue
        seen.add(addr)

        stmt = select(AddressTag).where(
            AddressTag.address == addr,
            AddressTag.source == "osint",
        )
        if db.execute(stmt).scalar_one_or_none():
            continue

        tag = AddressTag(
            address=addr,
            source="osint",
            label=article.event_type or "mentioned",
            category="risk",
            confidence=0.7,
        )
        db.add(tag)
        tags.append(tag)

    if tags:
        db.flush()
    return tags


def get_tags_for_address(db: Session, address: str, chain: str | None = None) -> list[AddressTag]:
    stmt = select(AddressTag).where(AddressTag.address == address.lower())
    if chain:
        stmt = stmt.where(AddressTag.chain == chain.lower())
    return db.execute(stmt).scalars().all()


def merge_duplicate_tags(db: Session) -> int:
    stmt = select(AddressTag).order_by(AddressTag.address, AddressTag.source, AddressTag.label, AddressTag.confidence.desc())
    tags = db.execute(stmt).scalars().all()
    merged = 0
    seen: set[tuple[str, str, str]] = set()
    for tag in tags:
        key = (tag.address, tag.source, tag.label)
        if key in seen:
            db.delete(tag)
            merged += 1
        else:
            seen.add(key)
    if merged:
        db.commit()
    return merged
