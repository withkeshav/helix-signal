"""External intel webhook — receives pre-classified stablecoin intelligence articles.

POST /api/v1/webhooks/intel
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from structlog import get_logger

from database import OsintArticle, OsintArticleAsset, get_db
from providers.settings import get_setting

log = get_logger(__name__)
router = APIRouter()

EXTERNAL_SIGNAL_MAP: dict[str, tuple[str, str, float]] = {
    "DEPEG":                      ("DEPEG_CONFIRMED",    "critical", 1.5),
    "HACK EXPLOIT":               ("PROTOCOL_EXPLOIT",   "critical", 1.4),
    "ADDRESS FREEZE BLACKLIST":   ("ISSUER_FREEZE",      "warning",  1.3),
    "OFAC SANCTION":              ("SANCTIONS_ACTION",   "warning",  1.3),
    "LAW ENFORCEMENT SEIZURE":    ("LAW_ENFORCEMENT",    "warning",  1.2),
    "MONEY LAUNDERING CASE":      ("AML_CASE",           "info",     1.1),
    "REGULATION LAW":             ("REGULATORY_PRESSURE","info",     1.1),
    "SCAM FRAUD":                 ("FRAUD_SIGNAL",       "info",     1.0),
    "OTHER":                      ("GEOPOLITICAL",       "info",     1.0),
}

SOURCE_AUTHORITY: dict[str, float] = {
    "tether": 0.85, "circle": 0.85, "makerdao": 0.80, "sky": 0.80,
    "ethena": 0.75, "liquity": 0.75, "aave": 0.75, "ondo": 0.70,
    "coindesk": 0.65, "cointelegraph": 0.60, "theblock": 0.65,
    "protos": 0.60, "dinews": 0.65, "chainalysis": 0.80, "nansen": 0.75,
    "defillama": 0.70, "bis": 0.90, "fsb": 0.90,
    "default": 0.50,
}

STABLECOIN_TAXONOMY_SYMBOLS: set[str] = {
    "USDT", "USDC", "PYUSD", "FDUSD", "GUSD", "RLUSD", "USD1", "USDG",
    "DAI", "USDS", "LUSD", "GHO", "crvUSD",
    "USDY", "BUIDL", "USYC", "sDAI", "sUSDS", "aUSDC", "syrupUSDC",
    "USDe", "sUSDe", "USDD", "FRAX",
}


def _verify_hmac(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _verify_secret_header(request: Request, header_name: str, secret: str) -> bool:
    received = request.headers.get(header_name, "")
    return hmac.compare_digest(received, secret)


def _extract_field(data: dict, field_path: str) -> Any:
    parts = field_path.split(".")
    value: Any = data
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def _extract_affected_assets(text: str) -> list[str]:
    upper = text.upper()
    found: list[str] = []
    for sym in STABLECOIN_TAXONOMY_SYMBOLS:
        if sym in upper:
            found.append(sym)
    return found


def _lookup_authority(source_domain: str) -> float:
    if not source_domain:
        return SOURCE_AUTHORITY["default"]
    domain_lower = source_domain.lower().strip()
    for key, authority in SOURCE_AUTHORITY.items():
        if key in domain_lower:
            return authority
    return SOURCE_AUTHORITY["default"]


@router.post("/v1/webhooks/intel")
async def receive_external_intel(request: Request, db: Session = Depends(get_db)):
    if not get_setting("external_intel_webhook_enabled", db):
        log.warning("intel_webhook.disabled")
        return {"status": "error", "reason": "webhook_disabled"}

    auth_mode = get_setting("external_intel_auth_mode", db) or "secret_header"
    secret_header_name = get_setting("external_intel_secret_header_name", db) or "X-Intel-Secret"
    webhook_secret = get_setting("external_intel_webhook_secret", db) or ""

    body = await request.body()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        log.warning("intel_webhook.invalid_json")
        return {"status": "error", "reason": "invalid_json"}

    if auth_mode == "hmac_sha256":
        sig = request.headers.get("X-Intel-Signature", "")
        if not _verify_hmac(body, sig, webhook_secret):
            log.warning("intel_webhook.invalid_hmac")
            return {"status": "error", "reason": "invalid_signature"}
    elif auth_mode == "secret_header":
        if not _verify_secret_header(request, secret_header_name, webhook_secret):
            log.warning("intel_webhook.invalid_secret")
            return {"status": "error", "reason": "invalid_secret"}

    field_map_raw = get_setting("external_intel_field_map_json", db) or (
        '{"title":"title","signal":"signal","summary":"summary",'
        '"url":"url","published_at":"publishedAt","source_domain":"source.domain"}'
    )
    try:
        field_map = json.loads(str(field_map_raw))
    except (json.JSONDecodeError, TypeError):
        field_map = {}

    title = _extract_field(payload, field_map.get("title", "title")) or ""
    signal_label = _extract_field(payload, field_map.get("signal", "signal")) or "OTHER"
    summary = _extract_field(payload, field_map.get("summary", "summary")) or ""
    url = _extract_field(payload, field_map.get("url", "url")) or ""
    published_at_raw = _extract_field(payload, field_map.get("published_at", "publishedAt"))
    source_domain = _extract_field(payload, field_map.get("source_domain", "source.domain")) or ""

    if not title and not url:
        log.warning("intel_webhook.missing_fields")
        return {"status": "ok", "processed": False, "reason": "missing_title_and_url"}

    if url:
        existing = db.query(OsintArticle).filter(OsintArticle.url == url).first()
        if existing:
            return {"status": "ok", "processed": False, "reason": "duplicate"}

    published_at = None
    if published_at_raw:
        try:
            published_at = datetime.fromisoformat(str(published_at_raw).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass

    helix_event_type = "GEOPOLITICAL"
    source_authority = _lookup_authority(source_domain)
    for sig_label, (h_type, h_severity, _amp) in EXTERNAL_SIGNAL_MAP.items():
        if signal_label.upper() == sig_label:
            helix_event_type = h_type
            break

    affected_assets = _extract_affected_assets(title + " " + summary)

    min_signal = get_setting("external_intel_min_process_signal", db) or "INFO"
    signal_priority = {"INFO": 0, "warning": 1, "critical": 2}
    if signal_priority.get(helix_event_type.lower() if helix_event_type in ("DEPEG_CONFIRMED", "PROTOCOL_EXPLOIT", "ISSUER_FREEZE", "SANCTIONS_ACTION", "LAW_ENFORCEMENT", "AML_CASE", "REGULATORY_PRESSURE", "FRAUD_SIGNAL", "GEOPOLITICAL") else "INFO", 0) < signal_priority.get(min_signal.upper(), 0):
        log.info("intel_webhook.skipped_low_signal", signal=helix_event_type)
        return {"status": "ok", "processed": False, "reason": "low_signal_priority"}

    article = OsintArticle(
        source=source_domain or "external_intel_webhook",
        title=title,
        url=url,
        summary=summary,
        published_at=published_at or datetime.now(timezone.utc),
        entities=json.dumps(affected_assets) if affected_assets else None,
        event_type=helix_event_type,
        source_authority=source_authority,
    )
    db.add(article)
    db.flush()
    for sym in affected_assets:
        db.add(OsintArticleAsset(article_id=article.id, asset_symbol=sym.upper()))
    db.commit()

    log.info("intel_webhook.processed", title=title[:60], event_type=helix_event_type)
    return {"status": "ok", "processed": True}
