#!/usr/bin/env bash
# Example scripted job: a small daily counts report. Its
# registry entry carries `report: when: always`, so this
# output is delivered as a report ping after every run —
# the pattern for jobs whose output IS the product.
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

entries=$(find "$ROOT/jobs" -maxdepth 1 -name '*.yaml' | wc -l)
bodies=$(find "$ROOT/bodies" -maxdepth 1 -name '*.md' | wc -l)

echo "Daily registry report"
echo "entries: $entries"
echo "bodies: $bodies"
echo "generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
