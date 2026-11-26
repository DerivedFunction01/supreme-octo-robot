#!/usr/bin/env bash
# The scripted detection half of the memory-index-watchdog entry:
# compare ${HOME}/MEMORY.md (sha256 + byte size) against the
# baseline in ${WS}/memory-watch/baseline.sha256. The agent half
# (the cleanup under MAINTENANCE.md) lives in the entry's
# escalate_body and runs only when this check escalates.
#
# Exit codes: 0 = hash and size match the baseline (silence);
# 3 = mismatch (drift — escalate); 4 = baseline missing or
# unparseable (escalate distinctly); 5 = MEMORY.md missing or
# unreadable (escalate); 6 = topic-file threshold overage with
# the index matching (escalate to topic compaction — thresholds
# in MAINTENANCE.md: any one topic file over 40960 bytes, or
# the topic set over topic_file_count x 12800 bytes total (a
# per-topic register, so the set cap scales as topics are
# added); overridable via SCHEDULER_TOPIC_FILE_MAX_BYTES /
# SCHEDULER_TOPIC_PER_FILE_BYTES, with
# SCHEDULER_TOPIC_TOTAL_MAX_BYTES still overriding the
# computed set total outright);
# 7 = a topic file is missing its Locate: routing header with
# the index matching (rule 0a in MAINTENANCE.md — every topic
# file carries one Locate: line near its top).
# 8 = a denylisted literal (the untracked denylist, same
# pattern as tools/portability_scan.py: env
# STARTER_DENYLIST_FILE or the repo's one home,
# pipeline/platform/state/denylist.txt;
# one literal per line, #-comments ignored) appears in a topic
# file, in ${HOME}/AGENTS.md, in MAINTENANCE.md, or in
# MEMORY.md itself, with the index matching (rule 0b in
# MAINTENANCE.md — those files carry
# no personal literals and no quoted speech). Findings report
# file + line count only, never the literal itself.
# 9 = the denylist itself is absent or unreadable with the
# index matching (the check cannot run unprovisioned).
# A topic overage, missing header, or denylist finding riding
# on an index mismatch is appended to the exit-3 line instead.
# Non-zero exits are failures under the
# entry's ok_exit_codes [0], so each escalates with this script's
# one-line output attached.
#
# Paths are derived from this script's own location (portability
# rule: no hardcoded home/workspace paths in tracked files);
# SCHEDULER_MEMORY_FILE / SCHEDULER_BASELINE_FILE override.
set -uo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/paths.sh"
export PATH="$SCHED_PATH"

# Argument surface: none. The empty declaration is
# parsed by the unified argv contract's bash adapter
# (contract home: pipeline/platform/argv.py; adapter:
# argv.sh in the same home, resolved from this script's
# own location): any argument is a usage refusal
# (exit 2); --help prints the generated usage. The
# refusal stands apart from this script's own verdict
# exits (0/3/4/5/6/7) documented above.
. "$SCHED_OPS_DIR/../../platform/argv.sh"
argv_tool memory_watchdog_check.sh "Memory watchdog check: one pass over the memory tree's health."
argv_parse "$@" || exit 2
[ "$ARGV_HELP" = 1 ] && exit 0
REPO_ROOT="$SCHED_REPO_ROOT"
WS_ROOT="${SCHEDULER_WORKSPACE:-$SCHED_WS_ROOT}"
USER_HOME_DIR="$SCHED_USER_HOME_DIR"

MEMORY_FILE="${SCHEDULER_MEMORY_FILE:-$USER_HOME_DIR/MEMORY.md}"
BASELINE_FILE="${SCHEDULER_BASELINE_FILE:-$WS_ROOT/memory-watch/baseline.sha256}"

if [[ ! -r "$BASELINE_FILE" ]]; then
  echo "MEMORY WATCHDOG: BASELINE MISSING - $BASELINE_FILE is absent or unreadable"
  exit 4
fi
base_hash="$(grep -E '^sha256:' "$BASELINE_FILE" | head -1 | sed 's/^sha256:[[:space:]]*//')"
base_bytes="$(grep -E '^bytes:' "$BASELINE_FILE" | head -1 | sed 's/^bytes:[[:space:]]*//')"
if [[ ! "$base_hash" =~ ^[0-9a-f]{64}$ || ! "$base_bytes" =~ ^[0-9]+$ ]]; then
  echo "MEMORY WATCHDOG: BASELINE MISSING - $BASELINE_FILE has no parseable sha256/bytes values"
  exit 4
fi
if [[ ! -r "$MEMORY_FILE" ]]; then
  echo "MEMORY WATCHDOG FAILURE - $MEMORY_FILE is missing or unreadable"
  exit 5
fi
cur_hash="$(sha256sum "$MEMORY_FILE" | cut -d' ' -f1)"
cur_bytes="$(stat -c %s "$MEMORY_FILE")"

TOPICS_DIR="${SCHEDULER_TOPICS_DIR:-$USER_HOME_DIR/memory/topics}"
TOPIC_FILE_MAX="${SCHEDULER_TOPIC_FILE_MAX_BYTES:-40960}"
# The set cap scales with the topic count: total limit =
# topic_file_count x this per-topic register (12800 x 12
# topics = the historical flat 153600). An explicit
# SCHEDULER_TOPIC_TOTAL_MAX_BYTES overrides the computed
# total outright.
TOPIC_PER_FILE="${SCHEDULER_TOPIC_PER_FILE_BYTES:-12800}"
TOPIC_TOTAL_OVERRIDE="${SCHEDULER_TOPIC_TOTAL_MAX_BYTES:-}"
topic_over=""
topic_missing_locate=""
topic_total=0
topic_count=0
if [[ -d "$TOPICS_DIR" ]]; then
  for f in "$TOPICS_DIR"/*.md; do
    [[ -e "$f" ]] || continue
    topic_count=$((topic_count + 1))
    sz="$(stat -c %s "$f")"
    topic_total=$((topic_total + sz))
    if (( sz > TOPIC_FILE_MAX )); then
      topic_over="${topic_over:+$topic_over; }$(basename "$f") is $sz bytes (limit $TOPIC_FILE_MAX)"
    fi
    if ! grep -q '^Locate:' "$f"; then
      topic_missing_locate="${topic_missing_locate:+$topic_missing_locate; }$(basename "$f") has no Locate: header"
    fi
  done
  if [[ -n "$TOPIC_TOTAL_OVERRIDE" ]]; then
    TOPIC_TOTAL_MAX="$TOPIC_TOTAL_OVERRIDE"
    topic_total_limit_desc="limit $TOPIC_TOTAL_MAX"
  else
    TOPIC_TOTAL_MAX=$((topic_count * TOPIC_PER_FILE))
    topic_total_limit_desc="limit $TOPIC_TOTAL_MAX = $topic_count topics x $TOPIC_PER_FILE per-topic"
  fi
  if (( topic_total > TOPIC_TOTAL_MAX )); then
    topic_over="${topic_over:+$topic_over; }topic set totals $topic_total bytes ($topic_total_limit_desc)"
  fi
fi

DENYLIST_FILE="${STARTER_DENYLIST_FILE:-$REPO_ROOT/../platform/state/denylist.txt}"
AGENTS_FILE="${SCHEDULER_AGENTS_FILE:-$USER_HOME_DIR/AGENTS.md}"
MAINTENANCE_FILE="$WS_ROOT/memory-watch/MAINTENANCE.md"
denylist_hits=""
denylist_missing=""
if [[ -r "$DENYLIST_FILE" ]]; then
  deny_tmp="$(mktemp)"
  grep -v '^[[:space:]]*#' "$DENYLIST_FILE" | grep -v '^[[:space:]]*$' > "$deny_tmp" || true
  if [[ -s "$deny_tmp" ]]; then
    deny_files=()
    if [[ -d "$TOPICS_DIR" ]]; then
      for f in "$TOPICS_DIR"/*.md; do
        [[ -e "$f" ]] && deny_files+=("$f")
      done
    fi
    [[ -r "$AGENTS_FILE" ]] && deny_files+=("$AGENTS_FILE")
    [[ -r "$MAINTENANCE_FILE" ]] && deny_files+=("$MAINTENANCE_FILE")
    [[ -r "$MEMORY_FILE" ]] && deny_files+=("$MEMORY_FILE")
    for f in "${deny_files[@]}"; do
      n="$(grep -c -F -f "$deny_tmp" "$f" 2>/dev/null || true)"
      if [[ "${n:-0}" =~ ^[0-9]+$ ]] && (( n > 0 )); then
        denylist_hits="${denylist_hits:+$denylist_hits; }$(basename "$f") has $n denylisted line(s)"
      fi
    done
  fi
  rm -f "$deny_tmp"
else
  denylist_missing="$DENYLIST_FILE is absent or unreadable"
fi

if [[ "$cur_hash" == "$base_hash" && "$cur_bytes" == "$base_bytes" ]]; then
  if [[ -n "$topic_over" ]]; then
    echo "TOPIC OVERAGE: $topic_over (index matches baseline)"
    if [[ -n "$topic_missing_locate" ]]; then
      echo "MISSING LOCATE HEADER: $topic_missing_locate"
    fi
    if [[ -n "$denylist_hits" ]]; then
      echo "DENYLIST HIT: $denylist_hits"
    fi
    if [[ -n "$denylist_missing" ]]; then
      echo "DENYLIST MISSING: $denylist_missing"
    fi
    exit 6
  fi
  if [[ -n "$topic_missing_locate" ]]; then
    echo "MISSING LOCATE HEADER: $topic_missing_locate (index matches baseline)"
    if [[ -n "$denylist_hits" ]]; then
      echo "DENYLIST HIT: $denylist_hits"
    fi
    if [[ -n "$denylist_missing" ]]; then
      echo "DENYLIST MISSING: $denylist_missing"
    fi
    exit 7
  fi
  if [[ -n "$denylist_hits" ]]; then
    echo "DENYLIST HIT: $denylist_hits (index matches baseline)"
    exit 8
  fi
  if [[ -n "$denylist_missing" ]]; then
    echo "DENYLIST MISSING: $denylist_missing (index matches baseline)"
    exit 9
  fi
  echo "match: MEMORY.md equals the baseline (sha256 $cur_hash, $cur_bytes bytes); topic files within thresholds ($topic_total bytes total)"
  exit 0
fi
echo "MISMATCH: MEMORY.md sha256 $cur_hash ($cur_bytes bytes) vs baseline $base_hash ($base_bytes bytes)"
if [[ -n "$topic_over" ]]; then
  echo "TOPIC OVERAGE: $topic_over"
fi
if [[ -n "$topic_missing_locate" ]]; then
  echo "MISSING LOCATE HEADER: $topic_missing_locate"
fi
if [[ -n "$denylist_hits" ]]; then
  echo "DENYLIST HIT: $denylist_hits"
fi
if [[ -n "$denylist_missing" ]]; then
  echo "DENYLIST MISSING: $denylist_missing"
fi
exit 3
