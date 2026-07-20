"""Moralis — holder concentration and large transfer alerts (transform.md §5.2)."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx

from providers.settings import get_setting, get_secret
from services.source_usage import _check_source_rate_limit, _record_source_call
from sources.onchain_tokens import ETHEREUM_TOKENS, WHALE_THRESHOLD_USD_DEFAULT

MORALIS_BASE = "https://deep-index.moralis.io/api/v2.2"


class MoralisSource:
    name = "moralis"

    def _api_key(self, db: Any = None) -> str:
        return str(get_secret("secret_moralis_api_key", db) or "").strip()

    def configured(self, db: Any = None) -> bool:
        return bool(self._api_key(db)) and bool(get_setting("provider_moralis", db))

    def _get(self, path: str, params: dict[str, Any], db: Any = None) -> dict[str, Any] | None:
        key = self._api_key(db)
        if not key or not get_setting("provider_moralis", db):
            return None
        for attempt in range(3):
            if _check_source_rate_limit(self.name):
                break
            time.sleep(0.5 * (2 ** attempt))
        else:
            return None
        _record_source_call(self.name)
        try:
            resp = httpx.get(
                f"{MORALIS_BASE}{path}",
                params=params,
                headers={"X-API-Key": key, "accept": "application/json"},
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    def fetch_holder_concentration(self, symbol: str, *, db: Any = None, limit: int = 10) -> dict[str, Any]:
        sym = symbol.upper()
        token = ETHEREUM_TOKENS.get(sym)
        if not token:
            return {"available": False, "reason": "unsupported_asset"}
        if not self.configured(db):
            return {"available": False, "reason": "moralis_not_configured"}

        address = str(token["address"])
        body = self._get(f"/erc20/{address}/owners", {"chain": "eth", "limit": limit}, db)
        if not body:
            return {"available": False, "reason": "moralis_error"}

        rows = body.get("result") or []
        decimals = int(token["decimals"])
        holders: list[dict[str, Any]] = []
        total_balance = 0.0
        for row in rows:
            bal_raw = float(row.get("balance") or row.get("balance_formatted") or 0)
            if row.get("balance_formatted") is None:
                bal = bal_raw / (10 ** decimals)
            else:
                bal = bal_raw
            total_balance += bal
            holders.append({
                "address": row.get("owner_address") or row.get("address"),
                "balance": round(bal, 2),
                "share_pct": None,
            })

        # Moralis may return percentage_of_supply
        top_share = 0.0
        for i, row in enumerate(rows):
            pct = row.get("percentage_relative_to_total_supply")
            if pct is not None:
                top_share += float(pct)
                holders[i]["share_pct"] = round(float(pct), 4)
            elif total_balance > 0 and holders[i]["balance"]:
                share = holders[i]["balance"] / total_balance * 100
                holders[i]["share_pct"] = round(share, 4)
                top_share += share

        risk = "low"
        if top_share > 60:
            risk = "high"
        elif top_share > 40:
            risk = "medium"

        return {
            "available": True,
            "source": self.name,
            "top10_share_pct": round(top_share, 2),
            "holder_count": len(holders),
            "holders": holders,
            "concentration_risk": risk,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    def fetch_large_transfers(
        self,
        symbol: str,
        *,
        db: Any = None,
        limit: int = 50,
        whale_threshold_usd: float | None = None,
    ) -> dict[str, Any]:
        sym = symbol.upper()
        token = ETHEREUM_TOKENS.get(sym)
        if not token:
            return {"available": False, "reason": "unsupported_asset"}
        if not self.configured(db):
            return {"available": False, "reason": "moralis_not_configured"}

        threshold = whale_threshold_usd
        if threshold is None:
            threshold = float(get_setting("onchain_whale_threshold_usd", db) or WHALE_THRESHOLD_USD_DEFAULT)

        address = str(token["address"])
        body = self._get(f"/erc20/{address}/transfers", {"chain": "eth", "limit": limit}, db)
        if not body:
            return {"available": False, "reason": "moralis_error"}

        decimals = int(token["decimals"])
        large: list[dict[str, Any]] = []
        gross_volume = 0.0
        for row in body.get("result") or []:
            val_raw = float(row.get("value") or 0)
            value_usd = val_raw / (10 ** decimals)
            if value_usd < threshold:
                continue
            # ERC20 transfer list has no wallet-relative direction without a seed address.
            # Label as transfer; accumulate gross large-transfer volume (not "net outflow").
            large.append({
                "hash": row.get("transaction_hash"),
                "from": row.get("from_address"),
                "to": row.get("to_address"),
                "value_usd": round(value_usd, 2),
                "direction": "transfer",
                "block_timestamp": row.get("block_timestamp"),
            })
            gross_volume += value_usd

        return {
            "available": True,
            "source": self.name,
            "large_transfers": large,
            "large_transfer_count": len(large),
            "whale_alert": len(large) >= 3,
            # Historical key name kept for callers; value is gross large-transfer USD volume
            "whale_net_outflow_usd": round(gross_volume, 2),
            "large_transfer_volume_usd": round(gross_volume, 2),
            "threshold_usd": threshold,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
