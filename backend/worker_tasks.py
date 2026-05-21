"""Celery tasks: refresh, predictive inference, optional AI enrichment."""

from __future__ import annotations

from celery_app import celery_app
from database import SessionLocal
from signal_engine.core import refresh_chain_data


@celery_app.task(name="helix.refresh_chain_data")
def task_refresh_chain_data() -> str:
    db = SessionLocal()
    try:
        refresh_chain_data(db)
        return "ok"
    finally:
        db.close()


@celery_app.task(name="helix.predictive_inference")
def task_predictive_inference(asset_symbol: str = "USDT") -> dict:
    from services.predictive import run_predictive_bundle

    db = SessionLocal()
    try:
        return run_predictive_bundle(db, asset_symbol=asset_symbol, log_to_mlflow=True)
    finally:
        db.close()


@celery_app.task(name="helix.ai_enrich")
def task_ai_enrich(feature: str, context: dict) -> dict:
    from services.ai_router import enrich_with_ai

    return enrich_with_ai(feature=feature, context=context)
