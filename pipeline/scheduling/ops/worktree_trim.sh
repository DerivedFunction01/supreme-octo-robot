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
#      make the cut, every older tree is trimmed;
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
#   4. branches are trimmed the same way as worktrees: a
#      trimmed tree's branch is deleted locally at trim time
#      and deleted on origin through a per-repo retry queue
#      (state/worktree-trim/remote-pending-<repo>.txt) that
#      every pass seeds from unexpired archive manifests and
#      drains at worker start and end — a failed origin
#      deletion stays queued and is retried next pass, and a
#      purge never loses the obligation (the clean script
#      enqueues the branch before removing an archive). A
#      tree the owner moved back inside the hour is a rescue:
#      its manifest is skipped while its path stands as a
#      registered worktree again.
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
#   5. no branch is exempt: branches trim exactly as their
#      trees do, whatever their name or state — a formation
#      that needs its branch lands it. (A keeper exemption
#      for formation union branches plus a pins file stood
#      briefly on 2026-11-15 and was removed the same day
#      by the owner's ruling: no carve-out.) The branch leg
#      carries a kill-switch (WT_TRIM_BRANCH_TRIM, default
#      on): it stood the leg down on 2026-11-15 after an
#      incident report until the flip back; setting it to
#      off re-imposes the stand-down.
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
# WT_TRIM_CAP_<SLUG>, WT_TRIM_REPO_TIMEOUT_SECS.
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

  # Seed the queue from unexpired archive manifests (both the
  # sibling manifests this script writes and the in-tree
  # manifests of the retired bundle format): each archived
  # tree's branch is owed the same trim, locally and on
  # origin — unless the owner rescued the tree, in which case
  # its path stands registered again and the manifest is
  # skipped. Runs against the census path set, so it executes
  # after the census below; declared here with the helpers.
  seed_branch_queue() {
    local mf b mp
    for mf in "$ARCHIVE_ROOT"/*/"${slug}__"*/manifest.txt "$ARCHIVE_ROOT"/*/"${slug}__"*.manifest.txt; do
      [ -f "$mf" ] || continue
      b="$(sed -n 's/^branch=//p' "$mf" | head -1)"
      mp="$(sed -n 's/^path=//p' "$mf" | head -1)"
      case "$b" in ""|DETACHED|"$base_branch"|main) continue ;; esac
      if [ -n "$mp" ] && is_in "$mp" "${census_paths[@]:-}"; then continue; fi
      trim_local_branch "$b" || partial=3
      enqueue_branch "$b"
    done
  }

  # --- census -------------------------------------------------
  # rows: activity_epoch<TAB>path<TAB>branch|DETACHED<TAB>head<TAB>ahead<TAB>merged
  local rows_file; rows_file="$(mktemp)"
  local line
  local cur_path="" cur_branch="DETACHED" cur_head=""
  local -a census_paths=()
  flush_row() {
    [ -z "$cur_path" ] && return
    [ "$cur_path" = "$main_dir" ] && return
    census_paths+=("$cur_path")
    local last_commit=0 newest_touch=0 activity ahead=-1 merged=0
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
    else
      activity=0
    fi
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$activity" "$cur_path" "$cur_branch" "$cur_head" "$ahead" "$merged" >>"$rows_file"
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
    while IFS=$'\t' read -r act p b h a m; do
      echo "CENSUS repo=$slug tree=$(basename "$p") branch=$b activity=$(iso_of "$act") ahead=$a merged=$m cap=$cap tier=$TIER" >>"$RESULT_FILE"
    done < <(sort -t$'\t' -k1,1rn -k2,2 "$rows_file")
    rm -f "$rows_file"
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
  # keep set: newest CAP trees (activity desc, path asc).
  local -a keep=()
  local n=0
  while IFS=$'\t' read -r act p b h a m; do
    n=$((n+1))
    [ "$n" -le "$cap" ] && keep+=("$p")
  done < <(sort -t$'\t' -k1,1rn -k2,2 "$rows_file")

  # trim set: everything not kept, acted on oldest first.
  local -a trimset=()
  while IFS=$'\t' read -r act p b h a m; do
    if ! is_in "$p" "${keep[@]:-}"; then trimset+=("$act|$p|$b|$h|$a|$m"); fi
  done < <(sort -t$'\t' -k1,1n -k2,2 "$rows_file")
  rm -f "$rows_file"

  # --- trim each target ----------------------------------------
  local t act p b h a m rest
  for t in "${trimset[@]:-}"; do
    [ -z "$t" ] && continue
    act="${t%%|*}"; rest="${t#*|}"; p="${rest%%|*}"; rest="${rest#*|}"; b="${rest%%|*}"; rest="${rest#*|}"; h="${rest%%|*}"; rest="${rest#*|}"; a="${rest%%|*}"; m="${rest##*|}"
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
      echo "plan=$plan"; echo "admin_id=$admin_id"; echo "admin_path=$gitdir_path"
      echo "restore_1=mv $adir/tree $p"
      echo "restore_2=mv $adir/worktree-admin $gitdir_path"
      if [ "$b" != "DETACHED" ]; then echo "restore_3=git -C $main_dir branch $b $h"; fi
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
    # the branch is trimmed the same way as the worktree:
    # deleted locally now, deleted on origin via the queue —
    # unless the branch leg is stood down.
    if [ "$BRANCH_TRIM" = "on" ] && [ "$b" != "DETACHED" ] && [ "$b" != "$base_branch" ] && [ "$b" != "main" ]; then
      trim_local_branch "$b" || partial=3
      enqueue_branch "$b"
    fi
    echo "ARCHIVED repo=$slug tree=$tname branch=$b archive=$adir expires=$EXPIRY_ISO note=restore-by-move-back-within-1h" >>"$RESULT_FILE"
    echo "act=trim repo=$slug tree=$tname branch=$b archive=$adir expiry_epoch=$EXPIRY_EPOCH epoch=$NOW" >>"$LEDGER_FILE"
  done

  # --- origin deletions for this pass's trims -------------------
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
