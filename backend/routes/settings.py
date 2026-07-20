from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.admin_auth import require_admin_token
from core.limiter import limiter
from database import get_db
from providers.settings import (
    get_all_settings,
    is_secret_skip_value,
    set_setting,
    setting_is_secret,
)
from services.retention import get_last_prune_result

router = APIRouter()


def _validate_webhook_settings(db: Session) -> None:
    from providers.settings import get_setting, get_secret
    from services.webhook_dispatcher import _coerce_bool, _validate_url

    enabled = _coerce_bool(get_setting("webhook_enabled", db))
    if not enabled:
        return
    url = str(get_setting("webhook_url", db) or "").strip()
    secret = str(get_secret("webhook_signing_secret", db) or "").strip()
    if not _validate_url(url):
        raise ValueError("webhook_url must be a valid http(s) URL when webhook_enabled is true")
    if not secret:
        raise ValueError("webhook_signing_secret is required when webhook_enabled is true")


class SettingUpdate(BaseModel):
    key: str
    value: bool | int | str

@router.get("/settings")
@limiter.limit("10/minute")
def api_get_settings(
    request: Request,
    search: str = Query(None, description="Search term to filter settings by key, label, or description"),
    group: str = Query(None, description="Filter settings by group"),
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> list[dict]:
    settings = get_all_settings(db)
    
    # Apply search filter
    if search:
        search_lower = search.lower()
        settings = [
            s for s in settings
            if search_lower in s.get("key", "").lower() 
            or search_lower in s.get("label", "").lower() 
            or search_lower in s.get("description", "").lower()
        ]
    
    # Apply group filter
    if group:
        settings = [s for s in settings if s.get("group") == group]
    
    # Remove sensitive information
    for s in settings:
        s.pop("key_env", None)
        
    return settings


@router.get("/settings/last-prune")
@limiter.limit("30/minute")
def api_last_prune(
    request: Request,
    _auth=Depends(require_admin_token),
) -> dict:
    """Last retention prune result for Control Room."""
    result = get_last_prune_result()
    return {"available": result is not None, "result": result}


@router.get("/settings/ops")
@limiter.limit("30/minute")
def api_settings_ops(
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict:
    """Scheduler + source health summary for Control Room Overview."""
    from core.registry import SOURCES_REGISTRY, get_source
    from services.data_quality_snapshots import get_quality_summary

    scheduler_running = False
    try:
        scheduler_running = bool(request.app.state.scheduler.running)
    except AttributeError:
        scheduler_running = False

    sources_ok = 0
    sources_total = len(SOURCES_REGISTRY)
    for name in SOURCES_REGISTRY:
        try:
            source = get_source(name)
            if source and hasattr(source, "health_check"):
                st = source.health_check()
                if st.get("state") == "closed":
                    sources_ok += 1
        except Exception:
            pass

    dq = get_quality_summary(db)
    return {
        "scheduler_running": scheduler_running,
        "sources_ok": sources_ok,
        "sources_total": sources_total,
        "last_prune": get_last_prune_result(),
        "quality_score": dq.get("overall_score"),
        "quality_generated_at": dq.get("generated_at"),
    }


@router.put("/settings")
@limiter.limit("5/minute")
def api_update_setting(
    request: Request,
    body: SettingUpdate,
    db: Session = Depends(get_db),
    _auth=Depends(require_admin_token),
) -> dict:
    user = None
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        # Never persist masked export sentinels as secret values; never echo secrets.
        if setting_is_secret(body.key):
            if is_secret_skip_value(body.value):
                return {"ok": True, "key": body.key, "value": "configured", "skipped": True}
            set_setting(body.key, body.value, db, user, ip_address, user_agent)
            _validate_webhook_settings(db)
            return {"ok": True, "key": body.key, "value": "configured"}
        set_setting(body.key, body.value, db, user, ip_address, user_agent)
        _validate_webhook_settings(db)
        return {"ok": True, "key": body.key, "value": body.value}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
