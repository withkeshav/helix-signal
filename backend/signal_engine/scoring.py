from __future__ import annotations

from datetime import datetime
from typing import Any

from utils import utc_normalize, utc_now


def peg_deviation(price: float | None) -> tuple[float, float]:
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
    if price is None:
        return 100
    _, pct = peg_deviation(price)
    if pct <= 0.1:
        return int(min(20, (pct / 0.1) * 20))
    if pct <= 0.5:
        return int(20 + (pct - 0.1) / 0.4 * 40)
    if pct <= 1.0:
        return int(60 + (pct - 0.5) / 0.5 * 25)
    return int(min(100, 85 + min(pct - 1.0, 4.0) * 3.75))


def composite_band(score: int) -> str:
    if score < 40:
        return "Normal"
    if score < 70:
        return "Watch"
    return "Risk"


def peg_stability_component(
    *,
    price: float | None,
    depeg_duration_minutes: int = 0,
    depeg_frequency_7d: int = 0,
    venue_divergence_bps: float = 0.0,
) -> tuple[int, dict[str, Any]]:
    score = depeg_index_score(price)
    if depeg_duration_minutes > 30:
        score = min(100, score + 10)
    if depeg_frequency_7d > 5:
        score = min(100, score + 5)
    if venue_divergence_bps > 10:
        score = min(100, score + int(venue_divergence_bps / 10))
    return (score, {"depeg_index": score, "depeg_duration_min": depeg_duration_minutes, "depeg_freq_7d": depeg_frequency_7d, "venue_divergence_bps": venue_divergence_bps})


def liquidity_depth_component(
    *,
    slippage_10k_bps: float = 0.0,
    slippage_100k_bps: float = 0.0,
    top3_pool_share_pct: float | None = None,
    tvl_change_24h_pct: float | None = None,
) -> tuple[int, dict[str, Any]]:
    score = 0
    if slippage_10k_bps > 50:
        score += 25
    elif slippage_10k_bps > 10:
        score += 15
    elif slippage_10k_bps > 5:
        score += 5
    if slippage_100k_bps > 200:
        score += 30
    elif slippage_100k_bps > 50:
        score += 20
    elif slippage_100k_bps > 10:
        score += 10
    if top3_pool_share_pct is not None:
        if top3_pool_share_pct > 80:
            score += 25
        elif top3_pool_share_pct > 60:
            score += 15
        elif top3_pool_share_pct > 40:
            score += 5
    if tvl_change_24h_pct is not None and abs(tvl_change_24h_pct) > 25:
        score += 20
    elif tvl_change_24h_pct is not None and abs(tvl_change_24h_pct) > 10:
        score += 10
    score = min(100, score)
    return (score, {"slippage_10k": slippage_10k_bps, "slippage_100k": slippage_100k_bps, "top3_pool_share": top3_pool_share_pct, "tvl_change_24h_pct": tvl_change_24h_pct})


def supply_stability_component(
    *,
    supply_change_24h_pct: float | None = None,
    supply_change_7d_pct: float | None = None,
    bridged_share_pct: float | None = None,
    mint_burn_anomaly: bool = False,
) -> tuple[int, dict[str, Any]]:
    score = 0
    for chg in (supply_change_24h_pct, supply_change_7d_pct):
        if chg is None:
            continue
        if abs(chg) > 10:
            score += 35
        elif abs(chg) > 5:
            score += 20
        elif abs(chg) > 2:
            score += 10
    if bridged_share_pct is not None and bridged_share_pct > 50:
        score += 15
    elif bridged_share_pct is not None and bridged_share_pct > 30:
        score += 5
    if mint_burn_anomaly:
        score += 35
    return (min(100, score), {"supply_change_24h_pct": supply_change_24h_pct, "supply_change_7d_pct": supply_change_7d_pct, "bridged_share_pct": bridged_share_pct, "mint_burn_anomaly": mint_burn_anomaly})


def concentration_component(shares: list[float], top3_dex_pool_share: float | None = None) -> tuple[int, dict[str, Any]]:
    if not shares:
        return (50, {"top_chain_share_pct": None, "hhi": None, "top3_dex_share": top3_dex_pool_share})
    s = sum(shares)
    if s <= 0:
        return (50, {"top_chain_share_pct": None, "hhi": None, "top3_dex_share": top3_dex_pool_share})
    norm = [max(0.0, x / s) for x in shares]
    hhi = sum(x * x for x in norm)
    top = max(norm) if norm else 0.0
    hhi_score = min(100, max(0, (hhi - 0.1) / 0.9 * 80))
    top_score = min(100, top * 100)
    score = int(min(100, (hhi_score * 0.5 + top_score * 0.25)))
    if top3_dex_pool_share is not None and top3_dex_pool_share > 80:
        score = min(100, score + 25)
    elif top3_dex_pool_share is not None and top3_dex_pool_share > 60:
        score = min(100, score + 10)
    return (score, {"top_chain_share_pct": round(top * 100, 2), "hhi": round(hhi, 4), "top3_dex_share": top3_dex_pool_share})


def observability_component(
    *,
    source_ok: bool,
    source_error: str | None,
    age_seconds: float | None,
    refresh_interval_seconds: int,
    cross_source_agreement: int = 0,
    attestation_age_days: float | None = None,
) -> tuple[int, str, dict[str, Any]]:
    details: dict[str, Any] = {"source_ok": source_ok, "age_seconds": age_seconds, "cross_source_agreement": cross_source_agreement}
    if not source_ok:
        return (90, "Low", details)
    if age_seconds is None:
        return (60, "Medium", details)
    fresh_s = max(900, refresh_interval_seconds * 3)
    warn_s = max(3600, refresh_interval_seconds * 12)
    if age_seconds <= fresh_s:
        score = 5
        label = "High"
    elif age_seconds <= warn_s:
        score = 35
        label = "Medium"
    else:
        score = 75
        label = "Low"
    if cross_source_agreement < 2:
        score = min(100, score + 20)
    if attestation_age_days is not None and attestation_age_days > 180:
        score = min(100, score + 10)
    return (score, label, details)


def compute_risk_score(
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
    slippage_10k_bps: float = 0.0,
    slippage_100k_bps: float = 0.0,
    top3_pool_share_pct: float | None = None,
    tvl_change_24h_pct: float | None = None,
    depeg_duration_minutes: int = 0,
    depeg_frequency_7d: int = 0,
    venue_divergence_bps: float = 0.0,
    bridged_share_pct: float | None = None,
    mint_burn_anomaly: bool = False,
    top3_dex_pool_share: float | None = None,
    cross_source_agreement: int = 0,
    attestation_age_days: float | None = None,
    cross_source_discrepancy_pct: float = 0.0,
) -> dict[str, Any]:
    peg_s, peg_d = peg_stability_component(price=price, depeg_duration_minutes=depeg_duration_minutes, depeg_frequency_7d=depeg_frequency_7d, venue_divergence_bps=venue_divergence_bps)
    liq_s, liq_d = liquidity_depth_component(slippage_10k_bps=slippage_10k_bps, slippage_100k_bps=slippage_100k_bps, top3_pool_share_pct=top3_pool_share_pct, tvl_change_24h_pct=tvl_change_24h_pct)
    sup_s, sup_d = supply_stability_component(
        supply_change_24h_pct=((supply_current - (supply_prev_day or 0)) / (supply_prev_day or 1) * 100) if supply_prev_day and supply_prev_day > 0 else None,
        supply_change_7d_pct=((supply_current - (supply_prev_week or 0)) / (supply_prev_week or 1) * 100) if supply_prev_week and supply_prev_week > 0 else None,
        bridged_share_pct=bridged_share_pct,
        mint_burn_anomaly=mint_burn_anomaly,
    )
    conc_s, conc_d = concentration_component(chain_shares, top3_dex_pool_share=top3_dex_pool_share)
    obs_s, obs_label, obs_d = observability_component(
        source_ok=source_ok,
        source_error=source_error,
        age_seconds=age_seconds,
        refresh_interval_seconds=refresh_interval_seconds,
        cross_source_agreement=cross_source_agreement,
        attestation_age_days=attestation_age_days,
    )

    composite = int(round(peg_s * 0.35 + liq_s * 0.25 + sup_s * 0.15 + conc_s * 0.15 + obs_s * 0.10))
    composite = max(0, min(100, composite))

    dev_abs, _ = peg_deviation(price)
    depeg_bps = dev_abs * 10000

    if depeg_bps > 200 and depeg_duration_minutes >= 30:
        composite = max(composite, 70)
    if age_seconds is not None and age_seconds > max(3600, refresh_interval_seconds * 12) * 3:
        obs_label = "Low"
    if cross_source_discrepancy_pct > 1.0:
        composite = min(100, composite + 10)

    return {
        "score": composite,
        "band": composite_band(composite),
        "components": {
            "peg_stability": {"score": peg_s, "weight": 0.35, "detail": peg_d},
            "liquidity_depth": {"score": liq_s, "weight": 0.25, "detail": liq_d},
            "supply_stability": {"score": sup_s, "weight": 0.15, "detail": sup_d},
            "concentration": {"score": conc_s, "weight": 0.15, "detail": conc_d},
            "observability": {"score": obs_s, "weight": 0.10, "label": obs_label, "detail": obs_d},
        },
    }


def compute_freshness(
    *,
    source_status: str,
    last_successful_fetch: datetime | None,
    newest_chain_snapshot: datetime | None,
    refresh_interval_seconds: int,
) -> dict[str, Any]:
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
        reason = f"{reason} Newest chain snapshot row is ~{snap_age / 60.0:.1f} min old (reference only)."

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
    return {"day_pct": d, "week_pct": w, "month_pct": m, "day_label": label(d), "week_label": label(w), "month_label": label(m)}


def chain_row_signal(
    *,
    chain_share_pct: float | None,
    peg_price: float | None,
    momentum_score_hint: int,
) -> dict[str, Any]:
    score = 0
    if chain_share_pct is not None and chain_share_pct > 35:
        score += 35
    if peg_price is not None:
        score += int(depeg_index_score(peg_price) * 0.35)
    score += int(min(40, momentum_score_hint * 0.4))
    score = max(0, min(100, score))
    return {"score": score, "band": composite_band(score)}


def supply_momentum_component(
    *,
    supply_current: float,
    supply_prev_day: float | None,
    supply_prev_week: float | None,
    supply_prev_month: float | None,
) -> tuple[int, dict[str, Any]]:
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

    for val in (d1, d7, d30):
        if val is None:
            continue
        mag = min(abs(val), 10.0) / 10.0 * 33.0
        scores.append(mag)

    if not scores:
        return (20, details)
    sub = int(min(100, sum(scores) / len(scores)))
    return (sub, details)


def chain_data_confidence(
    *,
    source_ok: bool,
    chain_snapshot_age_seconds: float | None,
    refresh_interval_seconds: int,
) -> dict[str, Any]:
    s, label, _ = observability_component(
        source_ok=source_ok,
        source_error=None,
        age_seconds=chain_snapshot_age_seconds,
        refresh_interval_seconds=refresh_interval_seconds,
    )
    return {"score": s, "label": label, "reason": "source_and_snapshot_recency"}
