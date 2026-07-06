from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from structlog import get_logger

from database import OsintArticle, OsintArticleAsset, SignalEvent
from services.attestation import get_attestation_status, refresh_attestation_reports
from services.rss_feed import (
    ENABLE_NLP,
    RSS_FEEDS,
    _classify_asset,
    _fetch_cryptocurrency_cv,
    _fetch_rss,
    _strip_html,
    classify_article_structured,
)

log = get_logger(__name__)


def _compute_sentiment(text: str, nlp_enabled: bool | None = None) -> dict[str, Any]:
    active = ENABLE_NLP if nlp_enabled is None else nlp_enabled
    if not active or not text:
        return {"score": 0.0, "label": "neutral"}
    from services.sentiment import analyze_batch
    results = analyze_batch([text])
    return results[0] if results else {"score": 0.0, "label": "neutral"}


def _batch_sentiment(titles: list[str], nlp_active: bool) -> list[dict[str, Any]]:
    if not nlp_active or not titles:
        return [{"score": 0.0, "label": "neutral"} for _ in titles]
    from services.sentiment import analyze_batch
    return analyze_batch(titles)


def ingest_osint_feed(db: Session) -> int:
    from providers.settings import get_setting
    from services.sentiment import clear_cache as _clear_sentiment_cache
    nlp_from_settings = get_setting("feature_nlp_sentiment", db)
    nlp_active = nlp_from_settings if isinstance(nlp_from_settings, bool) else ENABLE_NLP
    _clear_sentiment_cache()

    all_articles: list[dict[str, Any]] = []
    for source, url in RSS_FEEDS.items():
        for art in _fetch_rss(url, source):
            if _article_exists(db, art["title"], art["source"]):
                continue
            assets = _classify_asset(art["title"] + " " + (art["summary"] or ""))
            all_articles.append({**art, "assets": assets})

    for art in _fetch_cryptocurrency_cv():
        if _article_exists(db, art["title"], art["source"]):
            continue
        assets = _classify_asset(art["title"])
        all_articles.append({**art, "assets": assets})

    if not all_articles:
        return 0

    titles = [a["title"] for a in all_articles]
    sentiments = _batch_sentiment(titles, nlp_active)

    classification_cache: dict[str, dict[str, Any]] = {}
    for art, sentiment in zip(all_articles, sentiments):
        classify_key = art["title"][:100]
        if classify_key not in classification_cache:
            classification_cache[classify_key] = classify_article_structured(art["title"], art.get("summary", ""))
        cls = classification_cache[classify_key]

        article = OsintArticle(
            source=art["source"],
            title=art["title"],
            url=art["url"],
            summary=art["summary"],
            published_at=art["published_at"],
            sentiment_score=sentiment["score"],
            sentiment_label=sentiment["label"],
            entities=json.dumps(art["assets"]) if art["assets"] else None,
            event_type=cls["event_type"],
            driver_category=cls["driver_category"],
            source_authority=cls["source_authority"],
            is_leading_indicator=cls["is_leading_indicator"],
            extracted_numbers_json=json.dumps(cls["extracted_numbers"]) if cls.get("extracted_numbers") else None,
        )
        db.add(article)
        db.flush()
        for sym in (art["assets"] or []):
            db.add(OsintArticleAsset(article_id=article.id, asset_symbol=sym.upper()))

    db.commit()
    return len(all_articles)


def _article_exists(db: Session, title: str, source: str) -> bool:
    return db.execute(select(OsintArticle).where(OsintArticle.title == title, OsintArticle.source == source)).scalars().first() is not None


def get_osint_feed(db: Session, *, asset: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    stmt = select(OsintArticle).options(joinedload(OsintArticle.asset_links)).order_by(OsintArticle.published_at.desc().nullslast())
    if asset:
        sym = asset.strip().upper()
        stmt = stmt.join(OsintArticle.asset_links).where(OsintArticleAsset.asset_symbol == sym)
    articles = db.execute(stmt.limit(limit)).scalars().all()
    return [
        {
            "id": a.id,
            "title": a.title,
            "url": a.url,
            "source": a.source,
            "summary": _strip_html(a.summary) if a.summary else None,
            "published_at": a.published_at.isoformat().replace("+00:00", "Z") if a.published_at else None,
            "sentiment_score": a.sentiment_score,
            "sentiment_label": a.sentiment_label,
            "assets": [ln.asset_symbol for ln in a.asset_links],
        }
        for a in articles
    ]


def get_sentiment_timeseries(db: Session, *, asset: str | None = None, window_days: int = 7) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    stmt = select(OsintArticle).where(OsintArticle.published_at >= cutoff).order_by(OsintArticle.published_at.asc())
    if asset:
        sym = asset.strip().upper()
        stmt = stmt.join(OsintArticle.asset_links).where(OsintArticleAsset.asset_symbol == sym)
    articles = db.execute(stmt).scalars().all()
    if not articles:
        return []
    by_day: dict[str, list[float]] = {}
    for a in articles:
        if a.published_at and a.sentiment_score is not None:
            day = a.published_at.strftime("%Y-%m-%d")
            by_day.setdefault(day, []).append(a.sentiment_score)
    return [{"date": d, "avg_sentiment": round(sum(scores) / len(scores), 4), "count": len(scores)} for d, scores in sorted(by_day.items())]


def correlate_sentiment_depeg(db: Session, *, asset: str, window_hours: int = 24) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    sym = asset.strip().upper()
    articles = db.execute(
        select(OsintArticle)
        .where(OsintArticle.published_at >= cutoff, OsintArticle.sentiment_score < -0.3)
        .join(OsintArticle.asset_links)
        .where(OsintArticleAsset.asset_symbol == sym)
        .order_by(OsintArticle.published_at.desc())
    ).scalars().all()
    depeg_events = db.execute(
        select(SignalEvent)
        .where(
            SignalEvent.event_type.like("%depeg%"),
            SignalEvent.timestamp >= cutoff,
            SignalEvent.asset_symbol == sym,
        )
        .order_by(SignalEvent.timestamp.desc())
    ).scalars().all()
    negative_count = len(articles)
    depeg_count = len(depeg_events)
    correlation_found = negative_count > 0 and depeg_count > 0
    return {
        "asset": asset,
        "window_hours": window_hours,
        "negative_sentiment_articles": negative_count,
        "depeg_events_in_window": depeg_count,
        "correlation_found": correlation_found,
        "note": "Negative sentiment spike precedes depeg" if correlation_found else "No correlation detected in window.",
    }
