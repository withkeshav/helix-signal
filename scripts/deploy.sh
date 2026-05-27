#!/usr/bin/env bash
set -euo pipefail

echo "=== Helix Signal Deploy ==="

REMOTE="${HELIX_DEPLOY_REMOTE:-${1:-}}"
if [ -z "${REMOTE}" ]; then
  echo "ERROR: set HELIX_DEPLOY_REMOTE or pass remote as first argument"
  exit 1
fi
STACK="${HELIX_DEPLOY_STACK:-${2:-helix-signal}}"
BRANCH="${HELIX_DEPLOY_BRANCH:-${3:-main}}"
SMOKE_URL="${HELIX_SMOKE_URL:-http://localhost:8000}"

echo "Target: ${REMOTE}"
echo "Stack: ${STACK}"
echo "Branch: ${BRANCH}"
echo "Smoke URL: ${SMOKE_URL}"

# Ensure local is clean
if ! git diff --quiet --exit-code; then
  echo "ERROR: uncommitted changes. Commit or stash first."
  exit 1
fi

echo "Pushing to remote..."
git push origin "${BRANCH}"

echo "Connecting to ${REMOTE}..."
ssh "${REMOTE}" bash -s << ENDSSH
  set -euo pipefail

  cd /opt/helix-signal || {
    echo "First time — cloning repo..."
    git clone https://github.com/withkeshav/helix-signal.git /opt/helix-signal
    cd /opt/helix-signal
  }

  git fetch origin
  git checkout "${BRANCH}"
  git pull origin "${BRANCH}"

  if [ -f .env ]; then
    echo ".env exists — preserving"
  else
    echo "WARNING: no .env found! Copy from .env.example"
  fi

  echo "Backing up current state..."
  bash scripts/backup.sh 2>/dev/null || echo "  (backup skipped — non-fatal)"

  echo "Saving previous image IDs for rollback..."
  docker compose -p "${STACK}" images -q | sort -u > /tmp/helix-previous-images.txt 2>/dev/null || true

  docker compose -p "${STACK}" build --pull
  docker compose -p "${STACK}" up -d --remove-orphans

  echo "Waiting for backend health..."
  HEALTHY=false
  for i in \$(seq 1 30); do
    if curl -sf "${SMOKE_URL}/api/health" > /dev/null 2>&1; then
      echo "Backend healthy after \${i}s"
      HEALTHY=true
      break
    fi
    sleep 2
  done

  rollback() {
    echo "ERROR: \$1. Rolling back..."
    docker compose -p "${STACK}" down --remove-orphans
    if [ -f /tmp/helix-previous-images.txt ]; then
      while read -r img_id; do
        [ -n "\$img_id" ] && docker tag "\$img_id" "\$(docker inspect --format '{{.RepoTags}}' "\$img_id" 2>/dev/null | tr -d '[]' | cut -d' ' -f1)" 2>/dev/null || true
      done < /tmp/helix-previous-images.txt
    fi
    docker compose -p "${STACK}" up -d
    echo "Rollback complete — previous images restored and containers restarted."
    exit 1
  }

  if [ "\$HEALTHY" != "true" ]; then
    rollback "backend did not become healthy"
  fi

  echo "Running smoke checks..."
  if ! bash scripts/smoke-check.sh "${SMOKE_URL}"; then
    rollback "smoke check failed"
  fi

  echo "Pruning old images..."
  docker image prune -f

  echo "=== Deploy complete ==="
ENDSSH
