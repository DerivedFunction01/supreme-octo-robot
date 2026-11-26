#!/usr/bin/env bash
# Example scripted job: a small daily counts report. Its
# registry entry carries `report: when: always`, so this
# output is delivered as a report ping after every run —
# the pattern for jobs whose output IS the product.
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
argv_tool example_daily_report.sh "Example scripted job: a small daily counts report."
argv_parse "$@" || exit 2
[ "$ARGV_HELP" = 1 ] && exit 0

entries=$(find "$ROOT/jobs" -maxdepth 1 -name '*.yaml' | wc -l)
bodies=$(find "$ROOT/bodies" -maxdepth 1 -name '*.md' | wc -l)

echo "Daily registry report"
echo "entries: $entries"
echo "bodies: $bodies"
echo "generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
