# trim_common.sh — the worktree trim's shared foundation:
# configuration resolution and the config accessors every
# phase reads (cap_for, principals_for, branch_cap_for,
# iso_of, is_in). Sourced by ops/worktree_trim.sh before
# the argv block; never executed standalone.
#
# Paths derive from this script's location via ops/paths.sh.
# Overrides (tests, fixtures): SCHEDULER_WORKSPACE (via
# paths.sh), WORKTREE_ARCHIVE_ROOT, WORKTREE_TRIM_STATE_DIR,
# WORKTREE_TRIM_REPOS, WORKTREE_TRIM_NOW (epoch, fake clock),
# WT_TRIM_CAP_<SLUG>, WT_TRIM_REPO_TIMEOUT_SECS,
# WORKTREE_TRIM_DRAIN_ACT (the drain act's seam: marks
# the pass as the workbench drain detector's archive act;
# the pass is the ordinary one — see the header),
# WT_TRIM_BRANCH_CAP_<SLUG> / WT_TRIM_BRANCH_CAP (the
# branch-population cap's env seams — see below).
#
# Configuration: the target set and its per-repo caps are
# deployment data, not code — they live in the untracked
# config file repos.conf in the state dir (one line per
# repo: <slug> <soft-cap> <deep-cap> [principals];
# WORKTREE_TRIM_CONFIG names another file). The optional
# 4th field names the repo's declared principal branches
# (comma-separated, no spaces) — the standing refs the
# deployment protects beside the derived pair (header
# point 7). The environment overrides win
# (WORKTREE_TRIM_REPOS for the set, WT_TRIM_CAP_<SLUG> per
# cap). With no config at all, only the repo hosting this
# script is in scope, under the generic tier caps
# (soft 10, deep 5).
#
# The branch-population cap (header point 7) resolves
# through its own chain, in this order:
# WT_TRIM_BRANCH_CAP_<SLUG> (per-repo env), then
# WT_TRIM_BRANCH_CAP (global env), then the generic
# configured soft cap, 10. repos.conf's per-repo rows are
# worktree-tier caps only; they are NOT repurposed for the
# branch cap.

CONFIG_FILE="${WORKTREE_TRIM_CONFIG:-$STATE_DIR/repos.conf}"
if [ -n "${WORKTREE_TRIM_REPOS:-}" ]; then
  REPOS="$WORKTREE_TRIM_REPOS"
elif [ -f "$CONFIG_FILE" ]; then
  REPOS="$(grep -v '^[[:space:]]*#' "$CONFIG_FILE" | awk 'NF {print $1}' | paste -sd' ' -)"
  [ -n "$REPOS" ] || REPOS="$(basename "$(dirname "$(dirname "$(dirname "$OPS_DIR")")")")"
else
  REPOS="$(basename "$(dirname "$(dirname "$(dirname "$OPS_DIR")")")")"
fi
GIT="git -c core.fsync=none"
export GIT_AUTHOR_DATE="@$NOW +0000" GIT_COMMITTER_DATE="@$NOW +0000"

cap_for() {
  # Per-repo cap: env override wins; then the deployment
  # config's per-tier cap for the repo; then the generic
  # tier defaults (soft 10, deep 5).
  local slug="$1" var def cfg=""
  var="WT_TRIM_CAP_$(echo "$slug" | tr 'a-z-' 'A-Z_')"
  def="$(eval echo "\${$var:-}")"
  if [ -n "$def" ]; then echo "$def"; return; fi
  if [ -f "$CONFIG_FILE" ]; then
    if [ "$TIER" = "deep" ]; then
      cfg="$(awk -v s="$slug" '$1==s {print $3}' "$CONFIG_FILE" | head -1)"
    else
      cfg="$(awk -v s="$slug" '$1==s {print $2}' "$CONFIG_FILE" | head -1)"
    fi
    if [ -n "$cfg" ]; then echo "$cfg"; return; fi
  fi
  if [ "$TIER" = "deep" ]; then echo 5; else echo 10; fi
}

principals_for() {
  # Declared principal branches for a repo (2026-11-24
  # cure): repos.conf's optional 4th field, a
  # comma-separated list of standing branches the
  # deployment names as principals beside the derived
  # pair (the base branch and the remote's default) —
  # e.g. an integration branch a programme lands through
  # that is neither. The declaration is deployment data
  # in the same untracked config that names the target
  # set and the caps; the script carries no branch-name
  # literals. Absent field, absent file: no output.
  local slug="$1" cfg=""
  if [ -f "$CONFIG_FILE" ]; then
    cfg="$(awk -v s="$slug" '$1==s {print $4}' "$CONFIG_FILE" | head -1)"
  fi
  [ -n "$cfg" ] && printf '%s' "$cfg" | tr ',' ' '
  return 0
}

branch_cap_for() {
  # Branch-population cap (header point 7): per-repo env
  # WT_TRIM_BRANCH_CAP_<SLUG> wins; then the global env
  # WT_TRIM_BRANCH_CAP; then the generic configured soft
  # cap, 10. Deliberately NOT cap_for(): repos.conf's rows
  # are worktree-tier caps and stay out of this chain.
  local slug="$1" var def
  var="WT_TRIM_BRANCH_CAP_$(echo "$slug" | tr 'a-z-' 'A-Z_')"
  def="$(eval echo "\${$var:-}")"
  if [ -n "$def" ]; then echo "$def"; return; fi
  if [ -n "${WT_TRIM_BRANCH_CAP:-}" ]; then echo "$WT_TRIM_BRANCH_CAP"; return; fi
  echo 10
}

iso_of() { date -u -d "@$1" +%Y-%m-%dT%H:%M:%SZ; }

is_in() { local x="$1"; shift; local y; for y in "$@"; do [ "$y" = "$x" ] && return 0; done; return 1; }

