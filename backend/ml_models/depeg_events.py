"""Historical depeg windows for training labels — transform.md §4.1.

This is a JSON label loader, NOT an ONNX model. The real ONNX models
are the 5 helix_*_v4_heuristic.onnx files in this directory."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVENTS_PATH = _REPO_ROOT / "data" / "depeg_events.json"


@dataclass(frozen=True)
class DepegEvent:
    asset: str
    start: date
    end: date
    trough: float
    notes: str = ""


def load_depeg_events(path: Path | None = None) -> list[DepegEvent]:
    p = path or _EVENTS_PATH
    if not p.is_file():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    out: list[DepegEvent] = []
    for row in raw:
        out.append(
            DepegEvent(
                asset=str(row["asset"]).upper(),
                start=date.fromisoformat(row["start"]),
                end=date.fromisoformat(row["end"]),
                trough=float(row.get("trough", 0.5)),
                notes=str(row.get("notes", "")),
            )
        )
    return out


def depeg_probability_at(ts: datetime, asset_symbol: str, events: list[DepegEvent] | None = None) -> tuple[float, float, float]:
    """Return (1h, 6h, 24h) depeg probability labels for a snapshot timestamp."""
    events = events if events is not None else load_depeg_events()
    sym = asset_symbol.upper()
    d = ts.date() if ts.tzinfo else ts.replace(tzinfo=timezone.utc).date()
    for ev in events:
        if ev.asset != sym:
            continue
        if ev.start <= d <= ev.end:
            severity = min(0.99, 0.4 + (1.0 - ev.trough))
            return (round(severity * 0.6, 4), round(severity * 0.85, 4), round(severity, 4))
    return (0.02, 0.03, 0.04)
