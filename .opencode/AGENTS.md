# Helix Signal — Project Instructions

## Deployment Flow

1. Code changes go in `/mnt/ai-archive/Github-repo/Helix-Signal/`
2. Commit and push to GitHub: `git push origin main`
3. Give user deploy instructions:

```bash
# On the target server (e.g. root@srv1691089):
cd /apps/helix-signal
git pull origin main
docker compose up -d --build
```

Verify:
```bash
docker ps --filter name=helix
curl -sf http://localhost/api/health | python3 -m json.tool
```

## Known: TimesFM restart loop

**Symptom:** `helix-timesfm` shows `Restarting (N) X seconds ago`.

**Cause:** Container has `read_only: true` but the TimesFM model downloads to `~/.cache/huggingface/` on first load. That path is read-only without a writable volume.

**Fix:** `helix_timesfm_cache` volume at `/root/.cache/huggingface` in docker-compose.yml. Model downloads into volume on first deploy; subsequent starts use cache.

If it still fails, check:
```bash
docker logs helix-timesfm
docker compose logs timesfm
```

## Ollama Cloud AI

The `_ollama_cloud()` provider now uses `https://ollama.com/v1/chat/completions` (OpenAI-compatible) with `OLLAMA_API_KEY`. Default model: `ministral-3:8b-cloud` (Level 1 — minimal Pro quota).

Three AI features: `risk_explain` (existing), `market_narrative` (sentiment + events), `insight_summary` (supply + chains + anomalies). All gated by `AI_MODE`.

### Onboarding for new deployments

1. User generates API key at https://ollama.com/settings/keys
2. Adds to `.env`: `OLLAMA_API_KEY=ok-...`, `AI_MODE=ai_lite`
3. Redeploys: `docker compose up -d --build`

## Internal deployment guide

See `docs/internal_docs_deployment_guide.md` for full details (gitignored, not in repo).
