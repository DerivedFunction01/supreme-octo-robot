#!/usr/bin/env bash
# Start/stop the lease control UI server.
#   ui/ui.sh start|stop|restart|status
# Standalone panel runs only: in the consolidated tree the panel
# is served by the repo-root run.py serve-venue under the
# panel's own venue unit (pipeline/platform/ops/
# venue.service.tmpl), and this script's nohup + pidfile path
# is the standalone form. If venue.service is installed on the
# host, every verb delegates to systemctl — the unit is the
# supervisor, and a second nohup instance must never race it
# for the port. That delegation is also what the panel's
# Restart-server action rides: ui.sh restart restarts
# venue.service only, never the coupled workhorse unit. The
# pidfile and log live in the lease var dir (VENUE_RUNNER_VAR,
# default <repo>/var) alongside the lease state they control.
# Test seams (env): VENUE_UI_UNIT_DIR, VENUE_UI_SYSTEMCTL.
set -euo pipefail

UI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$UI_DIR")"
# The panel's actor identity for the core's session shape gate
# (the systemd unit carries the same claim in its Environment).
export VENUE_LEASE_ACTOR=panel
VAR_DIR="${VENUE_RUNNER_VAR:-${COLAB_RUNNER_VAR:-$REPO/var}}"  # step6-retire: COLAB_ dual-read fallback
PIDFILE="$VAR_DIR/lease-ui.pid"
LOG="$VAR_DIR/lease-ui.log"
PORT="${VENUE_LEASE_UI_PORT:-${COLAB_LEASE_UI_PORT:-8793}}"  # step6-retire: COLAB_ dual-read fallback
UNIT_NAME="venue.service"
UNIT_DIR="${VENUE_UI_UNIT_DIR:-${COLAB_UI_UNIT_DIR:-/etc/systemd/system}}"  # step6-retire: COLAB_ dual-read fallback
SYSTEMCTL="${VENUE_UI_SYSTEMCTL:-${COLAB_UI_SYSTEMCTL:-systemctl}}"  # step6-retire: COLAB_ dual-read fallback

unit_installed() {
  [[ -f "$UNIT_DIR/$UNIT_NAME" ]]
}

service_active() {
  "$SYSTEMCTL" is-active --quiet "$UNIT_NAME" 2>/dev/null
}

ui_pid() {
  if [[ -f "$PIDFILE" ]]; then
    local pid
    pid="$(cat "$PIDFILE")"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      printf '%s' "$pid"
      return 0
    fi
  fi
  return 1
}

# Argument surface: the four verbs, declared once and
# parsed by the unified argv contract's bash adapter
# (contract home: pipeline/platform/argv.py; adapter:
# argv.sh in the same home, resolved from this script's
# own location). An unknown verb, any flag, or a surplus
# argument is a usage refusal (exit 2); --help prints
# the usage generated from this declaration.
. "$UI_DIR/../../platform/argv.sh"
argv_tool ui.sh "Start/stop the lease control UI server."
argv_verb start "Start the UI server."
argv_verb stop "Stop the UI server."
argv_verb restart "Restart the UI server."
argv_verb status "Report whether the UI server is running."
argv_parse "$@" || exit 2
[ "$ARGV_HELP" = 1 ] && exit 0

case "$ARGV_VERB" in
  start)
    if unit_installed; then
      if service_active; then
        echo "lease-ui already running (systemd $UNIT_NAME) on http://127.0.0.1:$PORT"
        exit 0
      fi
      "$SYSTEMCTL" start "$UNIT_NAME"
      sleep 1
      if service_active; then
        echo "lease-ui started (systemd $UNIT_NAME) on http://127.0.0.1:$PORT — log: $LOG"
      else
        echo "lease-ui failed to start via systemd; see $LOG" >&2
        exit 1
      fi
      exit 0
    fi
    if pid="$(ui_pid)"; then
      echo "lease-ui already running (pid $pid) on http://127.0.0.1:$PORT"
      exit 0
    fi
    mkdir -p "$VAR_DIR"
    nohup /usr/bin/python3 "$UI_DIR/server.py" >>"$LOG" 2>&1 &
    echo $! > "$PIDFILE"
    sleep 1
    if pid="$(ui_pid)"; then
      echo "lease-ui started (pid $pid) on http://127.0.0.1:$PORT — log: $LOG"
    else
      echo "lease-ui failed to start; see $LOG" >&2
      exit 1
    fi
    ;;
  stop)
    if unit_installed; then
      if service_active; then
        "$SYSTEMCTL" stop "$UNIT_NAME"
        echo "lease-ui stopped (systemd $UNIT_NAME)"
      else
        echo "lease-ui is not running"
      fi
      rm -f "$PIDFILE"
      exit 0
    fi
    if pid="$(ui_pid)"; then
      kill "$pid"
      rm -f "$PIDFILE"
      echo "lease-ui stopped (pid $pid)"
    else
      echo "lease-ui is not running"
      rm -f "$PIDFILE"
    fi
    ;;
  restart)
    # Brief pause first: when the restart is triggered over HTTP
    # (POST /api/server/restart), the requesting server is this very
    # process — the pause lets its response land before the stop does.
    sleep 1
    if unit_installed; then
      "$SYSTEMCTL" restart "$UNIT_NAME"
      echo "lease-ui restarted (systemd $UNIT_NAME)"
      exit 0
    fi
    "$0" stop
    "$0" start
    ;;
  status)
    if unit_installed; then
      if service_active; then
        echo "lease-ui running (systemd $UNIT_NAME) on http://127.0.0.1:$PORT"
      else
        echo "lease-ui not running"
      fi
      exit 0
    fi
    if pid="$(ui_pid)"; then
      echo "lease-ui running (pid $pid) on http://127.0.0.1:$PORT"
    else
      echo "lease-ui not running"
    fi
    ;;
esac
