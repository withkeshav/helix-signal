"""Register all route modules (manual list — no auto-discovery)."""


def register_routes(app):
    from routes.admin import router as admin_router
    from routes.ai_routes import router as ai_router
    from routes.ai_models import router as ai_models_router
    from routes.alerts import router as alerts_router
    from routes.auth import router as auth_router
    from routes.dashboard import router as dashboard_router
    from routes.data_quality import router as data_quality_router
    from routes.events import router as events_router
    from routes.forecasts import router as forecasts_router
    from routes.health import router as health_router
    from routes.osint import router as osint_router
    from routes.playbooks import router as playbooks_router
    from routes.predictive import router as predictive_router
    from routes.reports import router as reports_router
    from routes.settings import router as settings_router
    from routes.sources import router as sources_router
    from routes.trends import router as trends_router
    from routes.analytics import router as analytics_router
    from routes.chain_detail import router as chain_detail_router
    from routes.settings_audit import router as settings_audit_router
    from routes.settings_import_export import router as settings_import_export_router
    from routes.users import router as users_router
    from routes.dews import router as dews_router
    from routes.onchain import router as onchain_router
    from routes.external_intel_webhook import router as external_intel_webhook_router
    from routes.investigate import router as investigate_router
    from routes.yield_intelligence import router as yield_intelligence_router
    from routes.blacklist import router as blacklist_router
    from routes.narrative import router as narrative_router

    app.include_router(admin_router, prefix="/api", tags=["admin"])
    app.include_router(ai_router, prefix="/api", tags=["ai"])
    app.include_router(ai_models_router, prefix="/api", tags=["admin"])
    app.include_router(alerts_router, prefix="/api", tags=["alerts"])
    app.include_router(auth_router, prefix="/api", tags=["auth"])
    app.include_router(dashboard_router, prefix="/api", tags=["dashboard"])
    app.include_router(data_quality_router, prefix="/api", tags=["data-quality"])
    app.include_router(events_router, prefix="/api", tags=["events"])
    app.include_router(forecasts_router, prefix="/api", tags=["forecasts"])
    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(osint_router, prefix="/api", tags=["osint"])
    app.include_router(playbooks_router, prefix="/api", tags=["playbooks"])
    app.include_router(predictive_router, prefix="/api", tags=["predictive"])
    app.include_router(reports_router, prefix="/api", tags=["reports"])
    app.include_router(settings_router, prefix="/api", tags=["settings"])
    app.include_router(sources_router, prefix="/api", tags=["sources"])
    app.include_router(trends_router, prefix="/api", tags=["trends"])
    app.include_router(analytics_router, prefix="/api", tags=["analytics"])
    app.include_router(chain_detail_router, prefix="/api", tags=["chains"])
    app.include_router(settings_audit_router, prefix="/api", tags=["settings"])
    app.include_router(settings_import_export_router, prefix="/api", tags=["settings"])
    app.include_router(users_router, prefix="/api", tags=["users"])
    app.include_router(dews_router, prefix="/api", tags=["dews"])
    app.include_router(onchain_router, prefix="/api", tags=["onchain"])
    app.include_router(external_intel_webhook_router, prefix="/api", tags=["webhooks"])
    app.include_router(investigate_router, prefix="/api/v1", tags=["investigate"])
    app.include_router(yield_intelligence_router, prefix="/api/v1", tags=["yield"])
    app.include_router(blacklist_router, prefix="/api/v1", tags=["blacklist"])
    app.include_router(narrative_router, prefix="/api/v1", tags=["narrative"])
