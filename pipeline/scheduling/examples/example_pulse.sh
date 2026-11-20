#!/usr/bin/env bash
# Example scripted job: a heartbeat pulse. Prints one
# timestamped line and exits 0. The simplest possible entry
# in the registry — copy it when admitting a real job.
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"

echo "pulse ok at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
