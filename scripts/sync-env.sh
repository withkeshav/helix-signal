#!/usr/bin/env bash
# sync-env.sh — merge .env.example into existing .env, keeping current values for existing keys
set -euo pipefail

ENV_FILE="${1:-.env}"
EXAMPLE_FILE="${2:-.env.example}"

if [ ! -f "$EXAMPLE_FILE" ]; then
  echo "ERROR: $EXAMPLE_FILE not found"
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "Creating $ENV_FILE from $EXAMPLE_FILE ..."
  cp "$EXAMPLE_FILE" "$ENV_FILE"
  echo "Done. Edit $ENV_FILE to set your values."
  exit 0
fi

echo "Merging new keys from $EXAMPLE_FILE into $ENV_FILE ..."

while IFS= read -r line; do
  case "$line" in
    '' | '#'* | ';'*)
      continue
      ;;
  esac
  key="${line%%=*}"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    continue
  fi
  echo "$line" >> "$ENV_FILE"
  echo "  added $key"
done < "$EXAMPLE_FILE"

echo "Done. Existing values preserved."
