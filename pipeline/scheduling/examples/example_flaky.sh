#!/usr/bin/env bash
# Example scripted job: a check that can fail, demonstrating
# the escalation pattern. While the marker file
# state/flaky-on exists (relative to the repo root), the
# check fails with exit 1; its registry entry reports on
# failure with an escalation body, so a ping carrying
# bodies/example-flaky-check-escalation.md is raised for an
# agent to work. Toggle it:
#
#   touch state/flaky-on    # the check starts failing
#   rm state/flaky-on       # the check passes again
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Argument surface: none. The empty declaration is
# parsed by the unified argv contract's bash adapter
# (contract home: pipeline/platform/argv.py; adapter:
# argv.sh in the same home, resolved from this script's
# own location): any argument is a usage refusal
# (exit 2); --help prints the generated usage.
. "$ROOT/../platform/argv.sh"
argv_tool example_flaky.sh "Example scripted job: a check that can fail, demonstrating the escalation pattern."
argv_parse "$@" || exit 2
[ "$ARGV_HELP" = 1 ] && exit 0

MARKER="$ROOT/state/flaky-on"

if [[ -f "$MARKER" ]]; then
  echo "flaky check: marker present, simulated dependency is DOWN"
  exit 1
fi
echo "flaky check: simulated dependency is up"
