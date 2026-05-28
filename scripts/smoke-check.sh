#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:3000}"

echo "Running smoke checks against ${BASE_URL}"

html="$(curl -fsSL "${BASE_URL}/")"
for marker in 'x-data="helixApp"' 'class="top-nav"' 'class="kpi-row"' 'class="time-range"' 'id="chart-trend-signal"'; do
  if ! printf '%s' "${html}" | grep -F "${marker}" >/dev/null; then
    echo "FAILED: frontend marker missing -> ${marker}"
    exit 1
  fi
done
echo "OK: frontend shell markers present"

app_status="$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/js/init.js")"
if [[ "${app_status}" != "200" ]]; then
  echo "FAILED: /js/init.js returned ${app_status}"
  exit 1
fi
echo "OK: /js/init.js reachable"

health_json="$(curl -fsSL "${BASE_URL}/api/health")"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert "status" in d and "version" in d; print("OK: /api/health -> status={}, version={}".format(d.get("status"), d.get("version")))' <<< "${health_json}"

dashboard_status="$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/api/dashboard?asset=USDT")"
if [[ "${dashboard_status}" != "200" ]]; then
  echo "FAILED: /api/dashboard returned ${dashboard_status}"
  exit 1
fi
echo "OK: /api/dashboard reachable"

settings_code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/api/settings")"
if [[ "${settings_code}" != "403" && "${settings_code}" != "503" ]]; then
  echo "FAILED: /api/settings should require admin token (got ${settings_code})"
  exit 1
fi
echo "OK: /api/settings requires auth (${settings_code})"

governance_code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/api/governance?asset=USDT")"
if [[ "${governance_code}" != "403" && "${governance_code}" != "503" ]]; then
  echo "FAILED: /api/governance should require admin token (got ${governance_code})"
  exit 1
fi
echo "OK: /api/governance requires auth (${governance_code})"

metrics_code="$(curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/metrics")"
if [[ "${metrics_code}" == "200" ]]; then
  echo "FAILED: /metrics should not be publicly exposed"
  exit 1
fi
echo "OK: /metrics is not publicly exposed (${metrics_code})"

echo "Smoke checks passed."
