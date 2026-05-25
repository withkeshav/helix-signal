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
    git clone https://github.com/anomalyco/Helix-Signal.git /opt/helix-signal
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

  docker compose -p "${STACK}" build --pull
  docker compose -p "${STACK}" up -d --remove-orphans

  echo "Waiting for backend health..."
  for i in \$(seq 1 30); do
    if curl -sf "${SMOKE_URL}/api/health" > /dev/null 2>&1; then
      echo "Backend healthy after \${i}s"
      break
    fi
    sleep 2
  done

  echo "Running smoke checks..."
  bash scripts/smoke-check.sh "${SMOKE_URL}"

  echo "Pruning old images..."
  docker image prune -f

  echo "=== Deploy complete ==="
ENDSSH
