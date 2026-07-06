"""Tests for the auto-tagging engine."""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy.orm import Session

from database import AddressTag, BlacklistEvent, OsintArticle
from services.tagging import (
    auto_tag_from_blacklist,
    auto_tag_from_osint,
    get_tags_for_address,
    merge_duplicate_tags,
)

_counter = [0]


def _bev(frozen_address: str = "0xdead", frozen_usd: float = 1_000_000) -> BlacklistEvent:
    _counter[0] += 1
    return BlacklistEvent(
        id=_counter[0],
        asset_symbol="USDT",
        chain="ethereum",
        frozen_address=frozen_address,
        frozen_balance_usd=frozen_usd,
        event_type="freeze",
        tx_hash=f"0x{_counter[0]:x}",
        intelligence_note=f"Test {_counter[0]}",
        timestamp=datetime.now(timezone.utc),
    )


def test_auto_tag_from_blacklist_creates_tag(db_session: Session):
    event = _bev(frozen_address="0xfrozen")
    db_session.add(event)
    db_session.flush()

    tag = auto_tag_from_blacklist(db_session, event)
    assert tag is not None
    assert tag.address == "0xfrozen"
    assert tag.source == "blacklist_monitor"
    assert tag.label == "sanctioned"


def test_auto_tag_from_blacklist_skips_duplicate(db_session: Session):
    event = _bev(frozen_address="0xfrozen2")
    db_session.add(event)
    db_session.flush()

    auto_tag_from_blacklist(db_session, event)
    tag2 = auto_tag_from_blacklist(db_session, event)
    assert tag2 is None


def test_auto_tag_from_blacklist_skips_empty_address(db_session: Session):
    event = BlacklistEvent(
        id=999,
        asset_symbol="USDT",
        chain="ethereum",
        frozen_address=None,
        frozen_balance_usd=1000000,
        event_type="freeze",
        tx_hash="0x999",
        intelligence_note="Test",
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(event)
    db_session.flush()

    tag = auto_tag_from_blacklist(db_session, event)
    assert tag is None


def test_auto_tag_from_osint_creates_tags(db_session: Session):
    article = OsintArticle(
        source="coindesk",
        title="Test article with address 0xosintaddr",
        entities='["0xosintaddr", "0xanother"]',
        event_type="hack",
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(article)
    db_session.flush()

    tags = auto_tag_from_osint(db_session, article)
    assert len(tags) == 2
    assert tags[0].source == "osint"
    assert tags[0].address == "0xosintaddr"


def test_auto_tag_from_osint_skips_duplicate(db_session: Session):
    article = OsintArticle(
        source="coindesk",
        title="Test article",
        entities='["0xdup"]',
        event_type="hack",
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(article)
    db_session.flush()

    auto_tag_from_osint(db_session, article)
    tags2 = auto_tag_from_osint(db_session, article)
    assert len(tags2) == 0


def test_get_tags_for_address(db_session: Session):
    tag = AddressTag(address="0xgetme", source="manual", label="test", category="info")
    db_session.add(tag)
    db_session.commit()

    result = get_tags_for_address(db_session, "0xgetme")
    assert len(result) == 1


def test_merge_duplicate_tags(db_session: Session):
    tag1 = AddressTag(address="0xdup", source="manual", label="test", category="info", confidence=1.0)
    tag2 = AddressTag(address="0xdup", source="manual", label="test", category="info", confidence=0.5)
    db_session.add_all([tag1, tag2])
    db_session.commit()

    merged = merge_duplicate_tags(db_session)
    assert merged == 1

    remaining = get_tags_for_address(db_session, "0xdup")
    assert len(remaining) == 1
