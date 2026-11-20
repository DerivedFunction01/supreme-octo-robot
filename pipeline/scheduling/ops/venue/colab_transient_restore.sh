#!/usr/bin/env bash
# Composed command for the colab-runner-transient-restore entry:
# the job's two duties, in order, exactly as its cron body
# prescribes. The server captures output; the entry's report rule
# (on_failure + verify-failed fail pattern + release report
# patterns) decides what reaches the main thread.
#
# Paths are derived from this script's own location (portability
# rule: no hardcoded home/workspace paths in tracked files):
# WS_ROOT is the workspace root, overridable via SCHEDULER_WORKSPACE.
set -uo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/paths.sh"
REPO_ROOT="$SCHED_REPO_ROOT"
WS_ROOT="${SCHEDULER_WORKSPACE:-$SCHED_WS_ROOT}"

python3 "$WS_ROOT/colab-runner/ops/mirror_transient.py" restore
restore_rc=$?
if [[ $restore_rc -ne 0 ]]; then
  exit $restore_rc
fi

python3 "$WS_ROOT/colab-runner/bin/colab-lease" reap
exit $?
