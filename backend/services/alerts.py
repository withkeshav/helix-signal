from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests
from sqlalchemy.orm import Session

from database import SignalEvent, SourceStatus
from signal_engine.core import load_configured_chains
from structlog import get_logger

log = get_logger(__name__)

ALERTS_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "alerts.json"


def load_alert_rules() -> list[dict]:
    with ALERTS_CONFIG_PATH.open("r", encoding="utf-8") as f:
        rules = json.load(f)
    return [r for r in rules if isinstance(r, dict) and r.get("enabled", False)]


def evaluate_alerts(db: Session, *, bundle: dict[str, Any], asset_symbol: str, now: datetime) -> list[dict[str, Any]]:
    rules = load_alert_rules()
    fired: list[dict[str, Any]] = []
    sources_orm = db.query(SourceStatus).order_by(SourceStatus.id.asc()).all()
    supply = bundle.get("total_supply")
    price = bundle.get("price")
    depeg_bps = abs((price or 1.0) - 1.0) * 10000 if price else 0
    for rule in rules:
        cond = rule["condition"]
        matched = False
        meta: dict[str, Any] = {"condition": cond}
        if "depeg_bps > 50" in cond and depeg_bps > 50:
            matched = True; meta["depeg_bps"] = depeg_bps
        if "depeg_bps > 100" in cond and depeg_bps > 100:
            matched = True; meta["depeg_bps"] = depeg_bps
        if "supply_change_7d < -3" in cond:
            pass
        if "freshness_age_minutes > 10" in cond:
            age = bundle.get("freshness_age_seconds")
            if age is not None and age > 600:
                matched = True; meta["age_minutes"] = round(age / 60, 1)
        if "source_status = error" in cond:
            for s in sources_orm:
                if s.status == "error":
                    matched = True; meta["source"] = s.source_name
        if matched:
            dedup_key = f"{asset_symbol}:{rule['type']}:{rule['severity']}"
            if not _recently_fired(db, dedup_key, rule.get("cooldown_minutes", 60), now):
                _log_alert_fire(db, asset_symbol=asset_symbol, rule=rule, meta=meta, now=now)
                _dispatch_alert(rule, asset_symbol=asset_symbol, meta=meta)
                fired.append({"type": rule["type"], "severity": rule["severity"], "asset": asset_symbol, "meta": meta})
    return fired


def _recently_fired(db: Session, dedup_key: str, cooldown_minutes: int, now: datetime) -> bool:
    if cooldown_minutes <= 0:
        return False
    cutoff = now - timedelta(minutes=cooldown_minutes)
    existing = db.query(SignalEvent).filter(
        SignalEvent.event_type == dedup_key,
        SignalEvent.timestamp >= cutoff,
    ).first()
    return existing is not None


def _log_alert_fire(db: Session, *, asset_symbol: str, rule: dict, meta: dict, now: datetime) -> None:
    row = SignalEvent(
        asset_symbol=asset_symbol,
        chain_key=None,
        event_type=rule["type"],
        severity=rule["severity"],
        title=f"{asset_symbol} {rule['type'].replace('_', ' ').title()}",
        summary=f"Alert fired: {rule['condition']}",
        old_value=None,
        new_value=None,
        delta=None,
        threshold=rule["condition"],
        timestamp=now,
        metadata_json=json.dumps(meta),
    )
    db.add(row)
    db.commit()


def _dispatch_alert(rule: dict, *, asset_symbol: str, meta: dict) -> None:
    channels = rule.get("channels", ["dashboard"])
    for channel in channels:
        if channel == "webhook":
            _dispatch_webhook(asset_symbol, rule, meta)
        elif channel == "discord":
            _dispatch_discord(asset_symbol, rule, meta)
        elif channel == "telegram":
            _dispatch_telegram(asset_symbol, rule, meta)
        elif channel == "email":
            _dispatch_email(asset_symbol, rule, meta)


def _dispatch_webhook(asset_symbol: str, rule: dict, meta: dict) -> None:
    url = os.getenv("ALERT_WEBHOOK_URL", "")
    if not url:
        return
    try:
        requests.post(url, json={"asset": asset_symbol, "type": rule["type"], "severity": rule["severity"], "meta": meta}, timeout=10)
    except Exception as exc:
        log.warning("webhook_failed", error=str(exc))


def _dispatch_discord(asset_symbol: str, rule: dict, meta: dict) -> None:
    url = os.getenv("ALERT_DISCORD_WEBHOOK", "")
    if not url:
        return
    try:
        requests.post(url, json={"content": f"[{rule['severity'].upper()}] {asset_symbol}: {rule['type']} - {rule['condition']}"}, timeout=10)
    except Exception as exc:
        log.warning("discord_failed", error=str(exc))


def _dispatch_telegram(asset_symbol: str, rule: dict, meta: dict) -> None:
    token = os.getenv("ALERT_TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("ALERT_TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        text = f"[{rule['severity'].upper()}] {asset_symbol}: {rule['type']}\n{rule['condition']}"
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as exc:
        log.warning("telegram_failed", error=str(exc))


def _dispatch_email(asset_symbol: str, rule: dict, meta: dict) -> None:
    log.warning("email_skipped", reason="not_implemented")
