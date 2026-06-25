"""Composite scoring — computes risk score from raw or pre-computed components."""

from typing import Dict, Any
from datetime import datetime, timezone

from signal_engine.components.peg_analysis import depeg_index_score
from signal_engine.components.concentration import concentration_component

# ASSET-LEVEL SIGNAL SCORE WEIGHTS (5-component architecture)
# depeg_index    0.35  (peg deviation pressure)
# concentration  0.20  (chain supply concentration)
# velocity       0.15  (supply momentum)
# liquidity      0.10  (DEX depth / slippage)
# age_penalty    0.20  (data staleness)
def liquidity_depth_score(slippage_100k_bps: float = 0.0) -> int:
    """Score liquidity depth from estimated 100k USD trade slippage (bps). Lower slippage = lower risk."""
    bps = abs(float(slippage_100k_bps or 0))
    if bps <= 5:
        return 0
    if bps <= 15:
        return 25
    if bps <= 40:
        return 50
    if bps <= 100:
        return 75
    return 100


def _age_penalty_score(age_seconds: float) -> tuple[int, dict[str, Any]]:
    """4-tier freshness penalty model."""
    age = float(age_seconds or 0)
    if age < 3600:
        score = 0
        tier = "fresh"
    elif age < 7200:
        score = 10
        tier = "aging"
    elif age < 86400:
        score = 15
        tier = "stale"
    else:
        score = 20
        tier = "very_stale"
    return score, {"age_seconds": age, "tier": tier}


def compute_risk_score(**kwargs) -> Dict[str, Any]:
    depeg_score = kwargs.get("depeg_index")
    if depeg_score is None:
        price = kwargs.get("price")
        depeg_score = depeg_index_score(price)

    concentration_score = kwargs.get("concentration_score")
    conc_detail = {}
    if concentration_score is None:
        chain_shares = kwargs.get("chain_shares", [])
        concentration_score, conc_detail = concentration_component(
            chain_shares,
            top3_dex_pool_share=kwargs.get("top3_dex_pool_share"),
        )
    elif "top_chain_share_pct" in kwargs:
        conc_detail = {"top_chain_share_pct": kwargs["top_chain_share_pct"]}

    supply_velocity_1h = kwargs.get("supply_velocity_1h", 0) or 0
    supply_velocity_4h = kwargs.get("supply_velocity_4h", 0) or 0
    source_ok = kwargs.get("source_ok", True)
    age_seconds = kwargs.get("age_seconds", 0) or 0

    velocity_component = 0
    vel_detail = {}
    # Contracting supply (negative velocity) contributes equally via abs()
    if supply_velocity_1h != 0:
        velocity_component += min(25, abs(float(supply_velocity_1h)) * 5)
    if supply_velocity_4h != 0:
        velocity_component += min(15, abs(float(supply_velocity_4h)) * 3)
    vel_detail["supply_velocity_1h"] = supply_velocity_1h
    vel_detail["supply_velocity_4h"] = supply_velocity_4h
    vel_detail["supply_accel_1h"] = kwargs.get("supply_accel_1h", 0) or 0

    liq_score = kwargs.get("liquidity_depth_score")
    if liq_score is None:
        liq_score = liquidity_depth_score(kwargs.get("slippage_100k_bps", 0) or 0)

    age_penalty, age_detail = _age_penalty_score(age_seconds)

    base_score = (
        depeg_score * 0.35
        + concentration_score * 0.20
        + velocity_component * 0.15
        + liq_score * 0.10
        + age_penalty * 0.20
    )

    final_score = max(0, min(100, base_score))
    band = _score_to_band(final_score)

    components = {
        "depeg_index": {
            "score": int(depeg_score),
            "weight": 0.35,
            "detail": {
                "price": kwargs.get("price"),
                "deviation_pct": kwargs.get("price") and round(abs(kwargs["price"] - 1.0) * 100, 4),
            },
        },
        "concentration": {"score": int(concentration_score), "weight": 0.20, "detail": conc_detail},
        "velocity": {"score": int(velocity_component), "weight": 0.15, "detail": vel_detail},
        "liquidity_depth": {
            "score": int(liq_score),
            "weight": 0.10,
            "detail": {"slippage_100k_bps": kwargs.get("slippage_100k_bps", 0)},
        },
        "age_penalty": {"score": int(age_penalty), "weight": 0.20, "detail": age_detail},
        "source_health": "OK" if source_ok else "DEGRADED",
    }

    return {
        "score": int(final_score),
        "band": band,
        "components": components,
    }


def _score_to_band(score: float) -> str:
    if score <= 20:
        return "Normal"
    if score <= 60:
        return "Watch"
    return "Alert"


def compute_freshness(
    source_status: str,
    last_successful_fetch: datetime | None,
    newest_chain_snapshot: datetime | None,
    refresh_interval_seconds: int,
) -> Dict[str, Any]:
    basis_timestamp = newest_chain_snapshot or last_successful_fetch
    basis = "chain_snapshot" if newest_chain_snapshot else "source_fetch"

    if basis_timestamp is None:
        return {
            "status": "unknown",
            "age_seconds": None,
            "age_minutes": None,
            "basis_timestamp": None,
            "basis": basis,
            "fresh_window_seconds": refresh_interval_seconds,
            "warning_window_seconds": refresh_interval_seconds * 3,
            "fresh_window_minutes": refresh_interval_seconds / 60,
            "stale_window_minutes": (refresh_interval_seconds * 6) / 60,
            "reason": "No timestamp available",
        }

    now = datetime.now(timezone.utc)
    age_s = (now - basis_timestamp).total_seconds()
    age_m = age_s / 60

    fresh_window = refresh_interval_seconds
    warning_window = refresh_interval_seconds * 3
    stale_window = refresh_interval_seconds * 6

    if age_s <= fresh_window:
        status = "fresh"
        reason = "Recently updated"
    elif age_s <= warning_window:
        status = "aging"
        reason = "Last update was recent but not current"
    elif age_s <= stale_window:
        status = "stale"
        reason = "Data is getting old, updates needed"
    else:
        status = "very stale"
        reason = "Data is very old, potential issues"

    return {
        "status": status,
        "age_seconds": round(age_s, 1),
        "age_minutes": round(age_m, 1),
        "basis_timestamp": basis_timestamp.isoformat(),
        "basis": basis,
        "fresh_window_seconds": fresh_window,
        "warning_window_seconds": warning_window,
        "fresh_window_minutes": fresh_window / 60,
        "stale_window_minutes": stale_window / 60,
        "reason": reason,
    }
