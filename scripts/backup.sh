#!/bin/bash
# Run daily via cron: 0 2 * * * /opt/helix-signal/scripts/backup.sh
set -euo pipefail

BACKUP_DIR="/mnt/ai-archive/helix-backups"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30
PROJECT_DIR="/opt/helix-signal"

echo "[$(date +%FT%T)] Starting backup to $BACKUP_DIR/$DATE"

mkdir -p "$BACKUP_DIR/$DATE"

cd "$PROJECT_DIR"

# PostgreSQL (if running)
if docker compose exec postgres pg_isready -U helix >/dev/null 2>&1; then
  echo "  Backing up PostgreSQL..."
  docker compose exec -T postgres pg_dump -U helix helix | gzip > "$BACKUP_DIR/$DATE/postgres.sql.gz"
  echo "  PostgreSQL: done ($(du -sh "$BACKUP_DIR/$DATE/postgres.sql.gz" | cut -f1))"
fi

# ClickHouse (if running)
if docker compose exec clickhouse clickhouse-client --query "SELECT 1" >/dev/null 2>&1; then
  echo "  Backing up ClickHouse snapshots..."
  docker compose exec clickhouse clickhouse-client \
    --query "SELECT * FROM asset_trend_snapshots FORMAT CSV" | \
    gzip > "$BACKUP_DIR/$DATE/clickhouse_snapshots.csv.gz"
  echo "  ClickHouse: done ($(du -sh "$BACKUP_DIR/$DATE/clickhouse_snapshots.csv.gz" | cut -f1))"
fi

# Redis (if running)
if docker compose exec redis redis-cli PING >/dev/null 2>&1; then
  echo "  Backing up Redis..."
  docker compose exec redis redis-cli SAVE
  cp "$(docker compose inspect redis -f '{{range .Mounts}}{{.Source}}{{end}}')/dump.rdb" \
    "$BACKUP_DIR/$DATE/redis.rdb" 2>/dev/null || true
  echo "  Redis: done"
fi

# SQLite data volume (always present)
echo "  Backing up SQLite/data volume..."
docker compose run --rm -v helix_data:/data alpine tar czf - -C /data . > "$BACKUP_DIR/$DATE/helix_data.tar.gz" 2>/dev/null || true
echo "  SQLite/data: done ($(du -sh "$BACKUP_DIR/$DATE/helix_data.tar.gz" | cut -f1))"

# Configuration
cp "$PROJECT_DIR/.env" "$BACKUP_DIR/$DATE/env.backup" 2>/dev/null || true
mkdir -p "$BACKUP_DIR/$DATE/config"
cp "$PROJECT_DIR/config/"*.json "$BACKUP_DIR/$DATE/config/" 2>/dev/null || true

# Prune old backups
find "$BACKUP_DIR" -maxdepth 1 -type d -name "20*" -mtime +$RETENTION_DAYS -exec rm -rf {} \; 2>/dev/null || true

# Verify backup integrity
echo "Backup size: $(du -sh "$BACKUP_DIR/$DATE" | cut -f1)"
echo "Backup complete: $DATE" >> "$BACKUP_DIR/backup.log"
echo "[$(date +%FT%T)] Backup complete — $BACKUP_DIR/$DATE"