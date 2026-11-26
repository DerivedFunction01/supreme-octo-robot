#!/usr/bin/env bash
# Venue trim dispatch — the hourly cadence half of the
# venue-form trim (owner ruling, 2026-11-26: the same
# trim system maintains both local venues' disk on the
# same automatic cadence, no manual ask). Dispatches the
# venue-trim runner job to each local venue, waits for
# each pass inside a bound, and prints each venue's
# report as this job's own output: per-surface
# before/after counts and every act line, so an over-cap
# venue is visible in the pass record the hour it
# happens. A venue that cannot be reached or whose pass
# ends partial is named (VENUE-TRIM-DISPATCH-FAILED /
# VENUE-TRIM-REPORT-MISSING, or the report's own non-zero
# VENUE-TRIM-EXIT) and this script ends partial (3) —
# a silent exemption is the defect this system exists to
# remove.
#
# Exit codes: 0 = both venues trimmed and at cap;
# 3 = partial (a venue unreachable, unreported, or its
# pass partial).
set -uo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=paths.sh
. "$OPS_DIR/paths.sh"
REPO_ROOT="$(cd "$OPS_DIR/../../.." && pwd)"
LOCAL_RUN="$REPO_ROOT/pipeline/venue/bin/local-run"
# The report read rides the runner's own SSH transport.
# The identity is a deployment binding, never a literal
# in tracked code: the env override wins; the default
# derives from the workspace root the paths spine
# provides (the workspace is a direct child of the
# operator's home, where the keypair lives).
SSH_IDENTITY="${VENUE_TRIM_SSH_IDENTITY:-$(dirname "$SCHED_WS_ROOT")/.ssh/id_ed25519}"
SSH_KNOWN_HOSTS="$(dirname "$SSH_IDENTITY")/known_hosts"

partial=0

dispatch() {
  # $1 = runner job, $2 = ssh port, $3 = venue label.
  local out run_id report
  if ! out="$("$LOCAL_RUN" "$1" --detach 2>&1)"; then
    echo "VENUE-TRIM-DISPATCH-FAILED venue=$3 job=$1"
    partial=3
    return
  fi
  run_id="$(printf %s "$out" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("run_id",""))' 2>/dev/null)"
  if [ -z "$run_id" ]; then
    echo "VENUE-TRIM-DISPATCH-FAILED venue=$3 reason=no-run-id"
    partial=3
    return
  fi
  "$LOCAL_RUN" --wait "$run_id" --max=1500 >/dev/null 2>&1 || true
  report="$(ssh -p "$2" -i "$SSH_IDENTITY" \
    -o UserKnownHostsFile="$SSH_KNOWN_HOSTS" \
    -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 \
    agent@127.0.0.1 "cat runs/$run_id/trim-report.txt" 2>/dev/null)"
  if [ -z "$report" ]; then
    echo "VENUE-TRIM-REPORT-MISSING venue=$3 run=$run_id"
    partial=3
    return
  fi
  echo "== venue $3 run $run_id:"
  printf '%s\n' "$report"
  case "$report" in
    *"VENUE-TRIM-EXIT rc=0"*) : ;;
    *) partial=3 ;;
  esac
}

dispatch venue-trim 2222 local-main
dispatch venue-trim-hp 2223 hp-envy
exit "$partial"
