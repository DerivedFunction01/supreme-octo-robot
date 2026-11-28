#!/usr/bin/env bash
# Worktree trim — the deterministic, scripted worktree cap job.
#
# One pass, per in-scope repo (the configured target set —
# see the configuration note below):
#   1. clean: worktree_archive_clean.sh permanently removes
#      every archive whose 1-hour expiry has passed;
#   2. rank + cut: lane worktrees rank by last activity (the
#      newest of last commit time and latest file touch — a
#      progress checkpoint is a file touch in the tree, so it
#      counts by construction); the newest up to the tier cap
#      make the cut, every older tree is trimmed. No held set
#      outranks the cut — see the contract below.
#
# No held set (owner ruling, 2026-11-26, final form):
# the cap binds the whole population. No state outranks
# the cut — not uncommitted or unlanded work, not a live
# process in the tree, not a run record naming the tree
# or its branch, not an explicit .trim-hold or holds.txt
# entry. Every exemption ever added here (dirty and
# unlanded in the 2026-11-21 cure, the venue-transport
# branch hold in the 2026-11-23 cure) became a way to
# keep a surface up indefinitely by claiming it, and the
# population grew behind each one. Preservation rides
# the trim's own mechanisms only:
#   - uncommitted work is AUTO-COMMITTED in place before
#     ranking: the trim commits the tree's full working
#     state (git add -A) on its checked-out branch — for
#     a detached tree, on trim/autocommit-<tree> (the
#     deterministic branch the trim names for that tree;
#     a same-named branch standing at another tip moves
#     the name to trim/autocommit-<tree>-<admin-id>) —
#     with the repo's configured identity and a commit
#     message naming the trim as the actor. A tree that
#     cannot be auto-committed (no identity configured,
#     a switch or commit failure) is reported by name —
#     AUTOCOMMIT-FAILED with its step and reason — and
#     the pass ends partial; its state then rides the
#     archive whole, as the archive always carries the
#     tree.
#   - what the cut takes rides the archive: the tree,
#     its admin directory and index move whole, the
#     branch stands while the archive stands, and
#     restoration inside the grace window is mechanical
#     (ops/worktree_restore.sh).
# After auto-commit, every tree ranks by activity alike:
# the newest up to the tier cap stand, every older tree
# is trimmed. A repo still over cap when the pass
# completes (an archive act failed) is reported by name
# — CAP-OVER — and the pass ends partial: an over-cap
# population is a defect in the trim, never a standing
# condition awaiting an order. The drain act caller
# (WORKTREE_TRIM_DRAIN_ACT=1, supervision plan Step 4)
# is an ordinary caller under this rule.
# Silent when nothing happens. Exit codes: 0 = every repo
# complete; 3 = at least one repo partial (archive failure,
# branch deletion failure, auto-commit failure) with the
# rest complete; 1 = no
# repo could be censused. Both are normal outcomes declared
# in the entries' ok_exit_codes.
#
# Parallelism is processes: the parent backgrounds one worker
# process per repo (this script re-invoked with --worker) and
# merges their result files in fixed repo order, so the
# report is identical regardless of completion order. All
# acts inside a repo are serial in its worker.
#
# A pass is a singleton (2026-11-24 cure): the parent holds
# an flock on $STATE_DIR/trim-pass.lock from before the
# clean until it exits, and a second parent finding it held
# exits 0 silently — one census stands at a time, whatever
# fired the overlap. Workers never take the lock (they are
# the standing pass's own children), and dry runs never
# take it (a read-only census, manually invoked).
#

set -uo pipefail
export GIT_TERMINAL_PROMPT=0

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=paths.sh
. "$OPS_DIR/paths.sh"
export PATH="$SCHED_PATH"

WS_ROOT="$SCHED_WS_ROOT"
ARCHIVE_ROOT="${WORKTREE_ARCHIVE_ROOT:-$WS_ROOT/worktree-archive}"
STATE_DIR="${WORKTREE_TRIM_STATE_DIR:-$SCHED_STATE_DIR/worktree-trim}"
NOW="${WORKTREE_TRIM_NOW:-$(date +%s)}"
TODAY="$(date -d "@$NOW" +%F)"
EXPIRY_EPOCH=$((NOW + 3600))
EXPIRY_ISO="$(date -u -d "@$EXPIRY_EPOCH" +%Y-%m-%dT%H:%M:%SZ)"
REPO_TIMEOUT="${WT_TRIM_REPO_TIMEOUT_SECS:-1200}"
# Branch-deletion kill-switch: WT_TRIM_BRANCH_TRIM=off
# stands the whole branch leg down (no local deletion, no
# queue seeding, no queue draining); tree archiving is not
# affected. Stood down briefly on 2026-11-15 after an
# incident report, then lifted; the default is on.
BRANCH_TRIM="${WT_TRIM_BRANCH_TRIM:-on}"
# The drain act's seam (supervision plan Step 4):
# WORKTREE_TRIM_DRAIN_ACT=1 marks a pass as the workbench
# drain detector's archive act rather than the standing
# census. The pass no longer varies by caller —
# the variable is carried for the drain detector's own
# accounting; see the no-held-set contract in the header.
DRAIN_ACT="${WORKTREE_TRIM_DRAIN_ACT:-}"

# The trim's shared foundation — configuration
# resolution and the config accessors — is sourced
# from ops/trim/; the phase modules follow the argv
# block below.
# shellcheck source=trim/trim_common.sh
. "$OPS_DIR/trim/trim_common.sh"


# Argument surface, declared once and parsed by the
# unified argv contract's bash adapter (contract home:
# pipeline/platform/argv.py; adapter: argv.sh in the
# same home, resolved from this script's own location).
# Both --flag value and --flag=value are the same flag;
# an unknown flag or a value flag missing its value is
# a usage refusal (exit 2); --dry-run is a safety flag
# and is honoured in any position; --help prints the
# usage generated from this declaration.
. "$OPS_DIR/../../platform/argv.sh"
argv_tool worktree_trim.sh "Worktree trim: the deterministic, scripted worktree cap job."
argv_global_flag tier value default=soft
argv_global_flag dry-run bool safety
argv_global_flag worker value
argv_global_flag result-file value
argv_global_flag ledger-file value
argv_parse "$@" || exit 2
[ "$ARGV_HELP" = 1 ] && exit 0

TIER="${ARGV_FLAGS[tier]}"
DRY_RUN=0; [ "${ARGV_FLAGS[dry-run]}" = true ] && DRY_RUN=1
WORKER_REPO="${ARGV_FLAGS[worker]}"
RESULT_FILE="${ARGV_FLAGS[result-file]}"
LEDGER_FILE="${ARGV_FLAGS[ledger-file]}"


# Phase modules: census, archive, branch transport,
# and the branch cap phase. They define functions
# only; the worker below calls them per repo.
# shellcheck source=trim/trim_census.sh
. "$OPS_DIR/trim/trim_census.sh"
# shellcheck source=trim/trim_archive.sh
. "$OPS_DIR/trim/trim_archive.sh"
# shellcheck source=trim/trim_transport.sh
. "$OPS_DIR/trim/trim_transport.sh"
# shellcheck source=trim/trim_branchcap.sh
. "$OPS_DIR/trim/trim_branchcap.sh"

# ------------------------------------------------------------------
# Worker: one repo's whole pass, serial. Appends report lines
# to $RESULT_FILE and ledger lines to $LEDGER_FILE.
# Exit: 0 complete, 3 partial, 2 census error.
# The phase functions (ops/trim/) read the worker's locals (slug,
# main_dir, base_branch, partial) through bash dynamic scoping.
# ------------------------------------------------------------------
run_worker() {
  local slug="$1"
  local main_dir="$WS_ROOT/$slug"
  local partial=0
  : >>"$RESULT_FILE"; : >>"$LEDGER_FILE"

  if [ ! -d "$main_dir" ] || ! $GIT -C "$main_dir" rev-parse --git-dir >/dev/null 2>&1; then
    echo "CENSUS-ERROR repo=$slug reason=not-a-git-repo" >>"$RESULT_FILE"
    return 2
  fi
  local base_branch
  base_branch="$($GIT -C "$main_dir" branch --show-current 2>/dev/null)"
  [ -z "$base_branch" ] && base_branch="main"
  local cap; cap="$(cap_for "$slug")"

  # GitHub pushes ride SSH from this machine: when the account
  # key sits beside the workspace, pin it explicitly (the
  # passwd-entry HOME and the real home can differ by shell).
  local home_dir; home_dir="$(dirname "$WS_ROOT")"
  if [ -f "$home_dir/.ssh/id_ed25519" ]; then
    export GIT_SSH_COMMAND="ssh -i $home_dir/.ssh/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=$home_dir/.ssh/known_hosts"
  fi

  # Principal branches (2026-11-23 cure): the refs the
  # branch leg must never charge, derived from the repo
  # itself at pass start — never a name list in the
  # script. The set is the base branch (the main
  # worktree's own checkout, the ref containment is
  # measured against) plus the remote's default branch
  # (the origin/HEAD symref target, read locally where
  # the clone recorded it, else from the remote itself).
  # In a main-base repo the two coincide; in a dev-base
  # repo they are the two standing refs — main is
  # contained in dev by construction, so without this
  # derivation the sweep and the cap treat the remote's
  # default as ordinary landed material. A third source
  # joins below (2026-11-24): branches the deployment
  # config declares for the repo, for the standing ref
  # neither derivation can see.
  local origin_default=""
  origin_default="$($GIT -C "$main_dir" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null)"
  origin_default="${origin_default#origin/}"
  if [ -z "$origin_default" ] && $GIT -C "$main_dir" remote get-url origin >/dev/null 2>&1; then
    origin_default="$(timeout 60 $GIT -C "$main_dir" ls-remote --symref origin HEAD 2>/dev/null | awk '$1 == "ref:" { sub("^refs/heads/", "", $2); print $2; exit }')"
  fi
  # Declared principals (2026-11-24 cure): the derived
  # pair above cannot see a standing integration branch
  # that is neither the base nor the remote's default —
  # a tenant repo lands through dev while both derivations
  # resolve to main, and the 2026-11-24 hourly pass
  # cap-archived origin dev at 00fb3e09 and deleted the
  # ref. The deployment declares such branches in
  # repos.conf's 4th field (principals_for); they join
  # the principal set for every phase below.
  local -a declared_principals=()
  local dpb
  for dpb in $(principals_for "$slug"); do
    [ -n "$dpb" ] && declared_principals+=("$dpb")
  done


  # Cross-phase state the sourced phase functions
  # share through dynamic scoping: the census row
  # file and its path set (trim_census), the trim set
  # (trim_rank_cut), and the census early-exit flag
  # (a dry-run census ends the worker pass there).
  local rows_file=""
  local -a census_paths=()
  local -a trimset=()
  CENSUS_DONE_EARLY=0

  # --- pass facts (per pass, before the census) -----------------
  # Origin tips for the manifest's record (one read per pass;
  # an unreachable origin simply leaves the map empty).
  declare -A origin_tips=()
  local ob os
  while IFS=$'\t' read -r os ob; do
    [ -n "$ob" ] && origin_tips["${ob#refs/heads/}"]="$os"
  done < <($GIT -C "$main_dir" ls-remote --heads origin 2>/dev/null | head -200)
  # auto_commit_tree <path> <branch>: commits the tree's

  # --- census (ops/trim/trim_census.sh) ------------------------
  trim_census
  [ "$CENSUS_DONE_EARLY" = 1 ] && return 0

  # --- branch trims owed from earlier archives ------------------
  if [ "$BRANCH_TRIM" = "on" ]; then
    seed_branch_queue
    branch_sweep
    drain_queue
  else
    echo "act=branch-standdown repo=$slug epoch=$NOW" >>"$LEDGER_FILE"
  fi

  # --- rank + cut, trim each target (ops/trim/trim_archive.sh) -
  trim_rank_cut
  trim_targets

  # --- cap proof ------------------------------------------------
  # The pass ends with the population at cap, or it says
  # so by name: a repo still over cap here (an archive
  # act failed above) is a defect in the trim, reported
  # as CAP-OVER and partial — never a standing condition.
  local standing; standing=$(( $($GIT -C "$main_dir" worktree list --porcelain 2>/dev/null | grep -c '^worktree ') - 1 ))
  if [ "$standing" -gt "$cap" ]; then
    echo "CAP-OVER repo=$slug live=$standing cap=$cap tier=$TIER" >>"$RESULT_FILE"
    echo "act=cap-over repo=$slug live=$standing cap=$cap tier=$TIER epoch=$NOW" >>"$LEDGER_FILE"
    partial=3
  fi

  # --- origin deletions queued by purges / earlier seeds --------
  if [ "$BRANCH_TRIM" = "on" ]; then
    drain_queue
  fi

  return "$partial"
}

# ------------------------------------------------------------------
# Worker mode: single repo, results straight to stdout files.
# ------------------------------------------------------------------
if [ -n "$WORKER_REPO" ]; then
  run_worker "$WORKER_REPO"
  exit $?
fi

# ------------------------------------------------------------------
# Parent: clean first, then one worker process per repo.
# ------------------------------------------------------------------
mkdir -p "$STATE_DIR"
# Singleton (header note): the lock fd stays open for the
# pass's whole life and closes with the process, so the
# lock releases exactly when the pass ends; workers forked
# below inherit the fd, so a killed parent's orphans keep
# it held until they exit — containment bounded by the
# worker timeout's kill-after grace.
if [ "$DRY_RUN" -eq 0 ]; then
  exec {PASS_LOCK_FD}>"$STATE_DIR/trim-pass.lock"
  flock -n "$PASS_LOCK_FD" || exit 0
fi
if [ "$DRY_RUN" -eq 0 ]; then
  bash "$OPS_DIR/worktree_archive_clean.sh"
else
  bash "$OPS_DIR/worktree_archive_clean.sh" --dry-run
fi

tmpdir="$(mktemp -d)"
declare -A wpids=()
for slug in $REPOS; do
  dry_arg=""
  [ "$DRY_RUN" -eq 1 ] && dry_arg="--dry-run"
  timeout -k 30 "$REPO_TIMEOUT" bash "${BASH_SOURCE[0]}" --worker "$slug" --tier "$TIER" \
    $dry_arg \
    --result-file "$tmpdir/$slug.out" --ledger-file "$tmpdir/$slug.ledger" &
  wpids["$slug"]=$!
done

any_partial=0
any_ok=0
for slug in $REPOS; do
  rc=0
  wait "${wpids[$slug]}" || rc=$?
  if [ ! -f "$tmpdir/$slug.out" ]; then
    echo "WORKER-TIMEOUT repo=$slug reason=no-result-file"
    any_partial=3
    continue
  fi
  cat "$tmpdir/$slug.out"
  case "$rc" in
    0) any_ok=1 ;;
    3) any_ok=1; any_partial=3 ;;
    *) any_partial=3 ;;
  esac
  if [ "$DRY_RUN" -eq 0 ] && [ -f "$tmpdir/$slug.ledger" ]; then
    cat "$tmpdir/$slug.ledger" >>"$STATE_DIR/ledger.jsonl"
  fi
done
rm -rf "$tmpdir"

# --- bundle census (workspace / venue scratch) --------------
# Transport bundles are inside the trim regime (owner
# ruling, 2026-11-26): a bundle is a transport copy, never
# a preservation claim that keeps work outside the branch
# and worktree census — work that exists only inside a
# bundle is unlanded surface, and it lands or is cut at
# its turn like any other. Roots: the venue scratch
# (.wv-scratch, recursive) and the workspace itself to
# depth 3 (top-level bundles and repo scratch such as
# var/), pruning .git internals; the archive root is
# excluded — its packages carry their own expiry. A
# bundle older than the grace (default 24h: transport is
# consumed in minutes; a day-old bundle is dead
# transport) is cut and reported by name. Seams:
# WORKTREE_TRIM_BUNDLE_ROOTS (colon list, replaces both
# roots), WORKTREE_TRIM_BUNDLE_GRACE_SECS.
if [ "$DRY_RUN" -eq 0 ]; then
  bundle_grace="${WORKTREE_TRIM_BUNDLE_GRACE_SECS:-86400}"
  bundle_roots="${WORKTREE_TRIM_BUNDLE_ROOTS:-$WS_ROOT/.wv-scratch:$WS_ROOT}"
  old_ifs="$IFS"; IFS=':'; read -ra broots <<< "$bundle_roots"; IFS="$old_ifs"
  for broot in "${broots[@]}"; do
    [ -d "$broot" ] || continue
    bdepth=8; [ "$broot" = "$WS_ROOT" ] && bdepth=3
    while IFS= read -r bf; do
      case "$bf" in "$ARCHIVE_ROOT"*) continue ;; esac
      bmt="$(stat -c %Y "$bf" 2>/dev/null || echo 0)"
      if [ $((NOW - bmt)) -gt "$bundle_grace" ]; then
        if rm -f "$bf"; then
          echo "BUNDLE-CUT path=$bf age_h=$(( (NOW - bmt) / 3600 ))"
        else
          echo "BUNDLE-CUT-FAILED path=$bf"
          any_partial=3
        fi
      fi
    done < <(find "$broot" -maxdepth "$bdepth" -path '*/.git' -prune -o -name '*.bundle' -type f -print 2>/dev/null)
  done
fi

if [ "$any_partial" -ne 0 ]; then exit 3; fi
if [ "$any_ok" -eq 0 ]; then exit 1; fi
exit 0
