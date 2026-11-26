#!/usr/bin/env bash
# Example keeper poller — one half of the keeper contract
# (the contract itself is specified in the README's Setup
# section; read it before adapting this file). The keeper
# hook this implements is the scheduler server's named
# external driver under the VM-restart survival pattern,
# contract v1 (see the README's keeper contract).
#
# The keeper is the ONE recurring mechanism outside the
# server. Whatever platform hosts it, it must:
#
#   1. Poll the server on a short cadence (~120 s).
#   2. Health half: GET /health. On failure, restore the
#      server — reinstall its supervisor unit from
#      ops/server-care/scheduler-server.service.tmpl and start
#      it (the ladder in ops/server-care/watchdog.sh), verify
#      by polling health,
#      and attempt the ladder at most once per outage
#      episode.
#   3. Wake half: GET /pings/wakeable. Deliver each wakeable
#      ping to the operator's agent surface, which works it
#      (an agent-due ping by following its body under
#      bodies/, an escalation or report ping by relaying it)
#      and acknowledges it with `bin/sched ack <ping-id>`.
#      Unworked work is never acked.
#
# This script implements the health half by delegating to
# the watchdog ladder, and prints the wakeable pings as
# JSON — the delivery mechanism is the platform's choice
# (on the reference platform a hosted hook runs this poll
# and wakes the agent surface itself). Wire the printed
# pings to your surface, or replace this file with your
# platform's equivalent.
#
# Exit 0: server healthy. Exit 1: server down and the
# ladder failed or was already spent for this episode.
set -uo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/paths.sh"
export PATH="$SCHED_PATH"

# Argument surface: none. The empty declaration is
# parsed by the unified argv contract's bash adapter
# (contract home: pipeline/platform/argv.py; adapter:
# argv.sh in the same home, resolved from this script's
# own location): any argument is a usage refusal
# (exit 2); --help prints the generated usage.
. "$SCHED_OPS_DIR/../../platform/argv.sh"
argv_tool keeper_poller.sh "Example keeper poller: the scheduler server's named external driver."
argv_parse "$@" || exit 2
[ "$ARGV_HELP" = 1 ] && exit 0

ROOT="$SCHED_REPO_ROOT"

port="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("port", 8796))' "$ROOT/config.json" 2>/dev/null || echo 8796)"
BASE="http://127.0.0.1:${port}"

# Health half: the watchdog ladder restores and verifies.
bash "$ROOT/ops/server-care/watchdog.sh"
health_rc=$?

# Wake half (delivery left to the platform): print what an
# agent surface would be woken for.
wakeable="$(curl --fail --silent --max-time 5 "$BASE/pings/wakeable" 2>/dev/null || true)"
if [[ -n "$wakeable" ]]; then
  echo "keeper: wakeable pings: $wakeable"
fi

exit $health_rc
