# Adding a Stablecoin

Adding a new stablecoin to Helix-Signal takes **3 steps** — all configuration, zero code.

## Step 1: Add to assets.json

```json
// config/assets.json
"NEWCOIN": {
  "name": "New Stablecoin",
  "symbol": "NEWCOIN",
  "enabled": true,
  "peg_type": "peggedUSD",
  "defillama_symbol": "NEWCOIN",
  "coingecko_id": "new-stablecoin",
  "chains": ["ethereum", "arbitrum"]
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `symbol` | Yes | Uppercase ticker (2-16 alphanumeric chars) |
| `name` | Yes | Human-readable name |
| `enabled` | Yes | `true` to show in UI and refresh cycle |
| `peg_type` | Yes | `"peggedUSD"` for USD stablecoins |
| `defillama_symbol` | Yes | Symbol DeFiLlama uses (auto-resolved) |
| `coingecko_id` | Yes | CoinGecko API ID |
| `chains` | Yes | List of chain keys from `chains.json` |

## Step 2: Restart the backend

```bash
docker compose restart backend
```

Or for local dev, reload (uvicorn auto-reload detects config changes).

## Step 3: Verify

```bash
curl http://localhost:8000/api/dashboard?asset=NEWCOIN | jq .
```

The asset appears in the asset selector, refresh cycle processes it, and all sources attempt to fetch data.

### What happens automatically

- DeFiLlama resolves supply and TVL for configured chains
- CoinGecko fetches price, market cap, volume
- DEX Screener checks liquidity pools on supported chains
- Risk scoring runs the V3 composite across all metrics
- Anomaly detection, forecasting, and OSINT work without changes

### Removing a coin

Set `"enabled": false` in `assets.json` and restart. The coin remains in historical data but stops refreshing.
