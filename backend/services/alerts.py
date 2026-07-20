"""Alert rule engine with a callable registry instead of fragile string matching."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable

import smtplib
from email.mime.text import MIMEText

from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SignalEvent, SourceStatus
from structlog import get_logger

log = get_logger(__name__)

ALERTS_CONFIG_PATH = Path(
    os.getenv(
        "HELIX_ALERTS_CONFIG",
        str(Path(__file__).resolve().parents[2] / "config" / "alerts.json"),
    )
)

# In-memory condition-first-seen tracker for persistence_minutes enforcement
_CONDTION_PERSISTENCE: dict[str, datetime] = {}


# --- Callable evaluator registry ---
# Maps condition patterns to (evaluator_fn, context_extractor_fn)
_RULE_EVALUATORS: dict[str, Callable[[dict[str, Any], dict[str, Any]], bool]] = {}


def _register_condition(pattern: str):
    """Decorator that registers a callable evaluator for a condition key."""
    def decorator(fn: Callable) -> Callable:
        _RULE_EVALUATORS[pattern] = fn
        return fn
    return decorator


@_register_condition("depeg_bps >")
def _eval_depeg_bps(bundle: dict[str, Any], rule: dict[str, Any]) -> bool:
    threshold = _extract_threshold(rule["condition"], "depeg_bps >")
    price = bundle.get("price")
    if not price:
        return False
    depeg_bps = abs(price - 1.0) * 10000
    if depeg_bps > threshold:
        bundle["_meta"]["depeg_bps"] = depeg_bps
        return True
    return False


@_register_condition("supply_change_7d <")
def _eval_supply_contraction(bundle: dict[str, Any], rule: dict[str, Any]) -> bool:
    threshold = _extract_threshold(rule["condition"], "supply_change_7d <")
    change = bundle.get("supply_change_7d_pct") or bundle.get("supply_change_7d")
    if change is not None and change < threshold:
        return True
    return False


@_register_condition("freshness_age_minutes >")
def _eval_freshness(bundle: dict[str, Any], rule: dict[str, Any]) -> bool:
    threshold = _extract_threshold(rule["condition"], "freshness_age_minutes >")
    age = bundle.get("freshness_age_seconds")
    if age is not None and age > threshold * 60:
        bundle["_meta"]["age_minutes"] = round(age / 60, 1)
        return True
    return False


@_register_condition("source_status = error")
def _eval_source_error(bundle: dict[str, Any], rule: dict[str, Any]) -> bool:
    sources = bundle.get("_sources", [])
    for s in sources:
        try:
            if s.status == "error":
                bundle["_meta"]["source"] = s.source_name
                return True
        except Exception:
            continue
    return False


@_register_condition("slippage_100k >")
def _eval_slippage(bundle: dict[str, Any], rule: dict[str, Any]) -> bool:
    med_7d = bundle.get("slippage_7d_median")
    cur = bundle.get("slippage_100k")
    if cur is not None and med_7d is not None and med_7d > 0:
        return cur > 2 * med_7d
    return False


@_register_condition("source_status = error for")
def _eval_source_error_persistent(bundle: dict[str, Any], rule: dict[str, Any]) -> bool:
    sources = bundle.get("_sources", [])
    for s in sources:
        try:
            if s.status == "error" and hasattr(s, "last_attempted_fetch") and s.last_attempted_fetch:
                mins = (datetime.now(timezone.utc) - s.last_attempted_fetch).total_seconds() / 60
                if mins > 5:
                    bundle["_meta"]["source"] = s.source_name
                    bundle["_meta"]["error_minutes"] = round(mins, 1)
                    return True
        except Exception:
            continue
    return False


@_register_condition("source transitions error")
def _eval_source_recovered(bundle: dict[str, Any], rule: dict[str, Any]) -> bool:
    sources = bundle.get("_sources", [])
    for s in sources:
        try:
            if s.status == "ok" and getattr(s, "previous_status", None) == "error":
                bundle["_meta"]["source"] = s.source_name
                return True
        except Exception:
            continue
    return False


@_register_condition("top3_pool_share >")
def _eval_concentration(bundle: dict[str, Any], rule: dict[str, Any]) -> bool:
    threshold = _extract_threshold(rule["condition"], "top3_pool_share >")
    share = bundle.get("top3_pool_share_pct")
    if share is not None and share > threshold:
        return True
    return False


@_register_condition("supply_age_hours >")
def _eval_supply_age(bundle: dict[str, Any], rule: dict[str, Any]) -> bool:
    threshold = _extract_threshold(rule["condition"], "supply_age_hours >")
    age = bundle.get("supply_age_hours")
    if age is not None and age > threshold:
        return True
    return False


@_register_condition("rule_10_yield_apy_collapse")
def _eval_yield_apy_collapse(bundle: dict[str, Any], rule: dict[str, Any]) -> bool:
    apy_current = bundle.get("apy_current")
    apy_7d_ago = bundle.get("apy_7d_ago")
    if apy_current is not None and apy_7d_ago is not None and apy_7d_ago > 0:
        drop_pct = (apy_7d_ago - apy_current) / apy_7d_ago
        if drop_pct > 0.30:
            bundle["_meta"]["apy_drop_pct"] = round(drop_pct * 100, 1)
            return True
    return False


@_register_condition("rule_11_funding_rate_negative")
def _eval_funding_rate_negative(bundle: dict[str, Any], rule: dict[str, Any]) -> bool:
    bundle["_meta"]["funding_rate_7d_negative_hours"] = funding_hours = bundle.get("funding_rate_7d_negative_hours", 0)
    return funding_hours >= 8


@_register_condition("rule_12_insurance_coverage")
def _eval_insurance_coverage(bundle: dict[str, Any], rule: dict[str, Any]) -> bool:
    coverage = bundle.get("insurance_fund_coverage")
    if coverage is not None and coverage < 0.02:
        bundle["_meta"]["insurance_fund_coverage"] = coverage
        return True
    return False


@_register_condition("rule_13_collateral_warning")
def _eval_collateral_warning(bundle: dict[str, Any], rule: dict[str, Any]) -> bool:
    headroom = bundle.get("collateral_headroom_pct")
    if headroom is not None and headroom < 15:
        bundle["_meta"]["collateral_headroom_pct"] = headroom
        return True
    return False


@_register_condition("rule_14_liquidation_cascade")
def _eval_liquidation_cascade(bundle: dict[str, Any], rule: dict[str, Any]) -> bool:
    queue = bundle.get("liquidation_queue_usd")
    if queue is not None and queue > 50_000_000:
        bundle["_meta"]["liquidation_queue_usd"] = queue
        return True
    return False


@_register_condition("rule_15_reserve_coverage")
def _eval_reserve_coverage(bundle: dict[str, Any], rule: dict[str, Any]) -> bool:
    ratio = bundle.get("coverage_ratio")
    if ratio is not None and ratio < 1.02:
        bundle["_meta"]["coverage_ratio"] = ratio
        return True
    return False


@_register_condition("rule_16_attestation_stale")
def _eval_attestation_stale(bundle: dict[str, Any], rule: dict[str, Any]) -> bool:
    lag = bundle.get("attestation_lag_days")
    if lag is not None and lag > 30:
        bundle["_meta"]["attestation_lag_days"] = lag
        return True
    return False


@_register_condition("rule_17_osint_critical")
def _eval_osint_critical(bundle: dict[str, Any], rule: dict[str, Any]) -> bool:
    event_type = bundle.get("osint_event_type", "")
    source_authority = bundle.get("osint_source_authority", 0)
    if event_type in ("DEPEG_CONFIRMED", "PROTOCOL_EXPLOIT", "ISSUER_FREEZE", "SANCTIONS_ACTION") and source_authority >= 0.70:
        bundle["_meta"]["osint_event_type"] = event_type
        bundle["_meta"]["osint_source_authority"] = source_authority
        return True
    return False


@_register_condition("rule_22_issuer_freeze")
def _eval_issuer_freeze(bundle: dict[str, Any], rule: dict[str, Any]) -> bool:
    frozen_usd = bundle.get("frozen_balance_usd")
    if frozen_usd is not None and frozen_usd > 1_000_000:
        bundle["_meta"]["frozen_balance_usd"] = frozen_usd
        bundle["_meta"]["frozen_address"] = bundle.get("frozen_address", "")
        return True
    return False


def _extract_threshold(condition: str, prefix: str) -> float:
    """Extract numeric threshold from a condition string like 'depeg_bps > 50'."""
    try:
        return float(condition.replace(prefix, "").strip())
    except (ValueError, TypeError):
        return 0.0


def _match_condition(condition: str) -> Callable | None:
    """Find the best matching evaluator for a condition string (longest prefix wins)."""
    matched: tuple[int, Callable] | None = None
    for pattern, fn in _RULE_EVALUATORS.items():
        if condition.startswith(pattern):
            if matched is None or len(pattern) > matched[0]:
                matched = (len(pattern), fn)
    return matched[1] if matched else None


def load_all_alert_rules() -> list[dict]:
    with ALERTS_CONFIG_PATH.open("r", encoding="utf-8") as f:
        rules = json.load(f)
    return [r for r in rules if isinstance(r, dict)]


def load_alert_rules() -> list[dict]:
    return [r for r in load_all_alert_rules() if r.get("enabled", False)]


def save_alert_rules(rules: list[dict]) -> None:
    if not isinstance(rules, list):
        raise ValueError("rules must be a list")
    cleaned: list[dict] = []
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("each rule must be an object")
        if "condition" not in rule or "type" not in rule:
            raise ValueError("each rule requires type and condition")
        cleaned.append(rule)
    ALERTS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ALERTS_CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2)
        f.write("\n")


def evaluate_alerts(db: Session, *, bundle: dict[str, Any], asset_symbol: str, now: datetime) -> list[dict[str, Any]]:
    rules = load_alert_rules()
    fired: list[dict[str, Any]] = []
    sources_orm = db.execute(select(SourceStatus).order_by(SourceStatus.id.asc())).scalars().all()
    bundle["_meta"] = {}
    bundle["_sources"] = sources_orm

    for rule in rules:
        cond = rule["condition"]
        evaluator = _match_condition(cond)
        if evaluator is None:
            log.warning("alert_no_evaluator", condition=cond)
            continue
        meta = bundle["_meta"]
        matched = evaluator(bundle, rule)

        persist_key = f"{asset_symbol}:{cond}"
        persist_min = rule.get("persistence_minutes", 0)

        if matched:
            if persist_min > 0 and persist_key not in _CONDTION_PERSISTENCE:
                _CONDTION_PERSISTENCE[persist_key] = now
                continue
            if persist_min > 0:
                elapsed = (now - _CONDTION_PERSISTENCE[persist_key]).total_seconds() / 60
                if elapsed < persist_min:
                    continue
            dedup_key = f"{asset_symbol}:{rule['type']}:{rule['severity']}"
            if not _recently_fired(db, dedup_key, rule.get("cooldown_minutes", 60), now):
                _log_alert_fire(db, asset_symbol=asset_symbol, rule=rule, meta=dict(meta), now=now, dedup_key=dedup_key)
                _dispatch_alert(rule, asset_symbol=asset_symbol, meta=dict(meta), db=db)
                fired.append({"type": rule["type"], "severity": rule["severity"], "asset": asset_symbol, "meta": dict(meta)})
        else:
            _CONDTION_PERSISTENCE.pop(persist_key, None)
    return fired


def _recently_fired(db: Session, dedup_key: str, cooldown_minutes: int, now: datetime) -> bool:
    if cooldown_minutes <= 0:
        return False
    cutoff = now - timedelta(minutes=cooldown_minutes)
    existing = db.execute(
        select(SignalEvent).where(
            SignalEvent.event_type == dedup_key,
            SignalEvent.timestamp >= cutoff,
        )
    ).scalars().first()
    return existing is not None


def _log_alert_fire(db: Session, *, asset_symbol: str, rule: dict, meta: dict, now: datetime, dedup_key: str = "") -> None:
    row = SignalEvent(
        asset_symbol=asset_symbol,
        chain_key=None,
        event_type=dedup_key or f"{asset_symbol}:{rule['type']}:{rule['severity']}",
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
    db.flush()


def _dispatch_alert(rule: dict, *, asset_symbol: str, meta: dict, db: Session | None = None) -> None:
    channels = rule.get("channels", ["dashboard"])
    for channel in channels:
        if channel == "email":
            _dispatch_email(asset_symbol, rule, meta, db)


def _dispatch_email(asset_symbol: str, rule: dict, meta: dict, db: Session | None = None) -> None:
    from providers.settings import get_setting
    if not get_setting("alert_email_enabled", db):
        return
    smtp_host = get_setting("alert_smtp_host", db) or ""
    smtp_port = int(get_setting("alert_smtp_port", db) or "587")
    smtp_user = get_setting("alert_smtp_user", db) or ""
    smtp_pass = get_setting("alert_smtp_pass", db) or ""
    mail_to = get_setting("alert_email_to", db) or ""
    mail_from = (get_setting("alert_email_from", db) or "").strip() or smtp_user
    if not smtp_host or not smtp_user or not smtp_pass or not mail_to:
        log.warning("email_skipped", reason="missing_smtp_config")
        return
    try:
        msg = MIMEText(
            f"Helix Signal Alert\n\n"
            f"Asset: {asset_symbol}\n"
            f"Type: {rule['type']}\n"
            f"Severity: {rule['severity']}\n"
            f"Condition: {rule['condition']}\n"
            f"Meta: {json.dumps(meta, indent=2)}\n",
        )
        msg["Subject"] = f"[Helix Signal] {rule['severity'].upper()} - {asset_symbol} {rule['type']}"
        msg["From"] = mail_from
        msg["To"] = mail_to
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        log.info("email_sent", asset=asset_symbol, to=mail_to)
    except Exception as exc:
        log.warning("email_failed", exc_info=True)
