#!/bin/bash
# Host-side (WSL) guard for the instance's total disk budget.
# The workspace image is a hard cap; Docker storage has no
# hard cap on the Windows WSL 2 backend, so this guard is the primary
# enforcement for its remaining share: at WARN it logs, at STOP it stops
# the workspace container before the host disk is threatened.
# Cron (WSL): */15 * * * *  $HOME/agent-workspace/disk-guard.sh
set -u
# Argument surface: none. This is the vendored
# refuse-any-argument guard of the unified argv
# contract (contract home: pipeline/platform/argv.py;
# bash adapter: argv.sh in the same home) — vendored,
# not sourced, because setup.sh copies this file OUT
# of the checkout into the instance directory, where
# no adapter stands beside it. Any argument is a usage
# refusal (exit 2); --help prints usage. Sync
# obligation: if the contract's no-argument guard form
# changes in argv.sh, this block changes with it.
if [ $# -gt 0 ]; then
  case "$1" in
    --help|-h)
      echo "usage: disk-guard.sh"
      exit 0
      ;;
    *)
      echo "disk-guard: unexpected argument: $1" >&2
      echo "usage: disk-guard.sh" >&2
      exit 2
      ;;
  esac
fi
DIR="$(cd "$(dirname "$0")" && pwd)"
# Thresholds come from the instance .env when present (cron does not
# inherit the shell env setup.sh wrote them for).
if [ -f "$DIR/.env" ]; then
  DISK_WARN_GB="${DISK_WARN_GB:-$(grep -oP '^DISK_WARN_GB=\K.+' "$DIR/.env" || true)}"
  DISK_STOP_GB="${DISK_STOP_GB:-$(grep -oP '^DISK_STOP_GB=\K.+' "$DIR/.env" || true)}"
fi
WARN_GB="${DISK_WARN_GB:-120}"
STOP_GB="${DISK_STOP_GB:-128}"
LOG="$DIR/disk-guard.log"

ws_kb=$(du -sk "$DIR/workspace" 2>/dev/null | cut -f1); ws_kb=${ws_kb:-0}
img_kb=0
[ -f "$DIR/workspace.img" ] && img_kb=$(du -sk "$DIR/workspace.img" | cut -f1)
docker_bytes=$(docker system df --format '{{.Size}}' 2>/dev/null | head -1)
total_gb=$(( (ws_kb + img_kb) / 1024 / 1024 ))
stamp=$(date -Is)

if [ "$total_gb" -ge "$STOP_GB" ]; then
  echo "$stamp STOP workspace=${ws_kb}K docker-system-df=${docker_bytes:-?} approx-total=${total_gb}G >= ${STOP_GB}G" >> "$LOG"
  (cd "$DIR" && docker compose stop ubuntu) >> "$LOG" 2>&1
elif [ "$total_gb" -ge "$WARN_GB" ]; then
  echo "$stamp WARN workspace=${ws_kb}K docker-system-df=${docker_bytes:-?} approx-total=${total_gb}G >= ${WARN_GB}G" >> "$LOG"
fi
