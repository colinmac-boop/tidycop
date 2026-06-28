#!/usr/bin/env bash
# refresh_site.sh — scheduled refresh of citycrimemap.us.
#
# Pipeline:
#   1) fetch fresh incidents via tidycop (rule-based, no LLM, no tokens)
#   2) regenerate static HTML
#   3) deploy to Vercel production
#
# Designed for launchd. Cron-equivalent without surprises:
#   * absolute paths everywhere (launchd has a minimal PATH)
#   * own log file with rotation
#   * single-instance lock so a slow run can't trip the next one
#   * exits non-zero on any failure so launchd records it
#
# Token-cost guarantee: this script invokes only deterministic Python
# (tidycop + tidycop-spotcrime, both rule-based) plus the Vercel CLI.
# No OpenAI/Anthropic/etc. API calls are made by anything in this path.

set -euo pipefail

REPO="/Users/mac/Projects/tidycop"
VENV_PY="$REPO/.venv/bin/python"
VERCEL_BIN="/opt/homebrew/bin/vercel"
LOG_DIR="$REPO/logs"
LOG_FILE="$LOG_DIR/refresh.log"
LOCK_FILE="$LOG_DIR/refresh.lock"
MAX_LOG_BYTES=$((2 * 1024 * 1024))   # 2 MB before rotation

mkdir -p "$LOG_DIR"

# Rotate log if it has grown past the cap.
if [[ -f "$LOG_FILE" ]]; then
  size=$(stat -f%z "$LOG_FILE" 2>/dev/null || echo 0)
  if (( size > MAX_LOG_BYTES )); then
    mv "$LOG_FILE" "$LOG_FILE.1"
  fi
fi

# Single-instance lock via flock (provided by util-linux on macOS via
# /opt/homebrew). Fall back to a noclobber file lock if flock missing.
exec_with_lock() {
  if command -v flock >/dev/null 2>&1; then
    exec 9>"$LOCK_FILE"
    if ! flock -n 9; then
      echo "[$(date -Iseconds)] refresh: another run is in progress, skipping" >> "$LOG_FILE"
      exit 0
    fi
  else
    if ! ( set -o noclobber; : > "$LOCK_FILE" ) 2>/dev/null; then
      echo "[$(date -Iseconds)] refresh: lock file present, skipping" >> "$LOG_FILE"
      exit 0
    fi
    trap 'rm -f "$LOCK_FILE"' EXIT
  fi
}
exec_with_lock

{
  echo
  echo "==============================================================="
  echo "[$(date -Iseconds)] refresh: start"
  echo "==============================================================="

  cd "$REPO"

  echo "[refresh] step 1/3 fetch_data.py"
  "$VENV_PY" web/scripts/fetch_data.py

  echo "[refresh] step 2/3 generate_site.py"
  "$VENV_PY" web/scripts/generate_site.py

  echo "[refresh] step 3/3 vercel --prod"
  cd web/pages
  # --yes accepts the project link non-interactively; .vercel/project.json
  # already pins the citymaps project so no prompts should appear.
  "$VERCEL_BIN" --prod --yes

  echo "[$(date -Iseconds)] refresh: done"
} >> "$LOG_FILE" 2>&1
