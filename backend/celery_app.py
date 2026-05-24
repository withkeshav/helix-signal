"""Celery application for background ML and ingest tasks."""

from __future__ import annotations

import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "helix_signal",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["worker_tasks"],
)

_refresh_seconds = int(os.getenv("REFRESH_INTERVAL_SECONDS", "300"))

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_soft_time_limit=120,
    task_time_limit=180,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "refresh-chain-data": {
            "task": "helix.refresh_chain_data",
            "schedule": float(_refresh_seconds),
        },
    },
)
