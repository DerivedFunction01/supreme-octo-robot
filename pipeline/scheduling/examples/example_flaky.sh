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
MARKER="$ROOT/state/flaky-on"

if [[ -f "$MARKER" ]]; then
  echo "flaky check: marker present, simulated dependency is DOWN"
  exit 1
fi
echo "flaky check: simulated dependency is up"
