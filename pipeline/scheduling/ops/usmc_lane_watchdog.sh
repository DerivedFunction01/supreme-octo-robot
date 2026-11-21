#!/usr/bin/env bash
# Composed command for the usmc-lane-watchdog entry: the venue
# lane watchdog ladder (platform.lane_watchdog), one attempt
# per episode — repo root as cwd, venv python.
#
# Paths are derived from this script's own location (portability
# rule: no hardcoded home/workspace paths in tracked files):
# WS_ROOT is the workspace root, overridable via SCHEDULER_WORKSPACE.
set -uo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$OPS_DIR")"
WS_ROOT="${SCHEDULER_WORKSPACE:-$(dirname "$REPO_ROOT")}"

cd "$WS_ROOT/usmc-pay-monitor-v2" || exit 1
exec "$WS_ROOT/usmc-pay-monitor-v2/var/venv/bin/python" -m platform.lane_watchdog
