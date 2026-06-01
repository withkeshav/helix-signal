"""Settings import/export service."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

from providers.settings import Setting
from providers.settings import get_all_settings, set_setting
from services.settings_audit import log_settings_change


def export_settings(db: Session) -> Dict[str, Any]:
    """Export all settings as a dictionary."""
    settings = get_all_settings(db)
    
    # Create a dictionary with setting keys and values
    exported_settings = {}
    for setting in settings:
        key = setting["key"]
        # Get the actual value from the database
        db_setting = db.query(Setting).filter(Setting.key == key).first()
        if db_setting:
            exported_settings[key] = db_setting.value
        else:
            # Use the default value if not in database
            exported_settings[key] = setting["default"]
    
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
    
    # Import each setting
    for key, value in settings_to_import.items():
        try:
            # Try to set the setting
            set_setting(key, value, db, user, ip_address, user_agent)
            results["imported"] += 1
        except ValueError as e:
            # Skip settings that can't be set (e.g., always_active settings)
            results["skipped"] += 1
            results["errors"].append(f"Skipped {key}: {str(e)}")
        except Exception as e:
            # Log other errors
            results["errors"].append(f"Error importing {key}: {str(e)}")
    
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