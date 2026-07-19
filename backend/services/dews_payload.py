"""Build DEWS payload (shared by route + insight assets)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from structlog import get_logger

from database import AssetChainSnapshot
from services.anomaly import detect_anomalies, detect_change_points
from services.dews import compute_dews
from services.onnx_inference import (
    MODELS_DIR,
    MODEL_REGISTRY,
    build_feature_vector,
    predict_depeg_probability,
    predict_depeg_probability_v4,
)
from services.predictive import _depeg_probability_heuristic
from services.ai_router import ai_mode
from signal_engine.metrics import compute_asset_metric_bundle
from signal_engine.risk_inputs import (
    build_risk_score_kwargs,
    build_v4_onnx_features,
    compute_unified_risk_score,
    inject_velocity,
)

log = get_logger(__name__)


def build_dews_payload(db: Session, sym: str) -> dict:
    bundle = compute_asset_metric_bundle(db, asset_symbol=sym)
    if bundle is None:
        return {"asset": sym, "available": False, "dews_score": 0, "band": "normal", "tiers_fired": []}

    chains = db.execute(select(AssetChainSnapshot).where(AssetChainSnapshot.asset_symbol == sym)).scalars().all()
    refresh_interval = 300
    try:
        from providers.settings import get_setting
        refresh_interval = int(get_setting("refresh_core_seconds", db) or 300)
    except Exception:
        log.warning("dews.refresh_interval_lookup_failed", asset=sym, exc_info=True)

    risk = compute_unified_risk_score(
        chains,
        source_ok=bundle.source_ok,
        source_error=bundle.source_error,
        age_seconds=bundle.freshness_age_seconds,
        refresh_interval_seconds=refresh_interval,
        db=db,
        asset_symbol=sym,
    )
    risk_kwargs = build_risk_score_kwargs(
        chains,
        source_ok=bundle.source_ok,
        source_error=bundle.source_error,
        age_seconds=bundle.freshness_age_seconds,
        refresh_interval_seconds=refresh_interval,
    )
    liq_component = int((risk.get("components") or {}).get("liquidity_depth", {}).get("score") or 0)
    disc_pct = float(risk_kwargs.get("cross_source_discrepancy_pct") or 0.0)

    anomaly = detect_anomalies(db, asset_symbol=sym)
    z_items = anomaly.get("z_score", {}) if isinstance(anomaly, dict) else {}
    z_max = 0.0
    for items in z_items.values():
        if isinstance(items, list):
            for item in items:
                z_max = max(z_max, abs(float(item.get("z_score", 0))))

    cusum = anomaly.get("cusum", {}) if isinstance(anomaly, dict) else {}
    cusum_triggered = any(
        isinstance(v, dict) and v.get("triggered") for v in cusum.values()
    )
    if not cusum_triggered:
        change_pts = detect_change_points(db, asset_symbol=sym)
        cusum_triggered = bool(
            change_pts.get("available") and (change_pts.get("total_change_points") or 0) > 0
        )

    llm_escalated = z_max > 3.0 and ai_mode(db) != "ai_off"

    vel_kwargs = inject_velocity(db, {}, asset_symbol=sym)
    features = build_feature_vector(
        price=bundle.price,
        signal_score=bundle.signal_score,
        concentration_score=bundle.concentration_score,
        depeg_index=bundle.depeg_index,
        supply_velocity_1h=vel_kwargs.get("supply_velocity_1h"),
        cross_source_discrepancy_pct=disc_pct,
    )

    from services.onchain import onchain_risk_inputs
    onchain = onchain_risk_inputs(sym, db)

    stablecoin_type = None
    for c in chains:
        if c.stablecoin_type:
            stablecoin_type = c.stablecoin_type
            break

    pred = None
    if stablecoin_type:
        v4_model = MODEL_REGISTRY.get(stablecoin_type)
        if v4_model and (MODELS_DIR / v4_model).is_file():
            try:
                v4_features = build_v4_onnx_features(
                    db,
                    asset_symbol=sym,
                    stablecoin_type=stablecoin_type,
                    price=bundle.price,
                )
                v4_prob = predict_depeg_probability_v4(sym, v4_features, stablecoin_type)
                pred = {
                    "horizon_1h": round(min(v4_prob * 0.5, 0.99), 4),
                    "horizon_6h": round(min(v4_prob * 0.8, 0.99), 4),
                    "horizon_24h": round(min(v4_prob, 0.99), 4),
                    "model": "onnx_depeg_v4",
                    "confidence": "high",
                }
            except Exception:
                log.warning("dews.v4_fallback", asset=sym)

    if pred is None:
        pred = predict_depeg_probability(features) or _depeg_probability_heuristic(
            price=bundle.price,
            signal_score=bundle.signal_score,
            liquidity_score=liq_component,
        )

    depeg_p24 = float(pred.get("horizon_24h", 0) or 0)

    out = compute_dews(
        z_score_max=z_max,
        cusum_triggered=cusum_triggered,
        cross_source_discrepancy_pct=disc_pct,
        depeg_probability_24h=depeg_p24,
        llm_escalated=llm_escalated,
        whale_net_outflow_usd=onchain.get("whale_net_outflow_usd", 0),
        whale_alert=onchain.get("whale_alert", False),
        top10_holder_share_pct=onchain.get("top10_holder_share_pct", 0),
        net_mint_burn_usd_24h=onchain.get("net_mint_burn_usd_24h", 0),
    )
    out["asset"] = sym
    out["available"] = True
    out["model"] = pred.get("model", "heuristic_v1")
    out["z_score_max"] = z_max
    out["cusum_triggered"] = cusum_triggered
    out["cross_source_discrepancy_pct"] = disc_pct
    out["depeg_probability_24h"] = depeg_p24
    return out
