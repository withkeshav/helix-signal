"""SQLAdmin operator panel — mounted at /admin.

Do NOT name this module backend/admin.py (collides with routes/admin.py).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import anyio
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from wtforms import ValidationError

from database import ApiKey, Playbook, SettingsAuditLog, SessionLocal, User, engine
from providers.settings import Setting, mask_secret, set_setting
from providers.settings_registry import _DEFAULT_SETTINGS
from services.user_service import authenticate_user, get_password_hash

log = logging.getLogger(__name__)

_MASKED_SENTINELS = frozenset({"", "configured", "********", "****", "[redacted]", "[REDACTED]"})


def is_secret_skip_value(value: Any) -> bool:
    """True when a submitted secret should NOT overwrite the stored value."""
    if value is None:
        return True
    text = str(value).strip()
    if text.lower() in {s.lower() for s in _MASKED_SENTINELS}:
        return True
    # Common mask patterns: last-4 reveal style "••••abcd" / "****abcd"
    if text.startswith(("•", "*")) and len(text) <= 12:
        return True
    return False


def _setting_is_secret(key: str) -> bool:
    meta = _DEFAULT_SETTINGS.get(key) or {}
    return meta.get("type") == "secret"


def _format_setting_value(model: Setting, _attr: Any) -> str:
    if _setting_is_secret(model.key):
        return mask_secret(model.value) or ""
    return model.value if model.value is not None else ""


class HelixAdminAuth(AuthenticationBackend):
    """Authenticate SQLAdmin with existing User rows (admin role / is_admin)."""

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = str(form.get("username") or "").strip()
        password = str(form.get("password") or "")
        if not username or not password:
            return False

        def _check() -> User | None:
            with SessionLocal() as db:
                user = authenticate_user(db, username, password)
                if user is None:
                    return None
                if not user.is_active:
                    return None
                if not (user.is_admin or user.role == "admin"):
                    return None
                return user

        user = await anyio.to_thread.run_sync(_check)
        if user is None:
            return False
        request.session.update(
            {
                "admin_user_id": user.id,
                "admin_username": user.username,
                "admin_role": user.role,
            }
        )
        return True

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return bool(request.session.get("admin_user_id"))


class SettingAdmin(ModelView, model=Setting):
    """Edit-only settings view; secrets masked; writes go through set_setting."""

    name = "Setting"
    name_plural = "Settings"
    icon = "fa-solid fa-sliders"
    can_create = False
    can_delete = False
    can_edit = True
    can_view_details = True
    column_list = [Setting.key, Setting.value]
    column_searchable_list = [Setting.key]
    column_sortable_list = [Setting.key]
    column_details_list = [Setting.key, Setting.value]
    form_columns = [Setting.value]
    column_formatters = {Setting.value: _format_setting_value}
    column_formatters_detail = {Setting.value: _format_setting_value}
    form_args = {
        "value": {
            "description": "For secrets: leave blank or 'configured' to keep the existing value.",
        }
    }

    async def get_object_for_edit(self, request: Request) -> Any:
        return await super().get_object_for_edit(request)

    async def get_form_data_for_edit(self, obj: Any) -> dict[str, Any]:
        data = await super().get_form_data_for_edit(obj)
        if obj is not None and _setting_is_secret(obj.key):
            data["value"] = mask_secret(obj.value) or ""
        return data

    async def update_model(self, request: Request, pk: str, data: dict) -> Any:
        value = data.get("value")
        username = request.session.get("admin_username")

        def _update() -> Setting:
            with self.session_maker(expire_on_commit=False) as session:
                row = session.get(Setting, pk)
                if row is None:
                    raise ValidationError(f"Setting '{pk}' not found")

                if _setting_is_secret(pk) and is_secret_skip_value(value):
                    return row

                user = None
                if username:
                    from sqlalchemy import select as sa_select

                    user = session.execute(
                        sa_select(User).where(User.username == username)
                    ).scalars().first()

                try:
                    set_setting(
                        pk,
                        value,
                        session,
                        user=user,
                        ip_address=request.client.host if request.client else None,
                        user_agent=request.headers.get("user-agent"),
                        flush=True,
                    )
                    session.commit()
                except ValueError as exc:
                    session.rollback()
                    raise ValidationError(str(exc)) from exc

                refreshed = session.get(Setting, pk)
                assert refreshed is not None
                return refreshed

        return await anyio.to_thread.run_sync(_update)


class SettingsAuditLogAdmin(ModelView, model=SettingsAuditLog):
    """Read-only audit trail for settings changes."""

    name = "Settings Audit Log"
    name_plural = "Settings Audit Logs"
    icon = "fa-solid fa-clock-rotate-left"
    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True
    column_list = [
        SettingsAuditLog.id,
        SettingsAuditLog.setting_key,
        SettingsAuditLog.old_value,
        SettingsAuditLog.new_value,
        SettingsAuditLog.user_username,
        SettingsAuditLog.created_at,
    ]
    column_searchable_list = [SettingsAuditLog.setting_key, SettingsAuditLog.user_username]
    column_sortable_list = [SettingsAuditLog.id, SettingsAuditLog.created_at, SettingsAuditLog.setting_key]
    column_default_sort = [(SettingsAuditLog.created_at, True)]
    column_details_list = [
        SettingsAuditLog.id,
        SettingsAuditLog.setting_key,
        SettingsAuditLog.old_value,
        SettingsAuditLog.new_value,
        SettingsAuditLog.user_id,
        SettingsAuditLog.user_username,
        SettingsAuditLog.ip_address,
        SettingsAuditLog.user_agent,
        SettingsAuditLog.created_at,
    ]


class PlaybookAdmin(ModelView, model=Playbook):
    """Playbook CRUD — built-ins are edit-protected and non-deletable."""

    name = "Playbook"
    name_plural = "Playbooks"
    icon = "fa-solid fa-book"
    column_list = [Playbook.id, Playbook.name, Playbook.label, Playbook.is_builtin, Playbook.updated_at]
    column_searchable_list = [Playbook.name, Playbook.label]
    column_sortable_list = [Playbook.id, Playbook.name, Playbook.is_builtin]
    form_excluded_columns = [Playbook.created_at, Playbook.updated_at]
    can_view_details = True

    async def check_can_edit(self, request: Request, model: Any) -> bool:
        if model is not None and getattr(model, "is_builtin", False):
            return False
        return self.can_edit

    async def check_can_delete(self, request: Request, model: Any) -> bool:
        if model is not None and getattr(model, "is_builtin", False):
            return False
        return self.can_delete

    async def on_model_delete(self, model: Playbook, request: Request) -> None:
        if model.is_builtin:
            raise ValidationError("Built-in playbooks cannot be deleted")

    async def on_model_change(self, data: dict, model: Any, is_created: bool, request: Request) -> None:
        from datetime import datetime, timezone

        data["updated_at"] = datetime.now(timezone.utc)
        if is_created:
            data.setdefault("is_builtin", False)
            data.setdefault("created_at", datetime.now(timezone.utc))
        elif model is not None and model.is_builtin:
            raise ValidationError("Built-in playbooks cannot be edited here")


class UserAdmin(ModelView, model=User):
    """User management — passwords hashed via user_service; hash never shown."""

    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-users"
    column_list = [User.id, User.username, User.email, User.role, User.is_active, User.is_admin, User.created_at]
    column_searchable_list = [User.username, User.email]
    form_excluded_columns = [User.created_at, User.updated_at]
    column_details_exclude_list = [User.hashed_password]
    form_create_rules = ["username", "email", "hashed_password", "role", "is_active", "is_admin"]
    form_edit_rules = ["username", "email", "hashed_password", "role", "is_active", "is_admin"]
    column_labels = {User.hashed_password: "Password"}
    can_view_details = True

    async def on_model_change(self, data: dict, model: Any, is_created: bool, request: Request) -> None:
        from datetime import datetime, timezone

        raw = data.get("hashed_password")
        if is_created:
            if not raw:
                raise ValidationError("Password is required for new users")
            data["hashed_password"] = get_password_hash(str(raw))
            data.setdefault("created_at", datetime.now(timezone.utc))
        else:
            # Empty password on edit → keep existing hash
            if not raw or is_secret_skip_value(raw):
                data.pop("hashed_password", None)
            else:
                data["hashed_password"] = get_password_hash(str(raw))
        data["updated_at"] = datetime.now(timezone.utc)

    async def get_form_data_for_edit(self, obj: Any) -> dict[str, Any]:
        data = await super().get_form_data_for_edit(obj)
        data["hashed_password"] = ""
        return data


class ApiKeyAdmin(ModelView, model=ApiKey):
    """API keys — create via REST to receive raw secret once; admin can revoke here."""

    name = "API Key"
    name_plural = "API Keys"
    icon = "fa-solid fa-key"
    can_create = False  # creation via POST /api/v1/api-keys so raw is returned once
    can_edit = True
    can_delete = True
    column_list = [
        ApiKey.id,
        ApiKey.name,
        ApiKey.key_prefix,
        ApiKey.scopes,
        ApiKey.enabled,
        ApiKey.rate_limit_rpm,
        ApiKey.last_used_at,
        ApiKey.revoked_at,
    ]
    column_searchable_list = [ApiKey.name, ApiKey.key_prefix]
    form_excluded_columns = [ApiKey.key_hash, ApiKey.created_at, ApiKey.created_by_user_id]
    column_details_exclude_list = [ApiKey.key_hash]
    can_view_details = True


def setup_admin(app) -> Admin | None:
    """Mount SQLAdmin at /admin. Uses SESSION_SIGNING_KEY for its own session cookie.

    Does not add a parent SessionMiddleware — SQLAdmin owns that when
    authentication_backend is provided.
    """
    secret = os.getenv("SESSION_SIGNING_KEY", "").strip()
    if not secret:
        log.warning("SESSION_SIGNING_KEY missing — /admin SQLAdmin not mounted")
        return None

    authentication_backend = HelixAdminAuth(secret_key=secret)
    admin = Admin(
        app,
        engine,
        authentication_backend=authentication_backend,
        title="Helix Signal Admin",
        base_url="/admin",
    )
    admin.add_view(SettingAdmin)
    admin.add_view(SettingsAuditLogAdmin)
    admin.add_view(PlaybookAdmin)
    admin.add_view(UserAdmin)
    admin.add_view(ApiKeyAdmin)
    log.info("SQLAdmin mounted at /admin")
    return admin
