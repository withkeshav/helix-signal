"""Audit settings registry: cross-reference every registered key against actual usage.

Outputs a CSV report of key,usage_count,files to stdout (or a file path given as argv[1]).

Usage:
    python scripts/audit_settings.py [output.csv]

Exits 0 always — the report is the deliverable. Reviewer decides which keys to remove.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

# Resolve repo root: this file lives in backend/scripts/, so repo root is two levels up.
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
REGISTRY_FILE = BACKEND_DIR / "providers" / "settings_registry.py"


def extract_registry_keys() -> list[str]:
    """Parse _DEFAULT_SETTINGS keys directly from source (no import side effects)."""
    src = REGISTRY_FILE.read_text()
    # Match quoted dict keys at the top level of _DEFAULT_SETTINGS.
    # Pattern: line starts with `    "key": {` (4-space indent inside the outer dict).
    keys: list[str] = []
    in_dict = False
    for line in src.splitlines():
        if not in_dict:
            if "_DEFAULT_SETTINGS" in line and ": Dict" in line and "{" in line:
                in_dict = True
            continue
        # End of outer dict: closing brace at column 0.
        if line.startswith("}"):
            break
        m = re.match(r'^\s*"([^"]+)":\s*\{', line)
        if m:
            keys.append(m.group(1))
    return keys


def count_usage(key: str) -> tuple[int, list[str]]:
    """Count occurrences of `key` across backend/ excluding the registry file itself.

    Matches `get_setting("key"`, `get_setting('key'`, and bare `"key"` string literals
    that appear in code paths reading settings. Conservative: any quoted occurrence
    of the exact key string counts as a hit (avoids missing dynamic lookups).
    """
    hits: list[str] = []
    needle_quoted = f'"{key}"'
    needle_single = f"'{key}'"
    for path in BACKEND_DIR.rglob("*.py"):
        if not path.is_file():
            continue
        # Skip the registry itself — that's where keys are defined, not used.
        if path == REGISTRY_FILE:
            continue
        # Skip __pycache__.
        if "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        if needle_quoted in text or needle_single in text:
            rel = path.relative_to(REPO_ROOT).as_posix()
            hits.append(rel)
    return len(hits), hits


def main() -> int:
    keys = extract_registry_keys()
    rows = []
    for key in keys:
        count, files = count_usage(key)
        rows.append({
            "key": key,
            "usage_count": count,
            "files": ";".join(files),
        })

    # Sort: unused first (so reviewer sees them immediately), then by key name.
    rows.sort(key=lambda r: (r["usage_count"], r["key"]))

    out = sys.stdout
    close = False
    if len(sys.argv) > 1:
        out = open(sys.argv[1], "w", newline="")
        close = True
    try:
        writer = csv.DictWriter(out, fieldnames=["key", "usage_count", "files"])
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if close:
            out.close()

    unused = sum(1 for r in rows if r["usage_count"] == 0)
    total = len(rows)
    sys.stderr.write(
        f"Audit complete: {total} keys registered, {unused} unused.\n"
        f"Report written to {'file' if len(sys.argv) > 1 else 'stdout'}.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())