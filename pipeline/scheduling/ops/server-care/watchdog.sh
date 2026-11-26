#!/usr/bin/env bash
# Scheduler server watchdog — the restore ladder the keeper hook
# calls. Conforms to the VM-restart survival pattern, contract v1
# (canonical text: the starter SPEC's supervision contract; each
# repo carries only its conformance, never its own copy of the
# pattern). Rung map for this ladder:
#
#   1. Tracked unit template + installer: the unit is a render of
#      ops/server-care/scheduler-server.service.tmpl, installed
#      by this script.
#   2. External driver: the server cannot drive itself — its named
#      driver is the keeper hook, an external poller (~120 s) that
#      runs this ladder whether or not the server is up (contract:
#      README, "The keeper contract").
#   3. Presence before health (EC-12): the unit file's existence is
#      checked separately from process health; a host replacement
#      can wipe the unit while the process still runs — healthy but
#      unit-gone is a quiet reinstall.
#   4. Render-when-invalid: a present unit that is not byte-equal
#      to the current template render is re-rendered, not merely
#      started — in the healthy branch quietly, in the ladder as
#      its first step. The comparison hashes an in-memory render;
#      the render is never landed to a file for comparison, and a
#      render that fails or is denied classifies the unit UNKNOWN
#      — never stale — so a render failure can never trigger a
#      reinstall against a healthy unit (flap defect, 2026-11-08:
#      a denied flush landed a 0-byte render, cmp failed, and the
#      healthy unit was misread as stale). Installs write a fresh
#      sibling, hash-verify it against the in-memory render, and
#      only then rename it over the unit — a denied or partial
#      stage leaves the installed unit untouched.
#   5. Bounded, detached probes: the health probe runs under an
#      external hard budget (timeout -s KILL) on top of curl's own
#      whole-read limit, so a wedged server (headers sent, body
#      stalled) reads as down and can never wedge the ladder.
#   6. Load-state repair verb: a unit systemd has not loaded gets
#      `start`; a loaded unit gets `restart`.
#   7. Fresh-restore confirmation window: when the ladder installs
#      a missing unit, its first start is confirmed over a long
#      window (180 s) before the attempt counts as failed — a
#      first start may run a startup sweep before the port binds.
#   8. Poll-verified ladder with an episode cap (EC-13): one ladder
#      attempt per episode marker under state/; recovery is proven
#      by polling the health endpoint, never a fixed wait; a spent
#      or failed ladder exits 1 and the keeper's wake escalates.
#   9. Supervision is the verdict: "restored" means health answers
#      after the repair verb acted on the supervised unit — this
#      ladder starts nothing outside the unit, so an answering
#      port is the unit's own process by construction.
#
# Exit 0: server healthy (or restored and verified). A healthy
#         server with an unrepairable-right-now unit (render or
#         write denied) also exits 0 — the server is the verdict;
#         the unit repair is retried on the next poll, never
#         reported as an outage.
# Exit 1: server down and the ladder failed or was already spent
#         for this episode — the keeper's wake escalates.
#
# The repo root is derived from this script's own location
# (portability rule: no hardcoded home/workspace paths in tracked
# files). Test/drill seams (env): SCHEDULER_ROOT, SCHEDULER_UNIT_DIR,
# SCHEDULER_SYSTEMCTL, SCHEDULER_CURL, SCHEDULER_SED,
# SCHEDULER_HEALTH_URL, SCHEDULER_POLL_SECS, SCHEDULER_FRESH_POLL_SECS,
# SCHEDULER_PROBE_SECS, SCHEDULER_PROBE_BUDGET_SECS.
set -uo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/paths.sh"

# Argument surface: none. The empty declaration is
# parsed by the unified argv contract's bash adapter
# (contract home: pipeline/platform/argv.py; adapter:
# argv.sh in the same home, resolved from this script's
# own location): any argument is a usage refusal
# (exit 2); --help prints the generated usage.
. "$SCHED_OPS_DIR/../../platform/argv.sh"
argv_tool watchdog.sh "Scheduler server watchdog: the restore ladder the keeper hook calls."
argv_parse "$@" || exit 2
[ "$ARGV_HELP" = 1 ] && exit 0

ROOT="${SCHEDULER_ROOT:-$SCHED_REPO_ROOT}"
UNIT_NAME="scheduler-server.service"
UNIT_DIR="${SCHEDULER_UNIT_DIR:-/etc/systemd/system}"
SYSTEMCTL="${SCHEDULER_SYSTEMCTL:-systemctl}"
CURL="${SCHEDULER_CURL:-curl}"
SED="${SCHEDULER_SED:-sed}"
POLL_SECS="${SCHEDULER_POLL_SECS:-60}"
FRESH_POLL_SECS="${SCHEDULER_FRESH_POLL_SECS:-180}"
PROBE_SECS="${SCHEDULER_PROBE_SECS:-5}"
PROBE_BUDGET_SECS="${SCHEDULER_PROBE_BUDGET_SECS:-8}"
STATE_DIR="$ROOT/state"
EPISODE_FILE="$STATE_DIR/keeper-episode"
TEMPLATE="$ROOT/ops/server-care/scheduler-server.service.tmpl"
UNIT_FILE="$UNIT_DIR/$UNIT_NAME"

mkdir -p "$STATE_DIR"

port="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("port", 8796))' "$ROOT/config.json" 2>/dev/null || echo 8796)"
HEALTH_URL="${SCHEDULER_HEALTH_URL:-http://127.0.0.1:${port}/health}"

healthy() {
  # Rung 5: curl's --max-time bounds the whole read; the external
  # timeout is a hard budget behind it, so even a hung probe
  # process cannot stall the ladder.
  timeout -s KILL "$PROBE_BUDGET_SECS" "$CURL" --fail --silent \
    --max-time "$PROBE_SECS" "$HEALTH_URL" >/dev/null 2>&1
}

render_unit() {
  "$SED" -e "s|@ROOT@|$ROOT|g" -e "s|@PYTHON@|$(command -v python3)|g" \
      -e "s|@HOME@|$SCHED_USER_HOME_DIR|g" "$TEMPLATE"
}

# The render's hash, computed in memory — the render is never
# written to a file for comparison. Fails (nonzero, no output)
# when the render itself fails or is denied.
render_sha() {
  local sha
  sha="$(render_unit 2>/dev/null | sha256sum)" || return 1
  sha="${sha%% *}"
  [[ -n "$sha" ]] || return 1
  echo "$sha"
}

# Rung 4: missing | stale | current | unknown. A failed render or
# an unreadable unit hashes to UNKNOWN, never to stale.
unit_state() {
  if [[ ! -f "$UNIT_FILE" ]]; then
    echo missing
    return
  fi
  local expected actual
  expected="$(render_sha)" || { echo unknown; return; }
  actual="$(sha256sum "$UNIT_FILE" 2>/dev/null)" || { echo unknown; return; }
  actual="${actual%% *}"
  if [[ "$actual" == "$expected" ]]; then
    echo current
  else
    echo stale
  fi
}

# Stage the render to a fresh sibling, verify its hash against
# the in-memory render, and only then rename it over the unit.
install_unit() {
  local expected staged_sha
  expected="$(render_sha)" || return 1
  render_unit > "$UNIT_FILE.tmp" 2>/dev/null || { rm -f "$UNIT_FILE.tmp"; return 1; }
  staged_sha="$(sha256sum "$UNIT_FILE.tmp" 2>/dev/null)" || { rm -f "$UNIT_FILE.tmp"; return 1; }
  staged_sha="${staged_sha%% *}"
  if [[ "$staged_sha" != "$expected" ]]; then
    rm -f "$UNIT_FILE.tmp"
    return 1
  fi
  mv "$UNIT_FILE.tmp" "$UNIT_FILE" && \
    "$SYSTEMCTL" daemon-reload
}

# Rung 6: the verb follows the unit's load state.
repair_verb() {
  local load_state
  load_state="$("$SYSTEMCTL" show --property=LoadState --value "$UNIT_NAME" 2>/dev/null || echo unknown)"
  if [[ "$load_state" == "loaded" ]]; then
    echo restart
  else
    echo start
  fi
}

if healthy; then
  # Rungs 3 + 4: healthy process, missing or stale unit — repair
  # the unit quietly; the running process is not disturbed. A
  # repair that cannot land right now (render or write denied)
  # is noted and retried next poll; the healthy server is the
  # verdict, so the exit stays 0. An unknown unit state touches
  # nothing at all.
  case "$(unit_state)" in
    missing)
      if install_unit; then
        echo "watchdog: unit file was missing; reinstalled from template"
      else
        echo "watchdog: unit reinstall could not land (render/write unavailable); server healthy — will retry next poll"
      fi
      ;;
    stale)
      if install_unit; then
        echo "watchdog: unit file differed from the template render; re-rendered"
      else
        echo "watchdog: unit re-render could not land (render/write unavailable); server healthy — will retry next poll"
      fi
      ;;
    unknown)
      echo "watchdog: unit render unavailable; unit state unknown — leaving the unit as-is"
      ;;
  esac
  rm -f "$EPISODE_FILE"
  exit 0
fi

# Server is down. One ladder attempt per episode (rung 8 / EC-13).
if [[ -f "$EPISODE_FILE" ]]; then
  echo "watchdog: still down; ladder already attempted for this episode"
  exit 1
fi
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ladder started" > "$EPISODE_FILE"

echo "watchdog: server down; running restore ladder"
state="$(unit_state)"
fresh=0
if [[ "$state" == "missing" ]]; then
  fresh=1
fi
if [[ "$state" == "missing" || "$state" == "stale" ]]; then
  install_unit || { echo "watchdog: unit install failed"; exit 1; }
elif [[ "$state" == "unknown" ]]; then
  echo "watchdog: unit render unavailable; proceeding with the unit as-is"
fi
verb="$(repair_verb)"
"$SYSTEMCTL" "$verb" "$UNIT_NAME" || { echo "watchdog: service $verb failed"; exit 1; }

# Rung 7: a fresh restore confirms over the long window.
window="$POLL_SECS"
if [[ "$fresh" == "1" ]]; then
  window="$FRESH_POLL_SECS"
fi
deadline=$((SECONDS + window))
while (( SECONDS < deadline )); do
  if healthy; then
    rm -f "$EPISODE_FILE"
    echo "watchdog: restored and verified healthy ($verb, ${window}s window)"
    exit 0
  fi
  sleep 2
done
echo "watchdog: ladder failed; server still unhealthy after ${window}s of polling"
exit 1
