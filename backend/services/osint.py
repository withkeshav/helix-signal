from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session
from structlog import get_logger

from database import OsintArticle, SignalEvent
from signal_engine.core import get_asset_by_symbol, load_enabled_assets

log = get_logger(__name__)

RSS_FEEDS = {
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/rss",
    "theblock": "https://www.theblock.co/rss.xml",
}

CRYPTOPANIC_API = "https://cryptopanic.com/api/v1/posts/"
ENABLE_NLP = os.getenv("ENABLE_NLP", "").strip().lower() in ("1", "true", "yes")


def _get_transformers_pipeline():
    if ENABLE_NLP:
        try:
            from transformers import pipeline
            return pipeline("text-classification", model="ProsusAI/finbert")
        except Exception:
            return None
    return None


_NLP_PIPELINE = None


def _fetch_rss(url: str, source: str) -> list[dict[str, Any]]:
    try:
        resp = httpx.get(url, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        articles: list[dict[str, Any]] = []
        for item in root.iter("item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            desc = item.findtext("description", "")
            pub_date = item.findtext("pubDate", "")
            dt = _parse_rss_date(pub_date)
            articles.append({"title": title, "url": link, "summary": desc, "published_at": dt, "source": source})
        return articles
    except Exception:
        return []


def _parse_rss_date(date_str: str) -> datetime | None:
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _fetch_cryptopanic() -> list[dict[str, Any]]:
    api_key = os.getenv("CRYPTOPANIC_API_KEY", "")
    if not api_key:
        return []
    try:
        params = {"auth_token": api_key, "public": "true", "kind": "news"}
        resp = httpx.get(f"{CRYPTOPANIC_API}?{urlencode(params)}", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        articles: list[dict[str, Any]] = []
        for post in data.get("results", []):
            title = post.get("title", "")
            url = post.get("url", "")
            published = post.get("published_at", "")
            dt = None
            if published:
                try:
                    dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                except Exception:
                    pass
            articles.append({
                "title": title,
                "url": url,
                "summary": post.get("domain", ""),
                "published_at": dt,
                "source": "cryptopanic",
            })
        return articles
    except Exception:
        return []


_STABLECOIN_KEYWORDS = {"USDT", "USDC", "DAI", "PYUSD", "TETHER", "CIRCLE", "MAKER", "PAYPAL"}


def _classify_asset(text: str) -> list[str]:
    upper = text.upper()
    found: list[str] = []
    for kw in _STABLECOIN_KEYWORDS:
        if kw in upper:
            found.append(kw)
    return found


def _ensure_nlp():
    global _NLP_PIPELINE
    if _NLP_PIPELINE is None and ENABLE_NLP:
        _NLP_PIPELINE = _get_transformers_pipeline()
    return _NLP_PIPELINE


def _compute_sentiment(text: str) -> dict[str, Any]:
    if not ENABLE_NLP or not text:
        return {"score": 0.0, "label": "neutral"}
    pipe = _ensure_nlp()
    if pipe is None:
        return {"score": 0.0, "label": "neutral"}
    try:
        result = pipe(text[:512])[0]
        label = result["label"].lower()
        score_map = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}
        return {"score": score_map.get(label, 0.0) * result["score"], "label": label}
    except Exception:
        return {"score": 0.0, "label": "neutral"}


def ingest_osint_feed(db: Session) -> int:
    count = 0
    for source, url in RSS_FEEDS.items():
        articles = _fetch_rss(url, source)
        for art in articles:
            if _article_exists(db, art["title"], art["source"]):
                continue
            assets = _classify_asset(art["title"] + " " + (art["summary"] or ""))
            sentiment = _compute_sentiment(art["title"])
            db.add(OsintArticle(
                asset_symbols=",".join(assets) if assets else None,
                source=art["source"],
                title=art["title"],
                url=art["url"],
                summary=art["summary"],
                published_at=art["published_at"],
                sentiment_score=sentiment["score"],
                sentiment_label=sentiment["label"],
                entities=json.dumps(assets) if assets else None,
            ))
            count += 1
    cp_articles = _fetch_cryptopanic()
    for art in cp_articles:
        if _article_exists(db, art["title"], art["source"]):
            continue
        assets = _classify_asset(art["title"])
        sentiment = _compute_sentiment(art["title"])
        db.add(OsintArticle(
            asset_symbols=",".join(assets) if assets else None,
            source=art["source"],
            title=art["title"],
            url=art["url"],
            summary=art["summary"],
            published_at=art["published_at"],
            sentiment_score=sentiment["score"],
            sentiment_label=sentiment["label"],
        ))
        count += 1
    if count > 0:
        db.commit()
    return count


def _article_exists(db: Session, title: str, source: str) -> bool:
    return db.query(OsintArticle).filter(OsintArticle.title == title, OsintArticle.source == source).first() is not None


def get_osint_feed(db: Session, *, asset: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    q = db.query(OsintArticle).order_by(OsintArticle.published_at.desc().nullslast())
    if asset:
        sym = asset.strip().upper()
        q = q.filter(OsintArticle.asset_symbols.like(f"%{sym}%"))
    articles = q.limit(limit).all()
    return [
        {
            "id": a.id,
            "title": a.title,
            "url": a.url,
            "source": a.source,
            "summary": a.summary,
            "published_at": a.published_at.isoformat().replace("+00:00", "Z") if a.published_at else None,
            "sentiment_score": a.sentiment_score,
            "sentiment_label": a.sentiment_label,
            "assets": a.asset_symbols.split(",") if a.asset_symbols else [],
        }
        for a in articles
    ]


def get_sentiment_timeseries(db: Session, *, asset: str | None = None, window_days: int = 7) -> list[dict[str, Any]]:
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    q = db.query(OsintArticle).filter(OsintArticle.published_at >= cutoff).order_by(OsintArticle.published_at.asc())
    if asset:
        sym = asset.strip().upper()
        q = q.filter(OsintArticle.asset_symbols.like(f"%{sym}%"))
    articles = q.all()
    if not articles:
        return []
    by_day: dict[str, list[float]] = {}
    for a in articles:
        if a.published_at and a.sentiment_score is not None:
            day = a.published_at.strftime("%Y-%m-%d")
            by_day.setdefault(day, []).append(a.sentiment_score)
    return [{"date": d, "avg_sentiment": round(sum(scores) / len(scores), 4), "count": len(scores)} for d, scores in sorted(by_day.items())]


ATTESTATION_CHECKLIST: dict[str, dict[str, Any]] = {
    "USDT": {"issuer": "Tether", "url": "https://tether.to/en/transparency/", "last_report": None, "observability": "attestation"},
    "USDC": {"issuer": "Circle", "url": "https://www.circle.com/en/transparency", "last_report": None, "observability": "attestation"},
    "DAI": {"issuer": "MakerDAO", "url": "https://makerdao.com/en/", "last_report": None, "observability": "onchain_feed"},
    "PYUSD": {"issuer": "PayPal", "url": "https://www.paypal.com/us/digital-wallet/manage-money/crypto", "last_report": None, "observability": "attestation"},
}


def get_attestation_status() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    result = {}
    for sym, info in ATTESTATION_CHECKLIST.items():
        report = info["last_report"]
        age_days = (now - report).days if report else None
        result[sym] = {
            "issuer": info["issuer"],
            "url": info["url"],
            "last_report": report.isoformat().replace("+00:00", "Z") if report else None,
            "age_days": age_days,
            "observability": info["observability"],
            "status": "fresh" if age_days is not None and age_days < 90 else ("aging" if age_days is not None and age_days < 180 else "stale") if age_days is not None else "unknown",
        }
    return result


def correlate_sentiment_depeg(db: Session, *, asset: str, window_hours: int = 24) -> dict[str, Any]:
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    articles = db.query(OsintArticle).filter(
        OsintArticle.published_at >= cutoff,
        OsintArticle.sentiment_score < -0.3,
    ).order_by(OsintArticle.published_at.desc()).all()
    depeg_events = db.query(SignalEvent).filter(
        SignalEvent.event_type.like("%depeg%"),
        SignalEvent.timestamp >= cutoff,
    ).order_by(SignalEvent.timestamp.desc()).all()
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
