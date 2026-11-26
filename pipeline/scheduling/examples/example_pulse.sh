#!/usr/bin/env bash
# Example scripted job: a heartbeat pulse. Prints one
# timestamped line and exits 0. The simplest possible entry
# in the registry — copy it when admitting a real job.
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"

# Argument surface: none. The empty declaration is
# parsed by the unified argv contract's bash adapter
# (contract home: pipeline/platform/argv.py; adapter:
# argv.sh in the same home, resolved from this script's
# own location): any argument is a usage refusal
# (exit 2); --help prints the generated usage.
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/../platform/argv.sh"
argv_tool example_pulse.sh "Example scripted job: a heartbeat pulse."
argv_parse "$@" || exit 2
[ "$ARGV_HELP" = 1 ] && exit 0

echo "pulse ok at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
