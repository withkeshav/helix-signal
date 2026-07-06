from __future__ import annotations

import html as html_mod
import json
import logging
import os
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any

import httpx
import defusedxml.ElementTree as ET
from structlog import get_logger

log = get_logger(__name__)

RSS_USER_AGENT = (
    "Mozilla/5.0 (compatible; HelixSignal/1.0; +https://github.com/withkeshav/helix-signal)"
)

RSS_FEEDS = {
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss",
    "cointelegraph": "https://cointelegraph.com/rss",
    "cryptoslate": "https://cryptoslate.com/feed/",
    "decrypt": "https://decrypt.co/feed",
    "bitcoincom": "https://news.bitcoin.com/feed/",
    "thedefiant": "https://thedefiant.io/api/feed",
    "protos": "https://protos.com/rss",
    "dinews": "https://www.dlnews.com/feed/rss",
    "chainalysis": "https://www.chainalysis.com/blog/feed/",
    "nansen": "https://www.nansen.ai/feed",
    "defillama": "https://defillama.com/rss",
    "bis": "https://www.bis.org/feed.rss",
    "fsb": "https://www.fsb.org/rss/",
}

CRYPTOCURRENCY_CV_URL = "https://api.cryptocurrency.cv/v1/news/latest"
ENABLE_NLP = os.getenv("ENABLE_NLP", "true").strip().lower() in ("1", "true", "yes")


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
        resp = httpx.get(
            url,
            timeout=15,
            headers={"User-Agent": RSS_USER_AGENT},
        )
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
                    logging.getLogger(__name__).debug("Failed to parse OSINT article date", exc_info=True)
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


_STABLECOIN_KEYWORDS = {
    "USDT", "USDC", "DAI", "PYUSD", "TETHER", "CIRCLE", "MAKER", "PAYPAL",
    "FDUSD", "GUSD", "RLUSD", "USD1", "USDG", "USDS", "LUSD", "GHO",
    "crvUSD", "USDY", "BUIDL", "USYC", "sDAI", "sUSDS", "aUSDC",
    "syrupUSDC", "USDe", "sUSDe", "USDD", "FRAX", "USDP", "TUSD",
    "FRAX", "LQTY", "SKY", "ETHE", "ONDO",
}


def _classify_asset(text: str) -> list[str]:
    upper = text.upper()
    found: list[str] = []
    for kw in _STABLECOIN_KEYWORDS:
        if kw in upper:
            found.append(kw)
    return found


CLASSIFIER_SYSTEM_PROMPT = (
    "You are a stablecoin intelligence classifier. Given a news article title and summary, "
    "return JSON with: event_type (one of: DEPEG, HACK EXPLOIT, ADDRESS FREEZE BLACKLIST, "
    "OFAC SANCTION, LAW ENFORCEMENT SEIZURE, REGULATION LAW, MONEY LAUNDERING CASE, "
    "SCAM FRAUD, OTHER), affected_assets (list of coin symbols), severity (info/warning/critical), "
    "driver_category (onchain/regulatory/economic/operational/geopolitical), "
    "extracted_numbers (list of floats), is_leading_indicator (bool), "
    "confidence (0.0-1.0), source_authority (0.0-1.0). "
    "Return ONLY valid JSON, no commentary."
)


def classify_article_structured(title: str, summary: str) -> dict[str, Any]:
    """Use Ollama Cloud to classify a stablecoin article into structured fields."""
    try:
        from services.components.ai.providers._ollama_cloud import _ollama_cloud
        text = f"Title: {title}\nSummary: {summary}"
        result = _ollama_cloud(system=CLASSIFIER_SYSTEM_PROMPT, user=text, json_mode=True)
        raw = result.get("content", "{}") if isinstance(result, dict) else str(result)
        parsed = json.loads(raw)
        return {
            "event_type": parsed.get("event_type", "OTHER"),
            "affected_assets": parsed.get("affected_assets", []),
            "severity": parsed.get("severity", "info"),
            "driver_category": parsed.get("driver_category", "economic"),
            "extracted_numbers": parsed.get("extracted_numbers", []),
            "is_leading_indicator": bool(parsed.get("is_leading_indicator", False)),
            "confidence": float(parsed.get("confidence", 0.5)),
            "source_authority": float(parsed.get("source_authority", 0.5)),
        }
    except Exception:
        log.exception("classify_article_structured.failed")
        return {
            "event_type": "OTHER", "affected_assets": [], "severity": "info",
            "driver_category": "economic", "extracted_numbers": [],
            "is_leading_indicator": False, "confidence": 0.0, "source_authority": 0.0,
        }
