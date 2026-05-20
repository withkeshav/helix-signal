"""
Helix Signal Score (V2.3): transparent, interpretable monitoring signals.

Weights (composite 0-100, higher = more attention needed):
- Peg pressure: 35%
- Supply momentum: 25%
- Chain concentration: 20%
- Data confidence: 20%

Bands: 0-39 Normal, 40-69 Watch, 70-100 Risk
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from utils import utc_normalize, utc_now


def peg_deviation(price: float | None) -> tuple[float, float]:
    """Return (absolute deviation from 1.0, percent deviation)."""
    if price is None or price <= 0:
        return (1.0, 100.0)
    dev = abs(float(price) - 1.0)
    pct = dev * 100.0
    return (dev, pct)


def peg_status_label(price: float | None) -> str:
    dev, _ = peg_deviation(price)
    if dev <= 0.001:
        return "Healthy"
    if dev <= 0.005:
        return "Watch"
    return "Alert"


def depeg_index_score(price: float | None) -> int:
    """
    0-100 peg stress from asset-level price (not chain-specific).
    Maps 0% deviation -> 0, 1% -> ~40, 5%+ -> 100 (capped).
    """
    if price is None:
        return 100
    _, pct = peg_deviation(price)
    # Piecewise: 0-0.1% -> 0-20, 0.1-0.5% -> 20-60, 0.5-1% -> 60-85, above 1% -> 85-100
    if pct <= 0.1:
        return int(min(20, (pct / 0.1) * 20))
    if pct <= 0.5:
        return int(20 + (pct - 0.1) / 0.4 * 40)
    if pct <= 1.0:
        return int(60 + (pct - 0.5) / 0.5 * 25)
    return int(min(100, 85 + min(pct - 1.0, 4.0) * 3.75))


def peg_pressure_component(price: float | None) -> int:
    """0-100 subscore; higher = worse peg."""
    return depeg_index_score(price)


def supply_momentum_component(
    *,
    supply_current: float,
    supply_prev_day: float | None,
    supply_prev_week: float | None,
    supply_prev_month: float | None,
) -> tuple[int, dict[str, Any]]:
    """
    0-100 subscore from directional changes vs baselines.
    """
    scores: list[float] = []
    details: dict[str, Any] = {}

    def pct_change(cur: float, prev: float | None) -> float | None:
        if prev is None or prev == 0:
            return None
        return ((cur - prev) / prev) * 100.0

    d1 = pct_change(supply_current, supply_prev_day)
    d7 = pct_change(supply_current, supply_prev_week)
    d30 = pct_change(supply_current, supply_prev_month)
    details["day_pct"] = d1
    details["week_pct"] = d7
    details["month_pct"] = d30

    for label, val in (("day", d1), ("week", d7), ("month", d30)):
        if val is None:
            continue
        # Large absolute change increases score; cap each window contribution
        mag = min(abs(val), 10.0) / 10.0 * 33.0
        scores.append(mag)

    if not scores:
        return (20, details)

    sub = int(min(100, sum(scores) / len(scores)))
    return (sub, details)


def concentration_component(shares: list[float]) -> tuple[int, dict[str, Any]]:
    """
    Herfindahl-style concentration on chain supply shares (0-1 each).
    Higher concentration -> higher score.
    """
    if not shares:
        return (50, {"top_chain_share_pct": None, "hhi": None})
    s = sum(shares)
    if s <= 0:
        return (50, {"top_chain_share_pct": None, "hhi": None})
    norm = [max(0.0, x / s) for x in shares]
    hhi = sum(x * x for x in norm)
    top = max(norm) if norm else 0.0
    # Map HHI [0.1, 1] roughly to score; top share also nudges
    hhi_score = min(100, max(0, (hhi - 0.1) / 0.9 * 80))
    top_score = min(100, top * 100)
    sub = int(min(100, (hhi_score * 0.65 + top_score * 0.35)))
    return (sub, {"top_chain_share_pct": round(top * 100, 2), "hhi": round(hhi, 4)})


def data_confidence_component(
    *,
    source_ok: bool,
    source_error: str | None,
    age_seconds: float | None,
    refresh_interval_seconds: int,
) -> tuple[int, str, dict[str, Any]]:
    """
    0-100 subscore; higher = lower confidence.
    """
    details: dict[str, Any] = {"source_ok": source_ok, "age_seconds": age_seconds}
    if not source_ok:
        return (90, "Low", details)
    if age_seconds is None:
        return (60, "Medium", details)

    fresh_s = max(900, refresh_interval_seconds * 3)
    warn_s = max(3600, refresh_interval_seconds * 12)
    if age_seconds <= fresh_s:
        return (5, "High", details)
    if age_seconds <= warn_s:
        return (35, "Medium", details)
    return (75, "Low", details)


def composite_band(score: int) -> str:
    if score < 40:
        return "Normal"
    if score < 70:
        return "Watch"
    return "Risk"


def compute_asset_signal(
    *,
    price: float | None,
    supply_current: float,
    supply_prev_day: float | None,
    supply_prev_week: float | None,
    supply_prev_month: float | None,
    chain_shares: list[float],
    source_ok: bool,
    source_error: str | None,
    age_seconds: float | None,
    refresh_interval_seconds: int,
) -> dict[str, Any]:
    peg_s = peg_pressure_component(price)
    mom_s, mom_detail = supply_momentum_component(
        supply_current=supply_current,
        supply_prev_day=supply_prev_day,
        supply_prev_week=supply_prev_week,
        supply_prev_month=supply_prev_month,
    )
    conc_s, conc_detail = concentration_component(chain_shares)
    conf_s, conf_label, conf_detail = data_confidence_component(
        source_ok=source_ok,
        source_error=source_error,
        age_seconds=age_seconds,
        refresh_interval_seconds=refresh_interval_seconds,
    )

    composite = int(
        round(
            peg_s * 0.35
            + mom_s * 0.25
            + conc_s * 0.20
            + conf_s * 0.20
        )
    )
    composite = max(0, min(100, composite))

    return {
        "score": composite,
        "band": composite_band(composite),
        "components": {
            "peg_pressure": {"score": peg_s, "weight": 0.35},
            "supply_momentum": {"score": mom_s, "weight": 0.25, "detail": mom_detail},
            "chain_concentration": {"score": conc_s, "weight": 0.20, "detail": conc_detail},
            "data_confidence": {"score": conf_s, "weight": 0.20, "label": conf_label, "detail": conf_detail},
        },
    }


def compute_freshness(
    *,
    source_status: str,
    last_successful_fetch: datetime | None,
    newest_chain_snapshot: datetime | None,
    refresh_interval_seconds: int,
) -> dict[str, Any]:
    """
    Server-side freshness using UTC-aware timestamps only.

    When ``last_successful_fetch`` is set (successful pipeline completion), age and
    status use that time only so old per-chain ``fetched_at`` labels cannot mark a
    successful refresh as stale. ``newest_chain_snapshot`` is referenced in ``reason``
    for upstream data-age context only.
    """
    lsf = utc_normalize(last_successful_fetch)
    ncs = utc_normalize(newest_chain_snapshot)

    if source_status == "error":
        basis_ts: datetime | None = None
        basis = "none"
        reason = "DefiLlama source status is error; freshness cannot be trusted."
    elif lsf is not None:
        basis_ts = lsf
        basis = "last_successful_fetch"
        reason = "Age measured from last successful source refresh completion (UTC)."
    elif ncs is not None:
        basis_ts = ncs
        basis = "newest_chain_snapshot"
        reason = "No source refresh timestamp; age measured from newest chain snapshot row (UTC)."
    else:
        basis_ts = None
        basis = "none"
        reason = "No freshness basis: missing last successful fetch and chain snapshots."

    now = utc_now()
    age_seconds: float | None = None
    if basis_ts is not None:
        age_seconds = max(0.0, (now - basis_ts).total_seconds())

    fresh_window = max(900.0, float(refresh_interval_seconds) * 3.0)
    warn_window = max(3600.0, float(refresh_interval_seconds) * 12.0)

    if source_status == "error":
        status = "Stale"
    elif basis_ts is None:
        status = "Stale"
    elif age_seconds is not None and age_seconds <= fresh_window:
        status = "Fresh"
        reason = f"{reason} Within fresh window."
    elif age_seconds is not None and age_seconds <= warn_window:
        status = "Aging"
        reason = f"{reason} Past fresh window but within aging window."
    else:
        status = "Stale"
        reason = f"{reason} Past aging window (data refresh is overdue)."

    if lsf and ncs and basis == "last_successful_fetch":
        snap_age = max(0.0, (now - ncs).total_seconds())
        reason = (
            f"{reason} Newest chain snapshot row is ~{snap_age / 60.0:.1f} min old "
            "(reference only)."
        )

    age_minutes = round(age_seconds / 60.0, 2) if age_seconds is not None else None

    return {
        "status": status,
        "age_seconds": age_seconds,
        "age_minutes": age_minutes,
        "basis_timestamp": basis_ts.isoformat().replace("+00:00", "Z") if basis_ts else None,
        "basis": basis,
        "fresh_window_seconds": int(fresh_window),
        "warning_window_seconds": int(warn_window),
        "fresh_window_minutes": round(fresh_window / 60.0, 2),
        "stale_window_minutes": round(warn_window / 60.0, 2),
        "reason": reason,
    }


def chain_supply_momentum(
    *,
    supply_current: float | None,
    supply_prev_day: float | None,
    supply_prev_week: float | None,
    supply_prev_month: float | None,
) -> dict[str, Any]:
    def label(pct: float | None) -> str:
        if pct is None:
            return "Unknown"
        if abs(pct) < 0.05:
            return "Stable"
        return "Expansion" if pct > 0 else "Contraction"

    def pct(cur: float | None, prev: float | None) -> float | None:
        if cur is None or prev is None or prev == 0:
            return None
        return ((cur - prev) / prev) * 100.0

    cur = supply_current or 0.0
    d = pct(cur, supply_prev_day)
    w = pct(cur, supply_prev_week)
    m = pct(cur, supply_prev_month)
    return {
        "day_pct": d,
        "week_pct": w,
        "month_pct": m,
        "day_label": label(d),
        "week_label": label(w),
        "month_label": label(m),
    }


def chain_row_signal(
    *,
    chain_share_pct: float | None,
    peg_price: float | None,
    momentum_score_hint: int,
) -> dict[str, Any]:
    """Per-chain composite label (simplified vs asset-level)."""
    score = 0
    if chain_share_pct is not None and chain_share_pct > 35:
        score += 35
    if peg_price is not None:
        score += int(peg_pressure_component(peg_price) * 0.35)
    score += int(min(40, momentum_score_hint * 0.4))
    score = max(0, min(100, score))
    return {"score": score, "band": composite_band(score)}


def chain_data_confidence(
    *,
    source_ok: bool,
    chain_snapshot_age_seconds: float | None,
    refresh_interval_seconds: int,
) -> dict[str, Any]:
    s, label, _ = data_confidence_component(
        source_ok=source_ok,
        source_error=None,
        age_seconds=chain_snapshot_age_seconds,
        refresh_interval_seconds=refresh_interval_seconds,
    )
    return {"score": s, "label": label, "reason": "source_and_snapshot_recency"}

