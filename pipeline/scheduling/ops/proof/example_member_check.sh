#!/usr/bin/env bash
# Example member-system wrapper — the pattern a composed
# command follows when a registry entry's real work lives in
# another system on the same machine:
#
# - derive every path from this script's own location (a
#   restart may reset PATH and cwd, never the script's path);
# - set PATH explicitly;
# - do the work, and let the exit code speak: 0 = healthy,
#   non-zero = the failure the entry's report rule describes.
#
# A real wrapper would change into the member system's tree
# (a sibling of this repo, reached via the workspace root —
# the parent of this repo) and run its check there. This
# example stays inside the repo so a fresh install runs it
# unchanged.
set -euo pipefail
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"

. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/paths.sh"

# Argument surface: none. The empty declaration is
# parsed by the unified argv contract's bash adapter
# (contract home: pipeline/platform/argv.py; adapter:
# argv.sh in the same home, resolved from this script's
# own location): any argument is a usage refusal
# (exit 2); --help prints the generated usage.
. "$SCHED_OPS_DIR/../../platform/argv.sh"
argv_tool example_member_check.sh "Example member-system wrapper: the composed-command pattern."
argv_parse "$@" || exit 2
[ "$ARGV_HELP" = 1 ] && exit 0

ROOT="$SCHED_REPO_ROOT"

echo "example member check: repo at $ROOT"
echo "example member check: ok"
