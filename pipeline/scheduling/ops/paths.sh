# Shared path derivation for the ops tree — the ONE home
# (shell counterpart of ops/paths.py; sourced, never copied,
# by every ops shell script). No script computes its own root.
#
# Derivation: this file lives at the ops root. The scheduling
# root is found by walking up from here to the directory
# holding jobs/ + server/ — depth-independent. The workspace
# root is found by a second walk: up from the scheduling root
# to the mega-repo root (the ancestor holding pipeline/ +
# apps/), whose parent is the workspace. A tree with no
# mega-repo ancestor (a fixture copy standing alone) falls
# back to the original one-level-up derivations.
#
# Exports: SCHED_OPS_DIR, SCHED_REPO_ROOT, SCHED_WS_ROOT,
# SCHED_USER_HOME_DIR, SCHED_STATE_DIR, SCHED_REGISTRY_DIR,
# SCHED_PATH.

SCHED_OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

_sched_d="$SCHED_OPS_DIR"
while [ ! -d "$_sched_d/jobs" ] || [ ! -d "$_sched_d/server" ]; do
  if [ "$_sched_d" = "/" ] || [ -z "$_sched_d" ]; then
    _sched_d="$(dirname "$SCHED_OPS_DIR")"
    break
  fi
  _sched_d="$(dirname "$_sched_d")"
done
# A marker found at the walk's end is the root; the loop's
# fallback already replaced _sched_d when no marker exists.
if [ -d "$_sched_d/jobs" ] && [ -d "$_sched_d/server" ]; then
  SCHED_REPO_ROOT="$_sched_d"
else
  SCHED_REPO_ROOT="$(dirname "$SCHED_OPS_DIR")"
fi
unset _sched_d

_sched_m="$(dirname "$SCHED_REPO_ROOT")"
while [ "$_sched_m" != "/" ] && [ -n "$_sched_m" ]; do
  if [ -d "$_sched_m/pipeline" ] && [ -d "$_sched_m/apps" ]; then
    break
  fi
  _sched_m="$(dirname "$_sched_m")"
done
if [ -d "$_sched_m/pipeline" ] && [ -d "$_sched_m/apps" ]; then
  SCHED_WS_ROOT="$(dirname "$_sched_m")"
else
  SCHED_WS_ROOT="$(dirname "$SCHED_REPO_ROOT")"
fi
unset _sched_m
# The server's exported workspace anchor wins when present.
if [ -n "${SCHEDULER_WORKSPACE:-}" ]; then
  SCHED_WS_ROOT="$SCHEDULER_WORKSPACE"
fi
SCHED_USER_HOME_DIR="$(dirname "$SCHED_WS_ROOT")"
SCHED_STATE_DIR="$SCHED_REPO_ROOT/state"
SCHED_REGISTRY_DIR="$SCHED_REPO_ROOT/registry"

# The one PATH anchor for the ops tree: a sourcing script
# exports PATH="$SCHED_PATH" instead of restating a literal.
# The home bin dir leads — the platform's own tools install
# there (uv and its tool shims) and are unfindable under the
# bare system default in non-login shells, the recorded
# failure class this anchor exists to cure.
SCHED_PATH="$SCHED_USER_HOME_DIR/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# Direct-execution guard: sourced (the intended use),
# this file declares no argument surface of its own —
# argv belongs to the consuming script, which parses
# it under the unified argv contract after sourcing, so
# no guard can stand here on a consumer's behalf.
# Executed directly, it takes no arguments: the empty
# declaration is parsed by the contract's bash adapter
# (contract home: pipeline/platform/argv.py; adapter:
# argv.sh in the same home), and any argument is a
# usage refusal (exit 2).
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  . "$SCHED_OPS_DIR/../../platform/argv.sh"
  argv_tool paths.sh "Shared path derivation for the ops tree (sourced, never executed)."
  argv_parse "$@" || exit 2
  if [ "$ARGV_HELP" = 1 ]; then exit 0; fi
fi
