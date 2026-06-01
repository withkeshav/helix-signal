"""Auto-discover and register all route modules."""


def register_routes(app):
    from routes.dashboard import router as dashboard_router
    from routes.forecasts import router as forecasts_router
    from routes.trends import router as trends_router
    from routes.events import router as events_router
    from routes.predictive import router as predictive_router
    from routes.osint import router as osint_router
    from routes.analytics import router as analytics_router
    from routes.health import router as health_router
    from routes.admin import router as admin_router
    from routes.chain_detail import router as chain_detail_router
    from routes.sources import router as sources_router
    from routes.settings import router as settings_router
    from routes.settings_audit import router as settings_audit_router
    from routes.settings_import_export import router as settings_import_export_router
    from routes.ai_routes import router as ai_router
    from routes.users import router as users_router
    from routes.telegram import router as telegram_router
    from routes.data_quality import router as data_quality_router

    app.include_router(dashboard_router, prefix="/api")
    app.include_router(ai_router, prefix="/api")
    app.include_router(trends_router, prefix="/api")
    app.include_router(forecasts_router, prefix="/api")
    app.include_router(events_router, prefix="/api")
    app.include_router(predictive_router, prefix="/api")
    app.include_router(osint_router, prefix="/api")
    app.include_router(analytics_router, prefix="/api")
    app.include_router(health_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")
    app.include_router(chain_detail_router, prefix="/api")
    app.include_router(sources_router, prefix="/api")
    app.include_router(settings_router, prefix="/api")
    app.include_router(settings_audit_router, prefix="/api")
    app.include_router(settings_import_export_router, prefix="/api")
    app.include_router(users_router, prefix="/api")
    app.include_router(telegram_router, prefix="/api")
    app.include_router(data_quality_router, prefix="/api")
