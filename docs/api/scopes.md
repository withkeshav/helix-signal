# API scopes & access policy

Helix API keys use **resource bundles** plus an optional `access_policy` JSON.

## Bundles

| Bundle | Typical routes |
|--------|----------------|
| `core:read` | health, version, dashboard summary |
| `trends:read` | `/api/trends` |
| `events:read` | `/api/events`, timeline events |
| `osint:read` | OSINT headlines / articles |
| `risk:read` | DEWS / risk panels |
| `forensics:read` | blacklist, forensics reads |
| `export:read` | CSV/export endpoints |
| `investigate:write` | `POST /api/v1/investigate` |
| `admin` | full operator powers (rarely issued as a key) |

**Default for new keys:** `core:read` only.

**Legacy:** `intelligence:read` is treated as the union of all `*:read` bundles for back-compat.

## access_policy

```json
{
  "allowed_bundles": ["core:read", "trends:read"],
  "allowed_assets": ["USDT", "USDC"],
  "max_history_hours": 168
}
```

- Empty `allowed_assets` → no asset filter.
- `max_history_hours` clamps `window` / `from` / timeline range.
- Admin session cookie bypasses all clamps.

## Create example

```bash
curl -s -X POST http://localhost/api/v1/api-keys \
  -H "X-Admin-Token: $HELIX_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name":"trends-only",
    "scopes":["trends:read"],
    "access_policy":{
      "allowed_bundles":["trends:read"],
      "allowed_assets":["USDT"],
      "max_history_hours":24
    }
  }'
```

See also `docs/api.md` and Control Room → Security.
