#!/bin/bash
# Daily cron example: 0 2 * * * /apps/helix-signal/scripts/backup.sh
# Project name MUST match deploy: helix-signal → volumes helix-signal_postgres_data etc.
set -euo pipefail

BACKUP_DIR="${HELIX_BACKUP_DIR:-/mnt/ai-archive/helix-backups}"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS="${HELIX_BACKUP_RETENTION_DAYS:-30}"
PROJECT_DIR="${HELIX_PROJECT_DIR:-/apps/helix-signal}"
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-helix-signal}"
POSTGRES_USER="${POSTGRES_USER:-helix}"
POSTGRES_DB="${POSTGRES_DB:-helix}"

echo "[$(date +%FT%T)] Starting backup to $BACKUP_DIR/$DATE (project=$COMPOSE_PROJECT)"

mkdir -p "$BACKUP_DIR/$DATE"
cd "$PROJECT_DIR"

DC=(docker compose -p "$COMPOSE_PROJECT")

# PostgreSQL (source of truth)
if "${DC[@]}" exec -T postgres pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1; then
  echo "  Backing up PostgreSQL..."
  "${DC[@]}" exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$BACKUP_DIR/$DATE/postgres.sql.gz"
  echo "  PostgreSQL: done ($(du -sh "$BACKUP_DIR/$DATE/postgres.sql.gz" | cut -f1))"
else
  echo "  WARNING: postgres not ready — skipped"
fi

# Redis (optional)
if "${DC[@]}" exec -T redis redis-cli PING >/dev/null 2>&1; then
  echo "  Backing up Redis..."
  "${DC[@]}" exec -T redis redis-cli SAVE >/dev/null 2>&1 || true
  VOL_SRC=$("${DC[@]}" volume inspect "${COMPOSE_PROJECT}_redis_data" -f '{{.Mountpoint}}' 2>/dev/null || true)
  if [ -n "${VOL_SRC:-}" ] && [ -f "$VOL_SRC/dump.rdb" ]; then
    cp "$VOL_SRC/dump.rdb" "$BACKUP_DIR/$DATE/redis.rdb" 2>/dev/null || true
  fi
  echo "  Redis: done"
fi

# App data volume (DuckDB / models) — Compose-prefixed name
echo "  Backing up helix_data volume..."
if docker volume inspect "${COMPOSE_PROJECT}_helix_data" >/dev/null 2>&1; then
  docker run --rm \
    -v "${COMPOSE_PROJECT}_helix_data:/data:ro" \
    -v "$BACKUP_DIR/$DATE:/out" \
    alpine tar czf /out/helix_data.tar.gz -C /data . 2>/dev/null \
    || echo "  WARNING: helix_data tar failed"
else
  echo "  WARNING: volume ${COMPOSE_PROJECT}_helix_data not found"
fi

# Configuration
cp "$PROJECT_DIR/.env" "$BACKUP_DIR/$DATE/env.backup" 2>/dev/null || true
mkdir -p "$BACKUP_DIR/$DATE/config"
cp "$PROJECT_DIR/config/"*.json "$BACKUP_DIR/$DATE/config/" 2>/dev/null || true

# Prune old backups
find "$BACKUP_DIR" -maxdepth 1 -type d -name "20*" -mtime +$RETENTION_DAYS -exec rm -rf {} \; 2>/dev/null || true

echo "Backup size: $(du -sh "$BACKUP_DIR/$DATE" | cut -f1)"
echo "Backup complete: $DATE" >> "$BACKUP_DIR/backup.log"
echo "[$(date +%FT%T)] Backup complete — $BACKUP_DIR/$DATE"
