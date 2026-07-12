#!/usr/bin/env bash
# Smoke-test driver for simple_fast_api.
# Launches the FastAPI server, hits a handful of endpoints, then shuts it down.
#
# Usage:
#   ./smoke.sh                 # safe mode: TELEGRAM_BOT_TOKEN blanked, no live bot polling
#   ENABLE_BOT=1 ./smoke.sh    # full mode: starts real Telegram polling using .env's token
#   COMPANY=삼성전자 ./smoke.sh  # override the company used for the data-endpoint checks
#
# Run from anywhere; the script cd's to its own project root (simple_fast_api/).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$PROJECT_DIR"

PORT="${PORT:-8000}"
BASE_URL="http://127.0.0.1:${PORT}"
LOG_FILE="/tmp/simple_fast_api_smoke.log"
COMPANY="${COMPANY:-삼성전자}"
ENABLE_BOT="${ENABLE_BOT:-0}"

if [ ! -d .venv ]; then
  echo "[setup] creating venv..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

if [ "$ENABLE_BOT" = "1" ]; then
  echo "[launch] starting server WITH live Telegram polling (uses TELEGRAM_BOT_TOKEN from .env)"
  nohup python main.py > "$LOG_FILE" 2>&1 &
else
  echo "[launch] starting server with bot polling disabled (TELEGRAM_BOT_TOKEN blanked for this run)"
  TELEGRAM_BOT_TOKEN="" nohup python main.py > "$LOG_FILE" 2>&1 &
fi
SERVER_PID=$!
echo "[launch] pid=$SERVER_PID log=$LOG_FILE"

cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "[wait] polling for readiness..."
for i in $(seq 1 60); do
  if curl -sf -m 2 "$BASE_URL/" > /dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -sf -m 2 "$BASE_URL/" > /dev/null 2>&1; then
  echo "[fail] server did not become ready within 60s — check $LOG_FILE"
  tail -n 40 "$LOG_FILE"
  exit 1
fi

echo
echo "=== GET / ==="
curl -s "$BASE_URL/"
echo
echo "=== GET /cache/status ==="
curl -s "$BASE_URL/cache/status"
echo
echo
echo "=== GET /dividend-data/${COMPANY} ==="
curl -s -m 20 "$BASE_URL/dividend-data/$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$COMPANY")"
echo
echo
echo "=== GET /valuation/${COMPANY} ==="
curl -s -m 20 "$BASE_URL/valuation/$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$COMPANY")"
echo

echo
echo "[done] smoke test complete. Stopping server."
