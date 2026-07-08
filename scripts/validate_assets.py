#!/usr/bin/env python3
"""Validate config/assets.json schema and enabled flags."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_KEYS = {"symbol", "name", "enabled"}
OPTIONAL_KEYS = {"chains", "peg_type", "coingecko_id", "display_order"}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    path = root / "config" / "assets.json"
    if not path.exists():
        print(f"ERROR: missing {path}", file=sys.stderr)
        return 1
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        print("ERROR: assets.json must be a JSON array", file=sys.stderr)
        return 1
    errors: list[str] = []
    symbols: set[str] = set()
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"row {i}: not an object")
            continue
        missing = REQUIRED_KEYS - set(item.keys())
        if missing:
            errors.append(f"row {i} ({item.get('symbol', '?')}): missing {sorted(missing)}")
        sym = str(item.get("symbol", "")).strip().upper()
        if not sym:
            errors.append(f"row {i}: empty symbol")
        elif sym in symbols:
            errors.append(f"duplicate symbol: {sym}")
        else:
            symbols.add(sym)
        if "enabled" in item and not isinstance(item["enabled"], bool):
            errors.append(f"{sym}: enabled must be boolean")
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    enabled = [a["symbol"] for a in data if a.get("enabled")]
    print(f"OK: {len(data)} assets ({len(enabled)} enabled)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
