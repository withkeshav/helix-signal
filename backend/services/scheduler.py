"""Background job scheduler module.

Provides job functions and a registration helper so main.py stays lean.
"""

from __future__ import annotations

import os
import random
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session
from structlog import get_logger

from database import SessionLocal
from services.osint import ingest_osint_feed
from services.retention import prune_old_history
from signal_engine.core import refresh_chain_data

log = get_logger(__name__)

_JOB_DEFAULTS = {
    "max_instances": 1,
    "coalesce": True,
    "misfire_grace_time": 300,
}

_PLUGIN_JITTER = (30, 120)


async def _refresh_job() -> None:
    log.info("refresh_job.start")
    db = SessionLocal()
    try:
        await refresh_chain_data(db)
        log.info("refresh_job.data_refresh_complete")
        _run_anomaly_circuit_breaker(db)
        log.info("refresh_job.complete")
    except Exception:
        log.exception("refresh_job.failed")
        raise
    finally:
        db.close()


def _run_anomaly_circuit_breaker(db: Session) -> None:
    from agents.anomaly_agent import run_circuit_breaker_cycle
    results = run_circuit_breaker_cycle(db)
    if results:
        triggered = [r["asset_symbol"] for r in results if r.get("investigated")]
        if triggered:
            log.info("circuit_breaker.triggered", assets=triggered)


def _retention_job() -> None:
    db = SessionLocal()
    try:
        prune_old_history(db)
    finally:
        db.close()


def _data_quality_snapshot_job() -> None:
    db = SessionLocal()
    try:
        from services.data_quality_snapshots import run_data_quality_snapshot_job
        run_data_quality_snapshot_job(db)
    except Exception:
        log.exception("data_quality_snapshot_job.failed")
    finally:
        db.close()


def _insight_refresh_job() -> None:
    db = SessionLocal()
    try:
        from services.insight_assets import refresh_all_insights_job
        refresh_all_insights_job(db)
    except Exception:
        log.exception("insight_refresh_job.failed")
    finally:
        db.close()


def _osint_job() -> None:
    from providers.settings import get_setting
    db = SessionLocal()
    try:
        if not get_setting("feature_osint_feed", db):
            return
        count = ingest_osint_feed(db)
        if count:
            log.info("osint_job.complete", articles_ingested=count)
    except Exception:
        log.exception("osint_job.failed")
    finally:
        db.close()


async def _osint_attestation_refresh() -> None:
    try:
        from services.attestation import _refresh_attestation_reports_async
        await _refresh_attestation_reports_async()
        log.info("osint_attestation_refresh.complete", cache_fresh=True)
    except Exception:
        log.exception("osint_attestation_refresh.failed")


async def _ethena_job() -> None:
    db = SessionLocal()
    try:
        from sources.plugins.ethena_plugin import fetch as ethena_fetch
        await ethena_fetch(db)
    except Exception:
        log.exception("ethena_job.failed")
    finally:
        db.close()


async def _coinglass_job() -> None:
    db = SessionLocal()
    try:
        from sources.plugins.coinglass_plugin import fetch as coinglass_fetch
        await coinglass_fetch(db)
    except Exception:
        log.exception("coinglass_job.failed")
    finally:
        db.close()


async def _sky_job() -> None:
    db = SessionLocal()
    try:
        from sources.plugins.sky_protocol_plugin import fetch as sky_fetch
        await sky_fetch(db)
    except Exception:
        log.exception("sky_job.failed")
    finally:
        db.close()


async def _liquity_job() -> None:
    db = SessionLocal()
    try:
        from sources.plugins.liquity_plugin import fetch as liquity_fetch
        await liquity_fetch(db)
    except Exception:
        log.exception("liquity_job.failed")
    finally:
        db.close()


async def _aave_job() -> None:
    db = SessionLocal()
    try:
        from sources.plugins.aave_plugin import fetch as aave_fetch
        await aave_fetch(db)
    except Exception:
        log.exception("aave_job.failed")
    finally:
        db.close()


async def _ondo_job() -> None:
    db = SessionLocal()
    try:
        from sources.plugins.ondo_plugin import fetch as ondo_fetch
        await ondo_fetch(db)
    except Exception:
        log.exception("ondo_job.failed")
    finally:
        db.close()


async def _blacklist_job() -> None:
    db = SessionLocal()
    try:
        from chain.intelligence.blacklist_monitor import poll as blacklist_poll
        await blacklist_poll(db)
    except Exception:
        log.exception("blacklist_job.failed")
    finally:
        db.close()


async def _fiat_reserve_job() -> None:
    """Best-effort fiat reserve scrape — failures never re-raise."""
    db = SessionLocal()
    try:
        from services.fiat_reserve_scraper import scrape_reserves
        result = await scrape_reserves(db)
        log.info("fiat_reserve_job.complete", **(result or {}))
    except Exception:
        log.exception("fiat_reserve_job.failed")
    finally:
        db.close()


def _web_search_job() -> None:
    """12h web context refresh — only when AI on + Tavily/Exa key."""
    db = SessionLocal()
    try:
        from services.web_search.job import run_web_search_job
        result = run_web_search_job(db)
        log.info("web_search_job.complete", **(result or {}))
    except Exception:
        log.exception("web_search_job.failed")
    finally:
        db.close()


def register_scheduler_jobs(
    scheduler: AsyncIOScheduler,
    setup_db: Session,
    *,
    skip_refresh: bool = False,
) -> None:
    """Register all background job functions with the APScheduler instance."""
    from providers.settings import get_setting

    def _add_job(func, trigger, *, job_id: str, jitter: int | None = None, **trigger_kwargs):
        kwargs = {**_JOB_DEFAULTS, "id": job_id, "replace_existing": True}
        if jitter is not None:
            trigger_kwargs["jitter"] = jitter
        scheduler.add_job(func, trigger, **trigger_kwargs, **kwargs)

    if not skip_refresh:
        interval_seconds = max(
            60,
            get_setting("refresh_core_seconds", setup_db)
            or int(os.getenv("REFRESH_INTERVAL_SECONDS", "300")),
        )
        _add_job(
            _refresh_job,
            "interval",
            job_id="defillama-refresh",
            seconds=interval_seconds,
        )

    osint_minutes = max(
        15,
        get_setting("refresh_osint_minutes", setup_db) or 60,
    )

    _add_job(_retention_job, "cron", job_id="history-retention", hour=3, minute=15)
    _add_job(_data_quality_snapshot_job, "cron", job_id="data-quality-snapshot", hour=4, minute=0)
    _add_job(_insight_refresh_job, "cron", job_id="insight-assets-refresh", hour=4, minute=30)
    # Daily best-effort issuer reserve scrape (isolated; HTML drift only logs warnings)
    _add_job(_fiat_reserve_job, "cron", job_id="fiat-reserve-scrape", hour=5, minute=0)
    # Web search cache for AI (12h) — skipped unless Tavily/Exa secret present + ai_mode on
    _add_job(_web_search_job, "cron", job_id="web-search-refresh", hour="6,18", minute=15)
    # One delayed boot fill if feature on and cache empty/stale (avoids waiting until next 06:15/18:15)
    try:
        from sqlalchemy import desc, select

        from database import WebSearchSnapshot
        from services.web_search.job import web_search_feature_enabled

        if web_search_feature_enabled(setup_db):
            now = datetime.now(timezone.utc)
            last = (
                setup_db.execute(
                    select(WebSearchSnapshot)
                    .order_by(desc(WebSearchSnapshot.fetched_at))
                    .limit(1)
                )
                .scalars()
                .first()
            )
            stale = last is None or (
                last.fetched_at is not None
                and last.fetched_at < now - timedelta(hours=12)
            )
            if stale:
                run_at = now + timedelta(minutes=5)
                _add_job(
                    _web_search_job,
                    "date",
                    job_id="web-search-startup-once",
                    run_date=run_at,
                )
                log.info("web_search.startup_once_scheduled", run_at=run_at.isoformat())
    except Exception:
        log.warning("web_search.startup_once_schedule_failed", exc_info=True)
    _add_job(_osint_job, "interval", job_id="osint-ingest", minutes=osint_minutes)
    _add_job(_osint_attestation_refresh, "interval", job_id="osint-attestation-refresh", minutes=osint_minutes)
    _add_job(
        _blacklist_job,
        "interval",
        job_id="blacklist-monitor",
        seconds=get_setting("blacklist_poll_interval_seconds", setup_db) or 300,
    )
    coinglass_seconds = max(
        900,
        get_setting("funding_rate_poll_interval_seconds", setup_db) or 900,
    )
    _add_job(_coinglass_job, "interval", job_id="funding-rate-poll", seconds=coinglass_seconds)
    plugin_jitter = random.randint(*_PLUGIN_JITTER)
    for idx, (func, job_id) in enumerate(
        (
            (_ethena_job, "ethena-poll"),
            (_sky_job, "sky-poll"),
            (_liquity_job, "liquity-poll"),
            (_aave_job, "aave-poll"),
            (_ondo_job, "ondo-poll"),
        )
    ):
        _add_job(
            func,
            "interval",
            job_id=job_id,
            minutes=15,
            jitter=plugin_jitter,
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=30 * (idx + 1)),
        )
