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
#      make the cut, every older tree is trimmed — subject to
#      the held set below, which outranks the cut entirely.
#
# Held set (2026-11-21 cure, owner commission through the
# workhorse seat): a tree is HELD — never archived, and not
# counted against the cap — while any of these stands:
#   - dirty: uncommitted or untracked state in the tree
#     (git status --porcelain non-empty). The pre-cure trim
#     archived dirty trees whole; an uncommitted cure in one
#     (Edgar W-P3NORM-1) was lost when its archive expired.
#   - unlanded: the head carries commits the base branch
#     does not (ahead > 0 / not merged). The census always
#     computed this and the pre-cure trim ignored it: the
#     2026-11-21 cycles archived the Steam DF-NEXT-101
#     exceptions formation at ahead=5, merged=0 — twice in
#     one night — and the 111/112/113-114 form trees the
#     same way, each mid-gate. A terminal gate record's
#     tree is unlanded until its seat lands it, so this
#     hold is also the unconsumed-terminal-record hold:
#     the record's consumption ends in a landing or an
#     abandonment, and both clear the hold mechanically.
#   - live: a process holds the tree (cwd or an open fd
#     under it, the /proc scan — the formation-clone
#     sweeper's precedent), or a non-terminal venue run
#     record names the tree's path.
#   - held: a seat's explicit hold — a .trim-hold file at
#     the tree root, or the tree's path in the state dir's
#     holds.txt (one absolute path per line).
# Every held tree prints one HELD line naming its reasons;
# a lane reading the ping learns its tree was at risk and
# why it stands.
#   - the drain act exception (supervision plan Step 4):
#     the workbench drain detector rides this worker for a
#     programme's archive act (WORKTREE_TRIM_DRAIN_ACT=1),
#     and under that caller the unlanded reason does not
#     stand. The drain fires only on a drained transition
#     — every todo on the programme's bundle done, nothing
#     doing, on the programme's own record — which is the
#     evidence the trees' unlanded commits are finished
#     work, and the archive stays recoverable inside its
#     grace window (the branch stands while the archive
#     stands; restore is the verb above). The census never
#     sets the flag, so the hold binds it exactly as cured;
#     dirty, live, and explicit holds still bind a drain
#     pass — uncommitted state and in-flight processes are
#     invisible to the drain's precondition, so they keep
#     their protection under every caller.
#   3. trim = move the worktree directory itself into the
#      archive folder with mv, together with its git admin
#      directory (.git/worktrees/<id> — it holds the index,
#      so staged state moves too, and moving both back is a
#      complete restore; a bare mv + prune would orphan the
#      admin entry and destroy the index). The archive is a
#      folder holding tree/, worktree-admin/, and a
#      manifest.txt carrying expiry = now + 1 hour. No
#      merging anywhere: no union tree, no bundle, no patch
#      extraction. Each archived tree prints one ARCHIVED
#      line — the archive ping's content: the owning lane
#      has that hour to move back what it actually needs.
#   4. branches: an archived tree's branch is NOT trimmed
#      while its archive stands (2026-11-21 cure — the
#      pre-cure trim deleted the branch locally and queued
#      its origin deletion in the same act as the archive,
#      which killed the registration and turned every
#      restore into a drill). The branch trim lands at
#      purge time instead: the clean script, before
#      removing an expired archive, enqueues the branch in
#      the per-repo origin-deletion retry queue
#      (state/worktree-trim/remote-pending-<repo>.txt) and
#      deletes the local branch when it still points at
#      the manifest's recorded head (a branch a seat moved
#      since is left standing, and the PURGED line says
#      so). The queue drains at worker start and end — a
#      failed origin deletion stays queued and is retried
#      next pass. The queue seeds from archive manifests
#      only when the archive itself no longer stands (the
#      crash window: a tree removed by hand without a
#      purge); a standing archive's manifest seeds nothing.
#      A tree restored inside the hour is a rescue: its
#      manifest is skipped while its path stands as a
#      registered worktree again. Restoration is mechanical
#      — ops/worktree_restore.sh <archive-dir> performs the
#      whole sequence (branch re-created at the recorded
#      head when missing, tree and admin directory moved
#      back, registration and head verified) and prints
#      RESTORED or the exact failing step.
#      Restore semantics (2026-11-18): the move-back in
#      point 3 is a complete restore only while the tree's
#      registration survives. Where the registration is
#      dropped in the same act — the branch deleted locally
#      under point 4, the admin entry gone with the archive —
#      move-back alone does NOT restore the worktree. The
#      restore guarantee in that case is the shared object
#      store's retention of the tip commit: recovery is
#      re-creating the branch at its exact recorded tip
#      (the manifest's restore_3) and pushing it to origin.
#      Proven by the Steam Power Stage 4 restoration: four
#      live formation worktrees archived by the trim, their
#      registrations dead with the archive, recovered from
#      the four tips surviving as unreferenced commits in
#      the shared object store.
#      Second instance (2026-11-18, Steam Power, deep-trim
#      archive): the archive package itself (tree/ +
#      manifest.txt + worktree-admin/) does not restore as
#      a worktree by move-back — the .git file inside tree/
#      arrives broken. Restoration is re-registration
#      against the branch: the branch re-created at its
#      recorded tip from the object store, the archive tree
#      verified byte-identical against it (diff 0), then
#      the redundant archive copy removed. The archive is
#      a comparison copy, not a restorable worktree.
#   5. no branch is exempt by NAME: whatever their name or
#      state, branches trim when their trees' archives
#      expire — a formation that needs its branch lands it.
#      (A keeper exemption for formation union branches plus
#      a pins file stood briefly on 2026-11-15 and was
#      removed the same day by the owner's ruling: no
#      carve-out.) The held set above is not a name
#      carve-out: it is work state (dirty, unlanded, live,
#      explicitly held), it lapses mechanically when the
#      state clears, and it binds every tree equally. The
#      branch leg carries a kill-switch
#      (WT_TRIM_BRANCH_TRIM, default on): it stood the leg
#      down on 2026-11-15 after an incident report until
#      the flip back; setting it to off re-imposes the
#      stand-down (no purge-time branch acts, no queue
#      seeding or draining; tree archiving is unaffected).
#
# Silent when nothing happens. Exit codes: 0 = every repo
# complete; 3 = at least one repo partial (archive failure,
# branch deletion failure) with the rest complete; 1 = no
# repo could be censused. Both are normal outcomes declared
# in the entries' ok_exit_codes.
#
# Parallelism is processes: the parent backgrounds one worker
# process per repo (this script re-invoked with --worker) and
# merges their result files in fixed repo order, so the
# report is identical regardless of completion order. All
# acts inside a repo are serial in its worker.
#
# Paths derive from this script's location via ops/paths.sh.
# Overrides (tests, fixtures): SCHEDULER_WORKSPACE (via
# paths.sh), WORKTREE_ARCHIVE_ROOT, WORKTREE_TRIM_STATE_DIR,
# WORKTREE_TRIM_REPOS, WORKTREE_TRIM_NOW (epoch, fake clock),
# WT_TRIM_CAP_<SLUG>, WT_TRIM_REPO_TIMEOUT_SECS,
# WORKTREE_TRIM_PROC_ROOT (the live-process scan's /proc),
# WORKTREE_TRIM_RUNS_DIR (venue run records for the
# live-run hold; default: the venue package's results/runs
# derived from this script's location in the mega repo),
# WORKTREE_TRIM_DRAIN_ACT (the drain act's seam: the
# unlanded hold reason does not stand for that pass).
#
# Configuration: the target set and its per-repo caps are
# deployment data, not code — they live in the untracked
# config file repos.conf in the state dir (one line per
# repo: <slug> <soft-cap> <deep-cap>; WORKTREE_TRIM_CONFIG
# names another file). The environment overrides win
# (WORKTREE_TRIM_REPOS for the set, WT_TRIM_CAP_<SLUG> per
# cap). With no config at all, only the repo hosting this
# script is in scope, under the generic tier caps
# (soft 10, deep 5).
set -uo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export GIT_TERMINAL_PROMPT=0

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=paths.sh
. "$OPS_DIR/paths.sh"

WS_ROOT="$SCHED_WS_ROOT"
ARCHIVE_ROOT="${WORKTREE_ARCHIVE_ROOT:-$WS_ROOT/worktree-archive}"
STATE_DIR="${WORKTREE_TRIM_STATE_DIR:-$SCHED_STATE_DIR/worktree-trim}"
PROC_ROOT="${WORKTREE_TRIM_PROC_ROOT:-/proc}"
RUNS_DIR="${WORKTREE_TRIM_RUNS_DIR:-$(cd "$OPS_DIR/../.." 2>/dev/null && pwd)/venue/results/runs}"
HOLDS_FILE="$STATE_DIR/holds.txt"
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
# census. Under it the unlanded hold reason does not
# stand — see the held-set note in the header.
DRAIN_ACT="${WORKTREE_TRIM_DRAIN_ACT:-}"
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

TIER="soft"
DRY_RUN=0
WORKER_REPO=""
RESULT_FILE=""
LEDGER_FILE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --tier) TIER="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --worker) WORKER_REPO="$2"; shift 2 ;;
    --result-file) RESULT_FILE="$2"; shift 2 ;;
    --ledger-file) LEDGER_FILE="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

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

iso_of() { date -u -d "@$1" +%Y-%m-%dT%H:%M:%SZ; }

is_in() { local x="$1"; shift; local y; for y in "$@"; do [ "$y" = "$x" ] && return 0; done; return 1; }

# ------------------------------------------------------------------
# Worker: one repo's whole pass, serial. Appends report lines
# to $RESULT_FILE and ledger lines to $LEDGER_FILE.
# Exit: 0 complete, 3 partial, 2 census error.
# Helper functions below read the worker's locals (slug,
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

  # --- branch-trim queue helpers -------------------------------
  queue_file() { echo "$STATE_DIR/remote-pending-$slug.txt"; }

  enqueue_branch() {
    local qf; qf="$(queue_file)"
    mkdir -p "$STATE_DIR"
    touch "$qf"
    grep -Fxq "$1" "$qf" || echo "$1" >>"$qf"
  }

  # The push target for origin deletions: the origin URL with
  # any github.com HTTPS form rewritten to the SSH form this
  # machine pushes over; anything else (SSH form, local path)
  # passes through unchanged. Empty when the repo has no
  # origin — remote trimming is then vacuous.
  push_url() {
    local u
    u="$($GIT -C "$main_dir" remote get-url origin 2>/dev/null)" || { echo ""; return; }
    case "$u" in
      git@github.com:*) echo "$u" ;;
      https://github.com/*)
        local p="${u#https://github.com/}"; p="${p%.git}"
        echo "git@github.com:${p}.git" ;;
      *) echo "$u" ;;
    esac
  }

  trim_local_branch() {
    # $1 = branch. Silent success when the ref is already gone.
    $GIT -C "$main_dir" show-ref --verify --quiet "refs/heads/$1" || return 0
    if $GIT -C "$main_dir" branch -D "$1" >/dev/null 2>&1; then
      echo "BRANCH-TRIMMED repo=$slug branch=$1 scope=local" >>"$RESULT_FILE"
      echo "act=branch-trim repo=$slug branch=$1 scope=local epoch=$NOW" >>"$LEDGER_FILE"
      return 0
    fi
    echo "BRANCH-LOCAL-FAIL repo=$slug branch=$1 reason=branch-delete-failed" >>"$RESULT_FILE"
    return 1
  }

  drain_queue() {
    local qf; qf="$(queue_file)"
    [ -f "$qf" ] && [ -s "$qf" ] || return 0
    local url; url="$(push_url)"
    if [ -z "$url" ]; then : >"$qf"; return 0; fi
    local keep; keep="$(mktemp)"
    local b out rc
    while IFS= read -r b; do
      [ -z "$b" ] && continue
      out="$(timeout 60 $GIT -C "$main_dir" ls-remote --heads "$url" "refs/heads/$b" 2>/dev/null)"; rc=$?
      if [ "$rc" -ne 0 ]; then
        echo "$b" >>"$keep"
        echo "BRANCH-REMOTE-FAIL repo=$slug branch=$b reason=origin-unreachable" >>"$RESULT_FILE"
        partial=3
        continue
      fi
      if [ -z "$out" ]; then continue; fi  # already gone on origin
      if timeout 120 $GIT -C "$main_dir" push "$url" --delete "$b" >/dev/null 2>&1; then
        echo "BRANCH-TRIMMED repo=$slug branch=$b scope=origin" >>"$RESULT_FILE"
        echo "act=branch-trim repo=$slug branch=$b scope=origin epoch=$NOW" >>"$LEDGER_FILE"
      else
        echo "$b" >>"$keep"
        echo "BRANCH-REMOTE-FAIL repo=$slug branch=$b reason=origin-delete-failed" >>"$RESULT_FILE"
        partial=3
      fi
    done <"$qf"
    mv "$keep" "$qf"
  }

  # Seed the queue from archive manifests whose archive no
  # longer stands (both the sibling manifests and the
  # in-tree manifests of the retired bundle format): the
  # archive's purge is what normally discharges the branch
  # trim (the clean script enqueues before removing), so a
  # manifest whose archive still stands seeds NOTHING —
  # its rescue window is open and its branch stands with
  # it (2026-11-21 cure). Seeding remains for the crash
  # window: an archive removed by hand, unpurged, its
  # branch still owed the trim — unless the owner rescued
  # the tree, in which case its path stands registered
  # again and the manifest is skipped. Runs against the
  # census path set, so it executes after the census
  # below; declared here with the helpers.
  seed_branch_queue() {
    local mf b mp adir
    for mf in "$ARCHIVE_ROOT"/*/"${slug}__"*/manifest.txt "$ARCHIVE_ROOT"/*/"${slug}__"*.manifest.txt; do
      [ -f "$mf" ] || continue
      case "$mf" in
        *.manifest.txt) adir="${mf%.manifest.txt}" ;;
        *) adir="$(dirname "$mf")" ;;
      esac
      [ -d "$adir" ] && continue  # archive stands: rescue window open
      b="$(sed -n 's/^branch=//p' "$mf" | head -1)"
      mp="$(sed -n 's/^path=//p' "$mf" | head -1)"
      case "$b" in ""|DETACHED|"$base_branch"|main) continue ;; esac
      if [ -n "$mp" ] && is_in "$mp" "${census_paths[@]:-}"; then continue; fi
      trim_local_branch "$b" || partial=3
      enqueue_branch "$b"
    done
  }

  # --- held-set facts (per pass, before the census) ------------
  # Origin tips for the manifest's record (one read per pass;
  # an unreachable origin simply leaves the map empty).
  declare -A origin_tips=()
  local ob os
  while IFS=$'\t' read -r os ob; do
    [ -n "$ob" ] && origin_tips["${ob#refs/heads/}"]="$os"
  done < <($GIT -C "$main_dir" ls-remote --heads origin 2>/dev/null | head -200)
  # Live-process targets: every process's cwd and open fds,
  # resolved. A tree is live while any target is the tree or
  # under it. The scan root is a seam (tests plant a fake).
  local proc_targets; proc_targets="$(mktemp)"
  local pd tgt
  for pd in "$PROC_ROOT"/[0-9]*; do
    [ -d "$pd" ] || continue
    tgt="$(readlink "$pd/cwd" 2>/dev/null)" && [ -n "$tgt" ] && echo "$tgt" >>"$proc_targets"
    for tgt in "$pd"/fd/*; do
      tgt="$(readlink "$tgt" 2>/dev/null)" && [ -n "$tgt" ] && echo "$tgt" >>"$proc_targets"
    done
  done
  # Non-terminal venue run records (the live-run hold): a
  # record names its tree by path anywhere in its text.
  local -a live_record_files=()
  local rf
  if [ -d "$RUNS_DIR" ]; then
    for rf in "$RUNS_DIR"/*.json; do
      [ -f "$rf" ] || continue
      grep -Eq '"state": "(complete|failed|orphaned)"' "$rf" || live_record_files+=("$rf")
    done
  fi
  # Explicit holds from the state dir's holds file.
  local -a hold_paths=()
  if [ -f "$HOLDS_FILE" ]; then
    local hp
    while IFS= read -r hp; do
      case "$hp" in ""|\#*) continue ;; esac
      hold_paths+=("$hp")
    done <"$HOLDS_FILE"
  fi

  # hold_reasons <path> <branch> <ahead> <merged> <dirty>:
  # echoes the comma-joined hold reasons, empty when the
  # tree is unheld. Reasons: dirty, unlanded, live, run,
  # held — the held-set contract in the header.
  hold_reasons() {
    local hp_path="$1" hp_branch="$2" hp_ahead="$3" hp_merged="$4" hp_dirty="$5"
    local reasons=""
    [ "$hp_dirty" = "1" ] && reasons="dirty"
    if [ -z "$DRAIN_ACT" ] && [ "$hp_ahead" != "-1" ] && [ "$hp_ahead" -gt 0 ] && [ "$hp_merged" != "1" ]; then
      reasons="${reasons:+$reasons,}unlanded"
    fi
    if grep -Fxq "$hp_path" "$proc_targets" || grep -Fq "$hp_path/" "$proc_targets"; then
      reasons="${reasons:+$reasons,}live"
    fi
    if [ "${#live_record_files[@]}" -gt 0 ] && grep -lF "$hp_path" "${live_record_files[@]}" >/dev/null 2>&1; then
      reasons="${reasons:+$reasons,}run"
    fi
    if [ -f "$hp_path/.trim-hold" ] || is_in "$hp_path" "${hold_paths[@]:-}"; then
      reasons="${reasons:+$reasons,}held"
    fi
    echo "$reasons"
  }

  # --- census -------------------------------------------------
  # rows: activity_epoch<TAB>path<TAB>branch|DETACHED<TAB>head<TAB>ahead<TAB>merged<TAB>dirty
  local rows_file; rows_file="$(mktemp)"
  local line
  local cur_path="" cur_branch="DETACHED" cur_head=""
  local -a census_paths=()
  flush_row() {
    [ -z "$cur_path" ] && return
    [ "$cur_path" = "$main_dir" ] && return
    census_paths+=("$cur_path")
    local last_commit=0 newest_touch=0 activity ahead=-1 merged=0 dirty=0
    if [ -d "$cur_path" ]; then
      last_commit="$($GIT -C "$cur_path" log -1 --format=%ct HEAD 2>/dev/null || echo 0)"
      [ -z "$last_commit" ] && last_commit=0
      newest_touch="$(find "$cur_path" -path '*/.git' -prune -o -path '*/node_modules' -prune -o -type f -printf '%T@\n' 2>/dev/null | sort -rn | head -1 | cut -d. -f1)"
      [ -z "$newest_touch" ] && newest_touch=0
      activity=$(( last_commit > newest_touch ? last_commit : newest_touch ))
      if [ "$cur_head" != "" ]; then
        ahead="$($GIT -C "$cur_path" rev-list --count "$base_branch..HEAD" 2>/dev/null || echo -1)"
        if $GIT -C "$cur_path" merge-base --is-ancestor HEAD "$base_branch" 2>/dev/null; then merged=1; fi
      fi
      [ -n "$($GIT -C "$cur_path" status --porcelain 2>/dev/null)" ] && dirty=1
    else
      activity=0
    fi
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$activity" "$cur_path" "$cur_branch" "$cur_head" "$ahead" "$merged" "$dirty" >>"$rows_file"
  }
  while IFS= read -r line; do
    case "$line" in
      "worktree "*) flush_row; cur_path="${line#worktree }"; cur_branch="DETACHED"; cur_head="" ;;
      "HEAD "*) cur_head="${line#HEAD }" ;;
      "branch refs/heads/"*) cur_branch="${line#branch refs/heads/}" ;;
    esac
  done <<EOF
$($GIT -C "$main_dir" worktree list --porcelain 2>/dev/null)
EOF
  flush_row

  # Scope restriction (the drain act's seam, supervision
  # plan Step 4): WORKTREE_TRIM_SCOPE_PATHS, a colon list
  # of absolute worktree paths, narrows this pass's census
  # to those trees — rows outside the set are dropped
  # before ranking, so they neither trim nor consume cap.
  # Unset, the pass covers the repo exactly as before.
  if [ -n "${WORKTREE_TRIM_SCOPE_PATHS:-}" ]; then
    local scoped_file; scoped_file="$(mktemp)"
    while IFS=$'\t' read -r s_act s_path s_rest; do
      case ":${WORKTREE_TRIM_SCOPE_PATHS}:" in
        *":${s_path}:"*) printf '%s\t%s\t%s\n' "$s_act" "$s_path" "$s_rest" >>"$scoped_file" ;;
      esac
    done <"$rows_file"
    mv "$scoped_file" "$rows_file"
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    while IFS=$'\t' read -r act p b h a m d; do
      local rs; rs="$(hold_reasons "$p" "$b" "$a" "$m" "$d")"
      echo "CENSUS repo=$slug tree=$(basename "$p") branch=$b activity=$(iso_of "$act") ahead=$a merged=$m dirty=$d held=${rs:--} cap=$cap tier=$TIER" >>"$RESULT_FILE"
    done < <(sort -t$'\t' -k1,1rn -k2,2 "$rows_file")
    rm -f "$rows_file" "$proc_targets"
    return 0
  fi

  # --- branch trims owed from earlier archives ------------------
  if [ "$BRANCH_TRIM" = "on" ]; then
    seed_branch_queue
    drain_queue
  else
    echo "act=branch-standdown repo=$slug epoch=$NOW" >>"$LEDGER_FILE"
  fi

  # --- rank + cut ----------------------------------------------
  # Held trees are partitioned out FIRST: they are never
  # trimmed and never consume cap — the cap binds only the
  # unheld population the trim is allowed to take.
  local -a unheld_rows=()
  while IFS=$'\t' read -r act p b h a m d; do
    local rs; rs="$(hold_reasons "$p" "$b" "$a" "$m" "$d")"
    if [ -n "$rs" ]; then
      echo "HELD repo=$slug tree=$(basename "$p") branch=$b reasons=$rs" >>"$RESULT_FILE"
      echo "act=held repo=$slug tree=$(basename "$p") branch=$b reasons=$rs epoch=$NOW" >>"$LEDGER_FILE"
    else
      unheld_rows+=("$act|$p|$b|$h|$a|$m|$d")
    fi
  done <"$rows_file"
  rm -f "$rows_file" "$proc_targets"

  # keep set: newest CAP unheld trees (activity desc, path asc).
  local -a keep=()
  local n=0
  while IFS='|' read -r act p b h a m d; do
    n=$((n+1))
    [ "$n" -le "$cap" ] && keep+=("$p")
  done < <(printf '%s\n' "${unheld_rows[@]:-}" | grep -v '^$' | sort -t'|' -k1,1rn -k2,2)

  # trim set: every unheld tree not kept, acted on oldest first.
  local -a trimset=()
  while IFS='|' read -r act p b h a m d; do
    if ! is_in "$p" "${keep[@]:-}"; then trimset+=("$act|$p|$b|$h|$a|$m|$d"); fi
  done < <(printf '%s\n' "${unheld_rows[@]:-}" | grep -v '^$' | sort -t'|' -k1,1n -k2,2)

  # --- trim each target ----------------------------------------
  local t act p b h a m d rest
  for t in "${trimset[@]:-}"; do
    [ -z "$t" ] && continue
    act="${t%%|*}"; rest="${t#*|}"; p="${rest%%|*}"; rest="${rest#*|}"; b="${rest%%|*}"; rest="${rest#*|}"; h="${rest%%|*}"; rest="${rest#*|}"; a="${rest%%|*}"; rest="${rest#*|}"; m="${rest%%|*}"; d="${rest##*|}"
    local tname; tname="$(basename "$p")"
    if [ ! -d "$p" ]; then
      $GIT -C "$main_dir" worktree prune >/dev/null 2>&1
      echo "PRUNED repo=$slug tree=$tname reason=path-missing" >>"$RESULT_FILE"
      echo "act=prune repo=$slug tree=$tname epoch=$NOW" >>"$LEDGER_FILE"
      continue
    fi
    # archive = mv the tree into the archive folder together
    # with its git admin directory (parsed from the tree's
    # .git file). Manifest first: if the admin directory
    # cannot be identified or the manifest cannot be written,
    # the tree is not touched — never remove what cannot be
    # restored whole.
    local gitdir_path=""
    if [ -f "$p/.git" ]; then
      gitdir_path="$(sed -n 's/^gitdir: //p' "$p/.git" | head -1)"
    fi
    if [ -z "$gitdir_path" ] || [ ! -d "$gitdir_path" ]; then
      echo "ARCHIVE-FAIL repo=$slug tree=$tname branch=$b reason=admin-dir-unidentified" >>"$RESULT_FILE"
      partial=3
      continue
    fi
    local admin_id; admin_id="$(basename "$gitdir_path")"
    local adir="$ARCHIVE_ROOT/$TODAY/${slug}__${tname}"
    local suffix=2
    while [ -e "$adir" ]; do adir="$ARCHIVE_ROOT/$TODAY/${slug}__${tname}-${suffix}"; suffix=$((suffix+1)); done
    local plan=""
    plan="$(grep -l "$b" "$main_dir"/.plans/*.md 2>/dev/null | head -1 | xargs -r basename)"
    if ! mkdir -p "$adir" || ! {
      echo "repo=$slug"; echo "tree=$tname"; echo "path=$p"; echo "branch=$b"
      echo "head=$h"; echo "base=$base_branch"; echo "ahead=$a"; echo "merged=$m"
      echo "dirty=$d"; echo "origin_tip=${origin_tips[$b]:-}"
      echo "plan=$plan"; echo "admin_id=$admin_id"; echo "admin_path=$gitdir_path"
      echo "restore_1=mv $adir/tree $p"
      echo "restore_2=mv $adir/worktree-admin $gitdir_path"
      if [ "$b" != "DETACHED" ]; then echo "restore_3=git -C $main_dir branch $b $h"; fi
      echo "restore_cmd=ops/worktree_restore.sh $adir"
      echo "trimmed_epoch=$NOW"; echo "expiry_epoch=$EXPIRY_EPOCH"
    } >"$adir/manifest.txt"; then
      rm -rf "$adir"
      echo "ARCHIVE-FAIL repo=$slug tree=$tname branch=$b reason=manifest-unwritable" >>"$RESULT_FILE"
      partial=3
      continue
    fi
    if ! mv "$p" "$adir/tree" || ! mv "$gitdir_path" "$adir/worktree-admin"; then
      # roll back whatever moved, so the tree stands whole
      [ -d "$adir/tree" ] && [ ! -e "$p" ] && mv "$adir/tree" "$p"
      [ -d "$adir/worktree-admin" ] && [ ! -e "$gitdir_path" ] && mv "$adir/worktree-admin" "$gitdir_path"
      if [ -d "$p" ] && [ -d "$gitdir_path" ]; then
        rm -rf "$adir"
        echo "ARCHIVE-FAIL repo=$slug tree=$tname branch=$b reason=move-failed" >>"$RESULT_FILE"
      else
        echo "ARCHIVE-FAIL repo=$slug tree=$tname branch=$b reason=move-failed-rollback-incomplete archive=$adir" >>"$RESULT_FILE"
      fi
      partial=3
      continue
    fi
    $GIT -C "$main_dir" worktree prune >/dev/null 2>&1
    # The branch is NOT trimmed while the archive stands
    # (2026-11-21 cure): it is the restore's registration
    # and the purge's charge — the clean script trims it
    # (locally when unmoved, on origin via the queue) in
    # the act that removes the expired archive.
    echo "ARCHIVED repo=$slug tree=$tname branch=$b archive=$adir expires=$EXPIRY_ISO note=branch-kept-until-purge restore=ops/worktree_restore.sh" >>"$RESULT_FILE"
    echo "act=trim repo=$slug tree=$tname branch=$b archive=$adir expiry_epoch=$EXPIRY_EPOCH epoch=$NOW" >>"$LEDGER_FILE"
  done

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
  timeout "$REPO_TIMEOUT" bash "${BASH_SOURCE[0]}" --worker "$slug" --tier "$TIER" \
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

if [ "$any_partial" -ne 0 ]; then exit 3; fi
if [ "$any_ok" -eq 0 ]; then exit 1; fi
exit 0
