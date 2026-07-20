# Adding a Stablecoin

Adding a new stablecoin to Helix-Signal takes **3 steps** - all configuration, zero code.

## Automated Pipeline (Recommended)

The easiest way to add a new stablecoin is to use the automated script:

```bash
# From the project root directory
python scripts/add_stablecoin.py <symbol> <name> [defillama_symbol] [peg_type]
```

Example:
```bash
python scripts/add_stablecoin.py USDD "Decentralized USD" USDD peggedUSD
```

This script will:
1. Validate the asset configuration
2. Add the asset to `config/assets.json`
3. Update the README with the new asset
4. Provide instructions for restarting services

## Manual Process

If you prefer to add assets manually, follow these steps:

### Step 1: Add to assets.json

```json
// config/assets.json
{
  "symbol": "NEWCOIN",
  "name": "New Stablecoin",
  "enabled": true,
  "peg_type": "peggedUSD",
  "defillama_symbol": "NEWCOIN"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `symbol` | Yes | Uppercase ticker (2-16 alphanumeric chars) |
| `name` | Yes | Human-readable name |
| `enabled` | Yes | `true` to show in UI and refresh cycle |
| `peg_type` | Yes | `"peggedUSD"` for USD stablecoins |
| `defillama_symbol` | Yes | Symbol DeFiLlama uses (auto-resolved) |
| `default` | No | Set to `true` for default asset in UI |

### Step 2: Add DexScreener Addresses (Optional)

If the stablecoin is available on DEXes, add its contract addresses to `backend/sources/dexscreener.py`:

```python
STABLECOIN_ADDRESSES: dict[str, list[tuple[str, str]]] = {
    "ethereum": [
        # ... existing entries
        ("NEWCOIN", "0x..."),  # Contract address
    ],
    # ... other chains
}
```

### Step 3: Restart the backend

```bash
docker compose restart backend
```

Or for local dev, reload (uvicorn auto-reload detects config changes).

## Verification

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

## Rate Limiting Considerations

When adding new assets, be mindful of API rate limits:

- **DexScreener**: 120 calls per minute
- **CoinGecko**: 100 calls per minute

Each asset added will increase the number of API calls. The system is designed to handle up to 4-5 major stablecoins without issues.

## Troubleshooting

1. **Asset not appearing in UI**: Check that `"enabled": true` and restart backend
2. **Data not loading**: Check backend logs for errors with `docker compose logs backend`
3. **Rate limit errors**: Reduce number of assets or increase refresh interval
