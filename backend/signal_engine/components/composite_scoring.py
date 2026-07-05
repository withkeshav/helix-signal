"""Composite scoring — computes risk score from raw or pre-computed components."""

from typing import Dict, Any
from datetime import datetime, timezone

from signal_engine.components.peg_analysis import depeg_index_score
from signal_engine.components.concentration import concentration_component

# ASSET-LEVEL SIGNAL SCORE WEIGHTS (5-component architecture)
# Base (stable regime) — depeg 0.35, concentration 0.20, velocity 0.15, liquidity 0.10, age 0.20
_REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    "stable": {"depeg": 0.35, "concentration": 0.20, "velocity": 0.15, "liquidity": 0.10, "age_penalty": 0.20},
    "volatile": {"depeg": 0.40, "concentration": 0.18, "velocity": 0.15, "liquidity": 0.10, "age_penalty": 0.17},
    "alert": {"depeg": 0.45, "concentration": 0.17, "velocity": 0.14, "liquidity": 0.09, "age_penalty": 0.15},
    "crisis": {"depeg": 0.50, "concentration": 0.15, "velocity": 0.13, "liquidity": 0.08, "age_penalty": 0.14},
}

# V4 type-specific weight matrices (replaces V3 single weight set per asset type)
V4_WEIGHT_MATRICES: dict[str, dict[str, float]] = {
    "fiat_backed": {
        "depeg_component": 0.20, "reserve_coverage": 0.30,
        "attestation_freshness": 0.15, "regulatory_compliance": 0.15,
        "concentration_component": 0.10, "liquidity_depth": 0.10,
    },
    "crypto_collateralized": {
        "collateral_health": 0.35, "depeg_component": 0.20,
        "concentration_component": 0.15, "velocity_component": 0.15,
        "liquidity_depth": 0.15,
    },
    "yield_bearing_delta_neutral": {
        "funding_rate_health": 0.30, "insurance_fund_coverage": 0.20,
        "cex_counterparty_health": 0.20, "depeg_component": 0.15,
        "concentration_component": 0.15,
    },
    "yield_bearing_tbill": {
        "reserve_coverage": 0.35, "attestation_freshness": 0.25,
        "redemption_liquidity": 0.20, "depeg_component": 0.20,
    },
    "yield_bearing_defi_lending": {
        "yield_sustainability": 0.30, "underlying_protocol_health": 0.25,
        "depeg_component": 0.20, "concentration_component": 0.15,
        "liquidity_depth": 0.10,
    },
    "algorithmic": {
        "collateral_health": 0.25, "yield_sustainability": 0.25,
        "depeg_component": 0.20, "mint_burn_ratio": 0.20,
        "liquidity_depth": 0.10,
    },
}

# External signal map: (helix_event_type, helix_severity, risk_score_amplifier)
# Used by apply_osint_amplifier() below. Canonical source lives in services/osint.py.
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


def _infer_regime(depeg_score: float, preliminary_score: float) -> str:
    if preliminary_score >= 80 or depeg_score >= 85:
        return "crisis"
    if preliminary_score >= 61 or depeg_score >= 60:
        return "alert"
    if preliminary_score >= 40 or depeg_score >= 40:
        return "volatile"
    return "stable"


def _weights_for_regime(regime: str | None) -> dict[str, float]:
    return _REGIME_WEIGHTS.get((regime or "stable").lower(), _REGIME_WEIGHTS["stable"])
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


def _onchain_risk_score(**kwargs: Any) -> tuple[int, dict[str, Any]]:
    """Additive on-chain overlay (aligned with DEWS tier-2 signals). Max +15 points."""
    whale_out = float(kwargs.get("whale_net_outflow_usd") or 0)
    whale_alert = bool(kwargs.get("whale_alert"))
    top10 = float(kwargs.get("top10_holder_share_pct") or 0)
    mint_burn = float(kwargs.get("net_mint_burn_usd_24h") or 0)
    if not (whale_alert or whale_out or top10 or mint_burn):
        return 0, {"available": False}

    score = 0.0
    detail: dict[str, Any] = {"available": True}
    if whale_alert or whale_out >= 5_000_000:
        score += min(8.0, whale_out / 1_000_000)
        detail["whale_net_outflow_usd"] = whale_out
        detail["whale_alert"] = whale_alert
    if top10 > 50:
        score += min(5.0, (top10 - 50) * 0.2)
        detail["top10_holder_share_pct"] = top10
    if abs(mint_burn) >= 10_000_000:
        score += min(5.0, abs(mint_burn) / 2_000_000)
        detail["net_mint_burn_usd_24h"] = mint_burn
    return int(min(15, round(score))), detail


def apply_osint_amplifier(raw_score: float, event_type: str, source_authority: float) -> float:
    """Amplify raw score when an active OSINT signal exists with high source authority.
    Looks up amplifier from EXTERNAL_SIGNAL_MAP by event_type. Applied only when
    source_authority >= 0.70. Cap amplified score at 100."""
    if source_authority < 0.70:
        return raw_score
    for _sig_label, (_event_type, _severity, amp) in EXTERNAL_SIGNAL_MAP.items():
        if _event_type == event_type:
            return min(raw_score * amp, 100.0)
    return raw_score


def _compute_v4_risk_score(stablecoin_type: str, **kwargs) -> Dict[str, Any]:
    """V4 dispatch: select weight matrix by stablecoin sub-type, apply V4 component scorers."""
    return compute_risk_score(**kwargs)  # placeholder — real V4 component scorers in Sprint 3


def compute_risk_score(**kwargs) -> Dict[str, Any]:
    stablecoin_type = kwargs.pop("stablecoin_type", None)
    if stablecoin_type and stablecoin_type in V4_WEIGHT_MATRICES:
        return _compute_v4_risk_score(stablecoin_type, **kwargs)
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

    regime = kwargs.get("regime") or _infer_regime(
        float(depeg_score),
        float(depeg_score) * 0.35
        + float(concentration_score) * 0.20
        + float(velocity_component) * 0.15
        + float(liq_score) * 0.10
        + float(age_penalty) * 0.20,
    )
    weights = _weights_for_regime(regime)

    base_score = (
        depeg_score * weights["depeg"]
        + concentration_score * weights["concentration"]
        + velocity_component * weights["velocity"]
        + liq_score * weights["liquidity"]
        + age_penalty * weights["age_penalty"]
    )

    onchain_score, onchain_detail = _onchain_risk_score(**kwargs)
    final_score = max(0, min(100, base_score + onchain_score))
    band = _score_to_band(final_score)

    components = {
        "regime": regime,
        "depeg_index": {
            "score": int(depeg_score),
            "weight": weights["depeg"],
            "detail": {
                "price": kwargs.get("price"),
                "deviation_pct": kwargs.get("price") and round(abs(kwargs["price"] - 1.0) * 100, 4),
            },
        },
        "concentration": {"score": int(concentration_score), "weight": weights["concentration"], "detail": conc_detail},
        "velocity": {"score": int(velocity_component), "weight": weights["velocity"], "detail": vel_detail},
        "liquidity_depth": {
            "score": int(liq_score),
            "weight": weights["liquidity"],
            "detail": {"slippage_100k_bps": kwargs.get("slippage_100k_bps", 0)},
        },
        "age_penalty": {"score": int(age_penalty), "weight": weights["age_penalty"], "detail": age_detail},
        "onchain": {"score": int(onchain_score), "weight": 0, "detail": onchain_detail},
        "source_health": "OK" if source_ok else "DEGRADED",
    }

    return {
        "score": int(final_score),
        "band": band,
        "regime": regime,
        "components": components,
    }


def _score_to_band(score: float) -> str:
    """Unified V4 band: Normal / Watch / Alert / Critical."""
    if score <= 20:
        return "Normal"
    if score <= 50:
        return "Watch"
    if score <= 75:
        return "Alert"
    return "Critical"


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
