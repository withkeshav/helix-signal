from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from database import ChainData, SourceStatus
from sources.defillama import DefiLlamaError, fetch_usdt_snapshot

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "chains.json"


def load_configured_chains() -> list[dict]:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        chains = json.load(file)
    if not isinstance(chains, list):
        return []
    return [item for item in chains if isinstance(item, dict) and item.get("defillama_id")]


def _upsert_source_status(
    db: Session,
    *,
    status: str,
    attempted_at: datetime,
    successful_at: datetime | None,
    last_error: str | None,
) -> None:
    row = db.query(SourceStatus).filter(SourceStatus.source_name == "defillama").first()
    if row is None:
        row = SourceStatus(source_name="defillama")
        db.add(row)

    row.status = status
    row.last_attempted_fetch = attempted_at
    if successful_at is not None:
        row.last_successful_fetch = successful_at
    row.last_error = last_error
    row.updated_at = datetime.now(timezone.utc)


def refresh_chain_data(db: Session) -> None:
    attempted_at = datetime.now(timezone.utc)
    configured = load_configured_chains()
    chain_ids = [str(item["defillama_id"]) for item in configured]

    try:
        snapshot = fetch_usdt_snapshot(chain_ids)
        fetched_at = snapshot["fetched_at"]
        per_chain = snapshot["chain_data"]

        for chain in configured:
            chain_name = str(chain["name"])
            key = str(chain["defillama_id"])
            values = per_chain.get(key, {})
            row = db.query(ChainData).filter(ChainData.chain_name == chain_name).first()
            if row is None:
                row = ChainData(chain_name=chain_name)
                db.add(row)

            row.usdt_supply = float(values.get("usdt_supply", 0.0))
            row.usdt_supply_prev_day = values.get("usdt_supply_prev_day")
            row.usdt_supply_prev_week = values.get("usdt_supply_prev_week")
            row.usdt_supply_prev_month = values.get("usdt_supply_prev_month")
            row.tvl = values.get("tvl")
            row.price = values.get("price")
            row.fetched_at = fetched_at
            row.updated_at = datetime.now(timezone.utc)

        _upsert_source_status(
            db,
            status="ok",
            attempted_at=attempted_at,
            successful_at=fetched_at,
            last_error=None,
        )
    except (DefiLlamaError, Exception) as exc:
        _upsert_source_status(
            db,
            status="error",
            attempted_at=attempted_at,
            successful_at=None,
            last_error=str(exc),
        )
        # Intentionally do not raise to keep scheduler worker alive.
    finally:
        db.commit()
