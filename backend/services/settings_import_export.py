"""Settings import/export service."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, Any

from sqlalchemy.orm import Session

from providers.settings import (
    get_all_settings,
    is_secret_skip_value,
    set_setting,
    setting_is_secret,
)


def export_settings(db: Session) -> Dict[str, Any]:
    """Export all settings as a dictionary.

    Secret values are already masked by get_all_settings (``configured`` / null).
    Re-importing that payload must not overwrite real secrets (see import_settings).
    """
    settings = get_all_settings(db)

    # Create a dictionary with setting keys and values
    exported_settings = {s["key"]: s["value"] for s in settings}

    # Add metadata
    export_data = {
        "settings": exported_settings,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "version": "1.0",
    }

    return export_data


def import_settings(
    db: Session,
    settings_data: Dict[str, Any],
    user: Any = None,
    ip_address: str = None,
    user_agent: str = None,
) -> Dict[str, Any]:
    """Import settings from a dictionary.

    Returns a dictionary with import results:
    {
        "imported": int,  # Number of settings imported
        "skipped": int,   # Number of settings skipped
        "errors": list,   # List of errors encountered
    }

    Secret keys with masked/sentinel values (e.g. export's ``configured``) are
    skipped so a round-trip export→import cannot clobber live API keys.
    """
    results = {
        "imported": 0,
        "skipped": 0,
        "errors": [],
    }

    # Validate the import data
    if "settings" not in settings_data:
        results["errors"].append("Invalid export format: missing 'settings' key")
        return results

    settings_to_import = settings_data["settings"]
    if not isinstance(settings_to_import, dict):
        results["errors"].append("Invalid export format: 'settings' must be an object")
        return results

    # Import each setting in a single transaction
    try:
        for key, value in settings_to_import.items():
            try:
                if setting_is_secret(str(key)) and is_secret_skip_value(value):
                    results["skipped"] += 1
                    continue
                set_setting(key, value, db, user, ip_address, user_agent, flush=True)
                results["imported"] += 1
            except ValueError as e:
                results["skipped"] += 1
                results["errors"].append(f"Skipped {key}: {str(e)}")
            except Exception as e:
                results["errors"].append(f"Error importing {key}: {str(e)}")
        db.commit()
    except Exception:
        db.rollback()
        raise

    return results


def export_settings_to_json(db: Session) -> str:
    """Export all settings as a JSON string."""
    export_data = export_settings(db)
    return json.dumps(export_data, indent=2)


def import_settings_from_json(
    db: Session,
    json_data: str,
    user: Any = None,
    ip_address: str = None,
    user_agent: str = None,
) -> Dict[str, Any]:
    """Import settings from a JSON string."""
    try:
        settings_data = json.loads(json_data)
        return import_settings(db, settings_data, user, ip_address, user_agent)
    except json.JSONDecodeError as e:
        return {
            "imported": 0,
            "skipped": 0,
            "errors": [f"Invalid JSON data: {str(e)}"],
        }