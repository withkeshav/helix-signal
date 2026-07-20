# Adding a Chain

Adding a new chain takes **2 steps** - configuration only.

## Step 1: Add to chains.json

```json
// config/chains.json
"newchain": {
  "name": "New Chain",
  "key": "newchain",
  "enabled": true,
  "loader": "evm",
  "explorer_api": "https://api.newscan.io/api",
  "rpc_endpoint": "https://rpc.newchain.io"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Display name |
| `key` | Yes | Unique chain identifier (lowercase, hyphenated) |
| `enabled` | Yes | `true` to include in refresh |
| `loader` | Yes | `"evm"` for EVM-compatible, `"solana"` for Solana, etc. |
| `explorer_api` | For governance | Etherscan-compatible API URL for contract monitoring |
| `rpc_endpoint` | For on-chain | RPC URL (optional, used for chain-specific loaders) |

Then add the chain key to any asset's `chains` list in `assets.json`:

```json
// config/assets.json
"USDC": {
  "chains": ["ethereum", "solana", "newchain"]
}
```

## Step 2: Restart

```bash
docker compose restart backend
```

The chain appears in the UI, DeFiLlama queries it for the associated assets, and the supply distribution table updates automatically.
