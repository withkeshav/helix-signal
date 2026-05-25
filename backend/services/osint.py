from __future__ import annotations

import html as html_mod
import json
import os
import re
import xml.etree.ElementTree as ET
import calendar
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any

import httpx
from sqlalchemy.orm import Session
from structlog import get_logger

from database import OsintArticle, SignalEvent, SourceStatus
from signal_engine.core import get_asset_by_symbol, load_enabled_assets

log = get_logger(__name__)

RSS_FEEDS = {
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/rss",
    "theblock": "https://www.theblock.co/rss.xml",
    "cryptoslate": "https://cryptoslate.com/feed/",
    "decrypt": "https://decrypt.co/feed",
    "bitcoincom": "https://news.bitcoin.com/feed/",
    "thedefiant": "https://thedefiant.io/api/feed",
}

CRYPTOCURRENCY_CV_URL = "https://api.cryptocurrency.cv/v1/news/latest"
ENABLE_NLP = os.getenv("ENABLE_NLP", "").strip().lower() in ("1", "true", "yes")


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._text: list[str] = []

    def handle_data(self, data: str) -> None:
        self._text.append(data)

    def get_text(self) -> str:
        return "".join(self._text)


def _strip_html(raw: str) -> str:
    if not raw:
        return ""
    stripper = _HTMLStripper()
    stripper.feed(raw)
    return html_mod.unescape(stripper.get_text()).strip()


def _fetch_rss(url: str, source: str) -> list[dict[str, Any]]:
    try:
        resp = httpx.get(url, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        articles: list[dict[str, Any]] = []
        for item in root.iter("item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            desc = _strip_html(item.findtext("description", ""))
            pub_date = item.findtext("pubDate", "")
            dt = _parse_rss_date(pub_date)
            articles.append({"title": title, "url": link, "summary": desc, "published_at": dt, "source": source})
        return articles
    except Exception as exc:
        log.warning("rss_fetch_failed", source=source, error=str(exc))
        return []


def _parse_rss_date(date_str: str) -> datetime | None:
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _fetch_cryptocurrency_cv() -> list[dict[str, Any]]:
    try:
        resp = httpx.get(CRYPTOCURRENCY_CV_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        articles: list[dict[str, Any]] = []
        for post in data.get("results") or data.get("data") or data.get("articles") or []:
            if not isinstance(post, dict):
                continue
            title = post.get("title", "")
            url = post.get("url", "") or post.get("link", "")
            published = post.get("published_at") or post.get("publishedAt") or post.get("date") or post.get("createdAt")
            dt = None
            if published:
                try:
                    dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                except Exception:
                    pass
            articles.append({
                "title": title,
                "url": url,
                "summary": post.get("description", "") or post.get("summary", ""),
                "published_at": dt,
                "source": post.get("source", "") or "cryptocurrency_cv",
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

    for art, sentiment in zip(all_articles, sentiments):
        db.add(OsintArticle(
            asset_symbols=",".join(art["assets"]) if art["assets"] else None,
            source=art["source"],
            title=art["title"],
            url=art["url"],
            summary=art["summary"],
            published_at=art["published_at"],
            sentiment_score=sentiment["score"],
            sentiment_label=sentiment["label"],
            entities=json.dumps(art["assets"]) if art["assets"] else None,
        ))

    db.commit()
    return len(all_articles)


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
            "summary": _strip_html(a.summary) if a.summary else None,
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
    "PYUSD": {"issuer": "Paxos/PayPal", "url": "https://paxos.com/pyusd-transparency/", "last_report": None, "observability": "attestation"},
}

_ATTESTATION_CACHE: dict[str, Any] = {"fetched_at": None, "reports": {}}
_ATTESTATION_CACHE_TTL = int(os.getenv("ATTESTATION_CACHE_TTL_SECONDS", "21600"))
_ATTESTATION_HINT_WORDS = ("attestation", "reserve", "transparency", "report", "proof")
_MONTH_NAMES = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December"
_DATE_PATTERNS = (
    re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b"),
    re.compile(rf"\b({_MONTH_NAMES})\s+(\d{{1,2}}),\s*(20\d{{2}})\b", re.IGNORECASE),
    re.compile(rf"\b(\d{{1,2}})\s+({_MONTH_NAMES})\s+(20\d{{2}})\b", re.IGNORECASE),
)
_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _normalize_month(month: str) -> int | None:
    return _MONTH_MAP.get(month.strip()[:4].lower())


def _is_valid_report_date(dt: datetime) -> bool:
    now = datetime.now(timezone.utc)
    return datetime(2020, 1, 1, tzinfo=timezone.utc) <= dt <= (now + timedelta(days=1))


def _extract_report_date_from_text(raw: str) -> datetime | None:
    text = re.sub(r"\s+", " ", raw)
    lower = text.lower()
    candidates: list[datetime] = []
    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span()
            context = lower[max(0, start - 120): min(len(lower), end + 120)]
            if not any(hint in context for hint in _ATTESTATION_HINT_WORDS):
                continue
            dt: datetime | None = None
            try:
                if pattern is _DATE_PATTERNS[0]:
                    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                    dt = datetime(year, month, day, tzinfo=timezone.utc)
                elif pattern is _DATE_PATTERNS[1]:
                    month = _normalize_month(match.group(1))
                    day = int(match.group(2))
                    year = int(match.group(3))
                    if month is not None:
                        dt = datetime(year, month, day, tzinfo=timezone.utc)
                else:
                    day = int(match.group(1))
                    month = _normalize_month(match.group(2))
                    year = int(match.group(3))
                    if month is not None:
                        dt = datetime(year, month, day, tzinfo=timezone.utc)
            except Exception:
                dt = None
            if dt and _is_valid_report_date(dt):
                candidates.append(dt)
    return max(candidates) if candidates else None


def _extract_latest_monthly_attestation_date(raw: str) -> datetime | None:
    # Paxos pages often publish month-only attestation markers (e.g. "2026 Jan Feb Mar")
    # with no day value. We map to the month-end date as a conservative representation.
    text = re.sub(r"\s+", " ", raw)
    lower = text.lower()
    anchor = lower.find("attestations")
    scoped = text[anchor:] if anchor >= 0 else text
    year_pattern = re.compile(r"(20\d{2})")
    month_pattern = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\b", re.IGNORECASE)
    years = [(m.start(), int(m.group(1))) for m in year_pattern.finditer(scoped)]
    if not years:
        return None
    best: datetime | None = None
    for idx, (pos, year) in enumerate(years):
        next_pos = years[idx + 1][0] if idx + 1 < len(years) else len(scoped)
        segment = scoped[pos:next_pos]
        months = []
        for mm in month_pattern.finditer(segment):
            m = _MONTH_MAP.get(mm.group(1).lower())
            if m is not None:
                months.append(m)
        if not months:
            continue
        latest_month = max(months)
        day = calendar.monthrange(year, latest_month)[1]
        candidate = datetime(year, latest_month, day, tzinfo=timezone.utc)
        if _is_valid_report_date(candidate) and (best is None or candidate > best):
            best = candidate
    return best


def _fetch_last_report_date(url: str) -> datetime | None:
    try:
        resp = httpx.get(url, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        if "paxos.com/pyusd-transparency" in url:
            from_index = _fetch_pyusd_attestation_date_from_framer_index(resp.text)
            if from_index is not None:
                return from_index
        exact = _extract_report_date_from_text(resp.text)
        if exact is not None:
            return exact
        return _extract_latest_monthly_attestation_date(resp.text)
    except Exception:
        return None


def _fetch_pyusd_attestation_date_from_framer_index(page_html: str) -> datetime | None:
    m = re.search(r'framer-search-index"\s+content="([^"]+)"', page_html)
    if not m:
        return None
    index_url = m.group(1).replace("&amp;", "&")
    try:
        idx_resp = httpx.get(index_url, timeout=20, follow_redirects=True)
        idx_resp.raise_for_status()
        payload = idx_resp.json()
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None

    entry = payload.get("/pyusd-transparency")
    if entry is None:
        for key, val in payload.items():
            if isinstance(key, str) and "pyusd-transparency" in key and isinstance(val, dict):
                entry = val
                break
    if not isinstance(entry, dict):
        return None

    chunks: list[str] = []
    for fld in ("h1", "h2", "h3", "p", "description", "title"):
        val = entry.get(fld)
        if isinstance(val, list):
            chunks.extend(str(x) for x in val)
        elif isinstance(val, str):
            chunks.append(val)
    if not chunks:
        return None
    joined = " ".join(chunks)
    return _extract_latest_monthly_attestation_date(joined)


def refresh_attestation_reports(*, force: bool = False) -> dict[str, datetime | None]:
    fetched_at = _ATTESTATION_CACHE.get("fetched_at")
    now = datetime.now(timezone.utc)
    if not force and isinstance(fetched_at, datetime):
        if (now - fetched_at).total_seconds() < _ATTESTATION_CACHE_TTL:
            return dict(_ATTESTATION_CACHE.get("reports") or {})

    reports: dict[str, datetime | None] = {}
    for sym, info in ATTESTATION_CHECKLIST.items():
        if info.get("observability") != "attestation":
            reports[sym] = None
            continue
        reports[sym] = _fetch_last_report_date(str(info.get("url") or ""))

    _ATTESTATION_CACHE["fetched_at"] = now
    _ATTESTATION_CACHE["reports"] = reports
    return dict(reports)


def _attestation_status_from_age_days(age_days: int | None) -> str:
    if age_days is None:
        return "unknown"
    if age_days < 90:
        return "fresh"
    if age_days < 180:
        return "aging"
    return "stale"


def _supply_feed_status_from_age_seconds(age_seconds: float | None) -> str:
    if age_seconds is None:
        return "unknown"
    if age_seconds <= 900:
        return "fresh"
    if age_seconds <= 3600:
        return "aging"
    return "stale"


def _supply_feed_block(defillama: SourceStatus | None, *, now: datetime) -> dict[str, Any]:
    updated_at: datetime | None = None
    if defillama and defillama.last_successful_fetch:
        updated_at = defillama.last_successful_fetch
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
    age_seconds = (now - updated_at).total_seconds() if updated_at else None
    age_minutes = round(age_seconds / 60.0, 1) if age_seconds is not None else None
    return {
        "supply_feed_source": "defillama",
        "supply_feed_status": _supply_feed_status_from_age_seconds(age_seconds),
        "supply_feed_updated_at": updated_at.isoformat().replace("+00:00", "Z") if updated_at else None,
        "supply_feed_age_minutes": age_minutes,
    }


def get_attestation_status(db: Session | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    report_map = refresh_attestation_reports()
    defillama = None
    if db is not None:
        defillama = db.query(SourceStatus).filter(SourceStatus.source_name == "defillama").first()
    feed = _supply_feed_block(defillama, now=now)
    result = {}
    for sym, info in ATTESTATION_CHECKLIST.items():
        observability = info.get("observability")
        report: datetime | None = None
        attestation_status = "unknown"
        if observability == "attestation":
            report = report_map.get(sym)
            if report and report.tzinfo is None:
                report = report.replace(tzinfo=timezone.utc)
            age_days = (now - report).days if report else None
            attestation_status = _attestation_status_from_age_days(age_days)
        elif observability == "onchain_feed":
            attestation_status = "n/a"

        age_days = (now - report).days if report else None
        result[sym] = {
            "issuer": info["issuer"],
            "url": info["url"],
            "observability": observability,
            # Issuer attestation report (only when provably parsed from issuer source)
            "attestation_status": attestation_status,
            "attestation_last_report": report.isoformat().replace("+00:00", "Z") if report else None,
            "attestation_age_days": age_days,
            # Backward-compatible aliases used by older frontend bindings
            "status": attestation_status,
            "last_report": report.isoformat().replace("+00:00", "Z") if report else None,
            "age_days": age_days,
            **feed,
        }
    return result


def correlate_sentiment_depeg(db: Session, *, asset: str, window_hours: int = 24) -> dict[str, Any]:
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    sym = asset.strip().upper()
    articles = db.query(OsintArticle).filter(
        OsintArticle.published_at >= cutoff,
        OsintArticle.sentiment_score < -0.3,
        OsintArticle.asset_symbols.contains(sym),
    ).order_by(OsintArticle.published_at.desc()).all()
    depeg_events = db.query(SignalEvent).filter(
        SignalEvent.event_type.like("%depeg%"),
        SignalEvent.timestamp >= cutoff,
        SignalEvent.asset_symbol == sym,
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
