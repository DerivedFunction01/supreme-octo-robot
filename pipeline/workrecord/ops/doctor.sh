#!/usr/bin/env bash
# wb doctor --post runner: the periodic consistency
# sweep over every swept project. Invoked by the
# scheduler registry's doctor entry every 15 minutes;
# the scheduler server is the cron (this VM has no
# unix crontab binary and no daemon), in the same
# shape as the other periodic runners.
#
# wb's exit code is propagated: 0 = clean, 1 = findings
# (both normal — a changed finding set is delivered by
# the doctor itself as a digest through the outbox);
# anything above 1 is a crash. Output appends to
# state/doctor.log (runtime state, untracked).
set -uo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"

# Argument surface: none. The empty declaration is
# parsed by the unified argv contract's bash adapter
# (contract home: pipeline/platform/argv.py; adapter:
# argv.sh in the same home, resolved from this script's
# own location): any argument is a usage refusal
# (exit 2); --help prints the generated usage. The
# refusal stands apart from wb's propagated exit code
# below.
. "$ROOT/../platform/argv.sh"
argv_tool doctor.sh "wb doctor --post runner: the periodic consistency sweep."
argv_parse "$@" || exit 2
[ "$ARGV_HELP" = 1 ] && exit 0
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
mkdir -p "$ROOT/state"
LOG="$ROOT/state/doctor.log"
{
  echo "== $(date -Is) wb doctor --post"
  (cd "$ROOT" && "$PY" wb doctor --post)
  rc=$?
  echo "exit=$rc"
  exit "$rc"
} >> "$LOG" 2>&1
