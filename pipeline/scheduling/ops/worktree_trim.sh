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
#      next pass. Queue line forms (2026-11-23): a guarded
#      charge is branch<TAB>evaluated-tip<TAB>class, class
#      sweep, seed, or cap; a bare branch name is the
#      purge's legacy charge — the clean script's form —
#      and drains unconditionally, as it always has. One
#      outstanding charge per branch: a fresh enqueue
#      replaces any older line for the same branch, and
#      the drain takes the first standing line for a
#      branch as its governing charge. The queue seeds
#      from archive manifests
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
#      carve-out.) There is no held set above the cap
#      either: no state a tree or branch can be claimed
#      to be in exempts it — the contract at the head of
#      this file. The
#      branch leg carries a kill-switch
#      (WT_TRIM_BRANCH_TRIM, default on): it stood the leg
#      down on 2026-11-15 after an incident report until
#      the flip back; setting it to off re-imposes the
#      stand-down (no purge-time branch acts, no queue
#      seeding or draining; tree archiving is unaffected).
#   6. branch sweep (2026-11-22, owner's ruling: the
#      hourly pass takes no exemptions when it comes to
#      trimming): every pass, per repo, the worker censuses
#      ALL branches — not only the archives' own. Branches
#      pushed by lanes whose trees never stood in the local
#      census (venue/session clones) otherwise accumulate
#      forever (steampowernj: 144 origin branches, 111 of
#      them fully contained in main). One fetch --prune
#      refreshes origin truth (an unreachable origin fails
#      the origin half only; the local half still runs);
#      the ONLY trim criterion is containment — the branch
#      tip is an ancestor of the default branch (the local
#      base branch locally, origin/<base> on origin).
#      Contained local branches delete through
#      trim_local_branch, except the default branch itself
#      and any branch checked out in a worktree (mechanical:
#      git refuses those). Contained origin branches
#      enqueue and the standing drain discharges them. No
#      provenance, no held set, no name carve-outs: an
#      uncontained branch is not trim material, a contained
#      one trims. The principal branches (point 7) stand
#      outside the candidate set entirely, in both scopes:
#      the base branch is the criterion's own reference,
#      and the remote's default branch — in a dev-base
#      repo, contained by construction — is never enqueued.
#      Two refinements bind the sweep's verdict to the
#      moment of the act (2026-11-23):
#      - tip-equal exclusion: a branch whose tip EQUALS
#        the default branch's tip at census is not swept
#        at all, on either side — the exclusion keys on
#        the ref's position, not its name. A tip-equal ref
#        is where the default branch itself stands (in a
#        dev-flow repo, the standing integration point);
#        the sweep's 'landed and spent' assertion does not
#        hold there. It draws a BRANCH-CONTAINED-SKIP-EQUAL
#        line and stays in the cap census, cap-eligible
#        exactly as any other branch. A branch that moves
#        off tip-equal is judged by plain containment at
#        the next census.
#      - drain re-verification: a containment verdict is
#        computed against a census-time snapshot, and a
#        branch can advance before the drain discharges
#        its charge. The queue therefore carries the
#        evaluated tip with each guarded charge, and the
#        drain (and the local deletion path) re-evaluates
#        containment against the LIVE tip whenever the
#        ref has moved: a branch is deleted only when the
#        tip actually deleted is itself contained, and
#        every BRANCH-TRIMMED record carries that tip as
#        sha=. A moved, no-longer-contained branch is
#        kept and draws a BRANCH-DRAIN-SKIP line naming
#        both tips. Charges whose preservation already
#        happened by another mechanism — the cap phase's
#        archive-before-delete, the purge's bare queue
#        lines — carry no containment verdict and drain
#        as they always have.
#   7. branch cap (2026-11-22, owner's correction:
#      containment is not the end state): the configured
#      max binds the branch POPULATION — 10 branches per
#      repo per side (local, origin) — and the hourly pass
#      takes no exemptions. After the containment sweep,
#      per repo per side, any population still over the cap
#      sheds its excess by ARCHIVE-BEFORE-DELETE, oldest
#      tip activity (tip committer epoch) first. Every
#      excess tip is preserved in ONE bundle per repo per
#      pass at $ARCHIVE_ROOT/<date>/<slug>-branch-cap/
#      branches.bundle under refs/archive-cap/<branch>,
#      with a manifest.tsv beside it (branch, tip sha, tip
#      date, sides trimmed) whose header carries the exact
#      restore commands; a same-day bundle from an earlier
#      pass is unioned in, never clobbered. The bundle is
#      verified (git bundle verify, and its head count
#      equals the manifest row count) BEFORE any ref is
#      deleted; on verification failure nothing is deleted
#      on either side, the failure is recorded, and the
#      pass is partial. The write protocol is safe
#      against concurrent passes over the same repo (an
#      hourly pass and a deep pass): a pass first bundles
#      its own excess alone — staged in a per-pass ref
#      namespace, written to a per-pass staged file
#      (branches.bundle.staged-<pid>) in the archive
#      directory, and verified there; the union with the
#      standing archive then happens under a
#      per-archive-directory flock (.merge.lock): inside
#      the lock the standing bundle and the staged bundle
#      are fetched into the archive ref namespace, the
#      union bundle is written to a fresh temp file,
#      verified, and renamed over branches.bundle, and
#      manifest.tsv is rewritten the same way (temp file,
#      rename) — the standing archive is only ever
#      replaced whole, by a verified union, and passes
#      serialize only on that short merge, never on
#      bundle creation. A staged file is removed once
#      merged; on any failure it is left in place and
#      named in the BRANCH-CAP-FAIL line — a source of
#      record until merged — and the standing archive
#      stands untouched. Only then do the excess refs go:
#      local through trim_local_branch, origin through the
#      queue and its drain. The disposition is uniform
#      over the SELECTABLE population: candidates rank by
#      tip activity alone and the newest `cap` stand.
#      (Owner, 2026-11-22: no exceptions as a hard
#      requirement — a live pass once printed live=12
#      cap=10 never=12, the whole population exempt and
#      the cap binding nothing. That ruling bans exempt
#      SETS — name lists and state carve-outs carried in
#      code; the structural exclusions below are not a
#      set: each is a property of the census itself,
#      derived from the repo at census time — or, for a
#      declared principal, named in the untracked
#      deployment config that already carries the target
#      set and caps — with no name literals and no
#      registry in the script.)
#      - principal branches (2026-11-23 cure): the base
#        branch — the ref containment is measured
#        against, the main worktree's own checkout — and
#        the remote's default branch (the origin/HEAD
#        symref target). A principal is never a sweep
#        candidate, never cap-selectable, never seeded,
#        and the drain refuses and drops any charge
#        naming one (BRANCH-DRAIN-SKIP reason=principal).
#        Declared principals (2026-11-24 cure) stand in
#        the same set: a repo whose standing integration
#        branch is neither the base nor the remote's
#        default — steampowernj lands through dev while
#        both derivations resolve to main — declares it
#        in repos.conf's optional 4th field, and it is
#        principal in every phase (sweep, cap census,
#        seed, drain). The 2026-11-24 hourly pass
#        cap-archived steampowernj's origin dev at
#        00fb3e09 and deleted the ref: the cap ranked it
#        as an ordinary lane branch because no derivation
#        could see it. The declaration is deployment data
#        in the same untracked config that names the
#        target set and the caps; the script still
#        carries no name literals, and an undeclared repo
#        behaves exactly as before.
#        The 2026-11-23 hourly pass cap-archived
#        steampowernj's main — strictly contained in its
#        base, dev — attempted its origin deletion
#        twice, and left a standing cap charge for it;
#        only the remote's own default-branch refusal
#        stood in the way (attempts on main reach back
#        to 2026-11-17), and a cap charge carries no
#        containment verdict the drain could re-verify.
#        A census cannot take its own reference points
#        as material.
#      - checked-out branches (2026-11-23 cure): a branch
#        with a live worktree checkout is not
#        cap-selectable on either side and is not
#        archived by the cap phase. The pre-cure phase
#        freed an attached excess branch by detaching its
#        worktree's HEAD at the same tip; the 2026-11-23
#        pass attempted exactly that against a tree the
#        same pass held as unlanded and failed
#        (BRANCH-LOCAL-FAIL reason=detach-failed). The
#        cap never detaches a tree to take its branch.
#      (A venue-transport branch hold stood here until
#      the 2026-11-26 ruling retired every hold that
#      outranks the cap: a branch a run record names as
#      its transport base is swept, capped, and drained
#      on the same criteria as any other branch.)
#      Blocked branches still count in their side's live
#      population. When the selectable population cannot
#      cover the excess, the pass reports the remainder
#      as BRANCH-CAP-OVER with the blocked survivors'
#      reasons and ends partial — the bound is stated
#      honestly rather than met by taking a protected
#      ref. A delete failure records the failure line,
#      marks the pass partial, and the pass continues
#      with the remaining excess — a failure line is an
#      outcome, not an exemption.
#
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
# The drain act's seam (supervision plan Step 4):
# WORKTREE_TRIM_DRAIN_ACT=1 marks a pass as the workbench
# drain detector's archive act rather than the standing
# census. The pass no longer varies by caller —
# the variable is carried for the drain detector's own
# accounting; see the no-held-set contract in the header.
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
  # steampowernj lands through dev while both derivations
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

  # --- branch-trim queue helpers -------------------------------
  queue_file() { echo "$STATE_DIR/remote-pending-$slug.txt"; }

  enqueue_branch() {
    # $1 = branch, $2 = evaluated tip (optional), $3 =
    # charge class (sweep|seed|cap, default sweep). With
    # a tip, the line is the guarded form
    # branch<TAB>tip<TAB>class; without one it is the
    # bare legacy line. One outstanding charge per
    # branch: any older line for the same branch (a bare
    # purge line included) is replaced — the freshest
    # evaluation governs.
    local qf; qf="$(queue_file)"
    mkdir -p "$STATE_DIR"
    touch "$qf"
    local tmp; tmp="$(mktemp)"
    awk -F'\t' -v b="$1" '$1 != b' "$qf" >"$tmp"
    if [ -n "${2:-}" ]; then
      printf '%s\t%s\t%s\n' "$1" "$2" "${3:-sweep}" >>"$tmp"
    else
      echo "$1" >>"$tmp"
    fi
    mv "$tmp" "$qf"
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

  # Principal membership (see the derivation at worker
  # start): the base branch or the remote's default
  # branch, in either scope — a local branch carrying the
  # default's name is the same standing ref the remote
  # protects, and the local census has no separate
  # derivation for it — or a branch the deployment
  # config declares for this repo (repos.conf field 4,
  # the 2026-11-24 cure). No name literals in the script:
  # the derived pair comes from the repo, the declared
  # names live only in the untracked config.
  is_principal() {
    [ "$1" = "$base_branch" ] && return 0
    [ -n "$origin_default" ] && [ "$1" = "$origin_default" ] && return 0
    is_in "$1" "${declared_principals[@]:-}" && return 0
    return 1
  }

  # Set by trim_local_branch when it keeps a moved branch:
  # the ref's live tip, for the caller's survivor census.
  TLB_LIVE_SHA=""

  trim_local_branch() {
    # $1 = branch, $2 = evaluated tip (optional): the tip
    # a containment verdict was computed against. Silent
    # success when the ref is already gone. When the ref
    # has moved since that verdict, containment is
    # re-evaluated against the live tip before any
    # delete — a branch is never deleted on a stale tip's
    # verdict (2026-11-23). Returns 0 deleted (or already
    # gone), 1 delete failed, 2 kept: moved and no longer
    # contained (BRANCH-DRAIN-SKIP emitted, TLB_LIVE_SHA
    # set). With no evaluated tip the delete is the
    # caller's own charge (the cap phase's archived
    # excess) and proceeds as it always has. Every
    # deletion records the tip actually deleted as sha=.
    TLB_LIVE_SHA=""
    local cur
    cur="$($GIT -C "$main_dir" rev-parse --verify --quiet "refs/heads/$1" 2>/dev/null)"
    [ -z "$cur" ] && return 0
    if [ -n "${2:-}" ] && [ "$cur" != "$2" ]; then
      if ! $GIT -C "$main_dir" merge-base --is-ancestor "refs/heads/$1" "refs/heads/$base_branch" 2>/dev/null; then
        TLB_LIVE_SHA="$cur"
        echo "BRANCH-DRAIN-SKIP repo=$slug branch=$1 scope=local reason=tip-moved-not-contained evaluated=$2 live=$cur" >>"$RESULT_FILE"
        return 2
      fi
    fi
    if $GIT -C "$main_dir" branch -D "$1" >/dev/null 2>&1; then
      echo "BRANCH-TRIMMED repo=$slug branch=$1 scope=local sha=$cur" >>"$RESULT_FILE"
      echo "act=branch-trim repo=$slug branch=$1 scope=local sha=$cur epoch=$NOW" >>"$LEDGER_FILE"
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
    # One charge per branch: the first standing line for
    # a branch governs; later lines for the same branch
    # (a bare purge charge beside a guarded line, in
    # either order of writing) are subsumed by its
    # outcome. A charge that cannot discharge is kept
    # verbatim for the next pass.
    local -a q_lines=()
    local ql qb
    declare -A q_seen=()
    while IFS= read -r ql; do
      [ -z "$ql" ] && continue
      qb="${ql%%$'\t'*}"
      [ -n "${q_seen[$qb]:-}" ] && continue
      q_seen["$qb"]=1
      q_lines+=("$ql")
    done <"$qf"
    local line b sha class rest live out rc out2 vb vbase contained
    for line in "${q_lines[@]:-}"; do
      [ -z "$line" ] && continue
      b="${line%%$'\t'*}"; rest="${line#*$'\t'}"
      if [ "$rest" = "$line" ]; then
        sha=""; class=""
      else
        sha="${rest%%$'\t'*}"; class="${rest#*$'\t'}"
        [ "$class" = "$rest" ] && class=""
      fi
      if is_principal "$b"; then
        # A principal branch is never charged (2026-11-23
        # cure): a standing charge naming one — of any
        # class, a legacy bare charge included, written
        # by any older code — is refused and dropped,
        # never discharged. Before this, the remote's
        # own default-branch refusal was the only thing
        # standing between a queued cap charge and the
        # delete, and cap charges carry no containment
        # verdict the drain could re-verify.
        echo "BRANCH-DRAIN-SKIP repo=$slug branch=$b scope=origin reason=principal" >>"$RESULT_FILE"
        continue
      fi

      out="$(timeout 60 $GIT -C "$main_dir" ls-remote --heads "$url" "refs/heads/$b" 2>/dev/null)"; rc=$?
      if [ "$rc" -ne 0 ]; then
        echo "$line" >>"$keep"
        echo "BRANCH-REMOTE-FAIL repo=$slug branch=$b reason=origin-unreachable" >>"$RESULT_FILE"
        partial=3
        continue
      fi
      if [ -z "$out" ]; then continue; fi  # already gone on origin
      live="${out%%[[:space:]]*}"
      case "$class" in
        sweep|seed)
          if [ -n "$sha" ] && [ "$live" != "$sha" ]; then
            # The tip moved after the containment
            # verdict: re-evaluate against the LIVE tip
            # and the LIVE base before deleting — never
            # delete on a stale verdict (2026-11-23).
            vb="refs/trim-drain/$b"; vbase="refs/trim-drain/$base_branch"
            if ! timeout 120 $GIT -C "$main_dir" fetch --quiet "$url" "+refs/heads/$b:$vb" "+refs/heads/$base_branch:$vbase" >/dev/null 2>&1; then
              # a ref that vanished mid-drain is simply
              # gone; anything else is an unreachable
              # origin at re-verification: keep the
              # charge, mark the pass partial
              out2="$(timeout 60 $GIT -C "$main_dir" ls-remote --heads "$url" "refs/heads/$b" 2>/dev/null)"
              [ -z "$out2" ] && continue
              echo "$line" >>"$keep"
              echo "BRANCH-REMOTE-FAIL repo=$slug branch=$b reason=origin-unreachable" >>"$RESULT_FILE"
              partial=3
              continue
            fi
            contained=0
            $GIT -C "$main_dir" merge-base --is-ancestor "$vb" "$vbase" 2>/dev/null && contained=1
            $GIT -C "$main_dir" update-ref -d "$vb" 2>/dev/null
            $GIT -C "$main_dir" update-ref -d "$vbase" 2>/dev/null
            if [ "$contained" -eq 0 ]; then
              echo "BRANCH-DRAIN-SKIP repo=$slug branch=$b scope=origin reason=tip-moved-not-contained evaluated=$sha live=$live" >>"$RESULT_FILE"
              continue
            fi
          fi
          ;;
      esac
      if timeout 120 $GIT -C "$main_dir" push "$url" --delete "$b" >/dev/null 2>&1; then
        echo "BRANCH-TRIMMED repo=$slug branch=$b scope=origin sha=$live" >>"$RESULT_FILE"
        echo "act=branch-trim repo=$slug branch=$b scope=origin sha=$live epoch=$NOW" >>"$LEDGER_FILE"
      else
        echo "$line" >>"$keep"
        echo "BRANCH-REMOTE-FAIL repo=$slug branch=$b reason=origin-delete-failed" >>"$RESULT_FILE"
        partial=3
      fi
    done
    mv "$keep" "$qf"
  }

  # Branch sweep (header points 6 and 7): census every
  # branch in both scopes against the containment criterion,
  # then bind the surviving population to the branch cap.
  # Runs after the manifest seeding, before the drain, so
  # the origin branches it enqueues discharge in this same
  # pass. Counts feed one BRANCH-SWEEP summary line, emitted
  # only when the sweep acted (the pass stays silent when
  # nothing happens). Survivors are recorded as
  # epoch|name|sha rows (tip committer epoch, tip sha) —
  # the cap phase's activity ranking and archive record.
  # A tip-equal branch (its tip is the base's tip) is a
  # survivor by position, drawn as BRANCH-CONTAINED-SKIP-
  # EQUAL, and enters the cap census like any survivor.
  branch_sweep() {
    local swept_local=0 swept_origin=0 kept=0
    local -a checked_out=()
    local -a l_surv=() o_surv=()
    local -A l_blocked=() o_blocked=()
    local origin_ok=0 have_base=0
    local wl lb ob oname url lsha lepoch osha oepoch
    local base_lsha base_osha trc lep2 cb
    while IFS= read -r wl; do
      case "$wl" in
        "branch refs/heads/"*) checked_out+=("${wl#branch refs/heads/}") ;;
      esac
    done < <($GIT -C "$main_dir" worktree list --porcelain 2>/dev/null)
    # Cap-phase blocks (2026-11-23 cure), derived here at
    # census and read by branch_cap_phase through dynamic
    # scoping: a principal branch is not cap-selectable in
    # either scope, and a branch checked out in a worktree
    # is not cap-selectable on either side — its tree
    # stands, and the cap never detaches a tree to take
    # its branch. Blocked branches still count in their
    # side's live population. Principal membership
    # overlays the checkout mark (the base branch is
    # always checked out — in the main worktree — and its
    # governing reason is principal).
    for cb in "${checked_out[@]:-}"; do
      [ -n "$cb" ] || continue
      l_blocked["$cb"]="checked-out"; o_blocked["$cb"]="checked-out"
    done
    l_blocked["$base_branch"]="principal"; o_blocked["$base_branch"]="principal"
    if [ -n "$origin_default" ]; then
      l_blocked["$origin_default"]="principal"; o_blocked["$origin_default"]="principal"
    fi
    # Declared principals (2026-11-24 cure) carry the
    # same census block, under the same governing reason:
    # the cap census reads only these laid marks, so a
    # principal source that is_principal knows but the
    # census does not lay is selectable here — the exact
    # shape of the venue-transport escape above.
    local dpb2
    for dpb2 in "${declared_principals[@]:-}"; do
      [ -n "$dpb2" ] || continue
      l_blocked["$dpb2"]="principal"; o_blocked["$dpb2"]="principal"
    done
    base_lsha="$($GIT -C "$main_dir" rev-parse --verify --quiet "refs/heads/$base_branch" 2>/dev/null)"
    while IFS=$'\t' read -r lb lsha lepoch; do
      [ -z "$lb" ] && continue
      if is_principal "$lb"; then
        # never a sweep candidate (2026-11-23 cure): the
        # base branch's own cap row is the cap phase's to
        # add, as before; any other principal (the remote
        # default's local namesake) stands as a survivor
        # in the cap census, blocked there as principal
        [ "$lb" = "$base_branch" ] && continue
        kept=$((kept+1)); l_surv+=("$lepoch|$lb|$lsha"); continue
      fi
      if [ -n "$base_lsha" ] && [ "$lsha" = "$base_lsha" ]; then
        echo "BRANCH-CONTAINED-SKIP-EQUAL repo=$slug branch=$lb sha=$lsha" >>"$RESULT_FILE"
        kept=$((kept+1)); l_surv+=("$lepoch|$lb|$lsha"); continue
      fi
      if is_in "$lb" "${checked_out[@]:-}"; then
        kept=$((kept+1)); l_surv+=("$lepoch|$lb|$lsha"); continue
      fi
      if $GIT -C "$main_dir" merge-base --is-ancestor "refs/heads/$lb" "refs/heads/$base_branch" 2>/dev/null; then
        trim_local_branch "$lb" "$lsha"; trc=$?
        case "$trc" in
          0) swept_local=$((swept_local+1)) ;;
          2)
            # moved under the pass and no longer
            # contained: it stands, and enters the cap
            # census at its live tip
            kept=$((kept+1))
            lep2="$($GIT -C "$main_dir" for-each-ref --format='%(committerdate:unix)' "refs/heads/$lb" 2>/dev/null)"
            l_surv+=("$lep2|$lb|$TLB_LIVE_SHA")
            ;;
          *) partial=3 ;;
        esac
      else
        kept=$((kept+1)); l_surv+=("$lepoch|$lb|$lsha")
      fi
    done < <($GIT -C "$main_dir" for-each-ref --format='%(refname:short)%09%(objectname)%09%(committerdate:unix)' refs/heads 2>/dev/null)
    url="$(push_url)"
    if [ -n "$url" ]; then
      if ! timeout 120 $GIT -C "$main_dir" fetch --prune origin >/dev/null 2>&1; then
        echo "BRANCH-REMOTE-FAIL repo=$slug scope=origin reason=origin-unreachable" >>"$RESULT_FILE"
        partial=3
      else
        origin_ok=1
        $GIT -C "$main_dir" show-ref --verify --quiet "refs/remotes/origin/$base_branch" && have_base=1
        base_osha=""
        if [ "$have_base" -eq 1 ]; then
          base_osha="$($GIT -C "$main_dir" rev-parse --verify --quiet "refs/remotes/origin/$base_branch" 2>/dev/null)"
        fi
        while IFS=$'\t' read -r ob osha oepoch; do
          oname="${ob#origin/}"
          case "$oname" in ""|HEAD) continue ;; esac
          if is_principal "$oname"; then
            # never a sweep candidate (2026-11-23 cure):
            # the base branch's own cap row is the cap
            # phase's to add, as before; the remote
            # default stands as a survivor in the cap
            # census, blocked there as principal. (Main
            # in a dev-base repo is contained by
            # construction — this skip is the only thing
            # between it and the queue.)
            [ "$oname" = "$base_branch" ] && continue
            kept=$((kept+1)); o_surv+=("$oepoch|$oname|$osha"); continue
          fi
          if [ "$have_base" -eq 1 ] && [ -n "$base_osha" ] && [ "$osha" = "$base_osha" ]; then
            echo "BRANCH-CONTAINED-SKIP-EQUAL repo=$slug branch=$oname sha=$osha" >>"$RESULT_FILE"
            kept=$((kept+1)); o_surv+=("$oepoch|$oname|$osha"); continue
          fi
          if [ "$have_base" -eq 1 ] && $GIT -C "$main_dir" merge-base --is-ancestor "refs/remotes/origin/$oname" "refs/remotes/origin/$base_branch" 2>/dev/null; then
            enqueue_branch "$oname" "$osha" sweep; swept_origin=$((swept_origin+1))
          else
            kept=$((kept+1)); o_surv+=("$oepoch|$oname|$osha")
          fi
        done < <($GIT -C "$main_dir" for-each-ref --format='%(refname:short)%09%(objectname)%09%(committerdate:unix)' refs/remotes/origin 2>/dev/null)
      fi
    fi
    if [ "$swept_local" -gt 0 ] || [ "$swept_origin" -gt 0 ]; then
      echo "BRANCH-SWEEP repo=$slug local=$swept_local origin=$swept_origin kept=$kept" >>"$RESULT_FILE"
      echo "act=branch-sweep repo=$slug local=$swept_local origin=$swept_origin kept=$kept epoch=$NOW" >>"$LEDGER_FILE"
    fi
    branch_cap_phase
  }

  # Branch cap phase (header point 7): bind each side's
  # surviving population to branch_cap_for(). Reads the
  # sweep's locals (l_surv, o_surv, l_blocked, o_blocked,
  # origin_ok, have_base) through dynamic scoping. Excess
  # tips are archived into one verified bundle BEFORE any
  # deletion; a verification failure deletes nothing and
  # marks the pass partial.
  branch_cap_phase() {
    local bcap; bcap="$(branch_cap_for "$slug")"
    case "$bcap" in ""|*[!0-9]*) bcap=10 ;; esac
    local e rest nm
    # --- per-side populations: every surviving branch
    # counts in its side's population, ranked by tip
    # activity (epoch asc, name asc — the standing
    # ranking). The excess is drawn from the SELECTABLE
    # rows only: a row blocked at census (a principal
    # branch, or a branch checked out in a worktree —
    # l_blocked/o_blocked, derived in branch_sweep) is
    # never selected and never archived. When the
    # selectable rows cannot cover the excess, the
    # remainder is reported as BRANCH-CAP-OVER with the
    # blocked survivors' reasons and the pass ends
    # partial — the bound is stated honestly rather than
    # met by taking a protected ref.
    local -a l_pop=() o_pop=()
    local bsha bepoch
    bsha="$($GIT -C "$main_dir" rev-parse --verify --quiet "refs/heads/$base_branch" 2>/dev/null)"
    if [ -n "$bsha" ]; then
      bepoch="$($GIT -C "$main_dir" for-each-ref --format='%(committerdate:unix)' "refs/heads/$base_branch" 2>/dev/null)"
      l_pop+=("$bepoch|$base_branch|$bsha")
    fi
    for e in "${l_surv[@]:-}"; do
      [ -n "$e" ] && l_pop+=("$e")
    done
    if [ "${#l_pop[@]}" -gt 0 ]; then
      mapfile -t l_pop < <(printf '%s\n' "${l_pop[@]}" | sort -t'|' -k1,1n -k2,2)
    fi
    local live_local=${#l_pop[@]}
    if [ "$origin_ok" -eq 1 ]; then
      if [ "$have_base" -eq 1 ]; then
        bsha="$($GIT -C "$main_dir" rev-parse --verify --quiet "refs/remotes/origin/$base_branch" 2>/dev/null)"
        if [ -n "$bsha" ]; then
          bepoch="$($GIT -C "$main_dir" for-each-ref --format='%(committerdate:unix)' "refs/remotes/origin/$base_branch" 2>/dev/null)"
          o_pop+=("$bepoch|$base_branch|$bsha")
        fi
      fi
      for e in "${o_surv[@]:-}"; do
        [ -n "$e" ] && o_pop+=("$e")
      done
      if [ "${#o_pop[@]}" -gt 0 ]; then
        mapfile -t o_pop < <(printf '%s\n' "${o_pop[@]}" | sort -t'|' -k1,1n -k2,2)
      fi
    fi
    local live_origin=${#o_pop[@]}
    # --- selection: the oldest selectable rows, up to
    # the excess; blocked rows are walked past, never
    # taken. over = the excess the selectable population
    # could not cover.
    local -a cap_l_excess=() cap_o_excess=()
    local nx sel_nm l_over=0 o_over=0
    local l_surv_reasons="" o_surv_reasons=""
    if [ "$live_local" -gt "$bcap" ]; then
      nx=$((live_local - bcap))
      for e in "${l_pop[@]:-}"; do
        [ -z "$e" ] && continue
        [ "${#cap_l_excess[@]}" -ge "$nx" ] && break
        rest="${e#*|}"; sel_nm="${rest%%|*}"
        [ -n "${l_blocked[$sel_nm]:-}" ] && continue
        cap_l_excess+=("$e")
      done
      l_over=$((live_local - bcap - ${#cap_l_excess[@]}))
      if [ "$l_over" -gt 0 ]; then
        local -a rs=()
        for e in "${l_pop[@]:-}"; do
          [ -z "$e" ] && continue
          rest="${e#*|}"; sel_nm="${rest%%|*}"
          [ -n "${l_blocked[$sel_nm]:-}" ] && rs+=("${l_blocked[$sel_nm]}")
        done
        l_surv_reasons="$(printf '%s\n' "${rs[@]:-}" | grep -v '^$' | sort -u | paste -sd, -)"
      fi
    fi
    if [ "$origin_ok" -eq 1 ] && [ "$live_origin" -gt "$bcap" ]; then
      nx=$((live_origin - bcap))
      for e in "${o_pop[@]:-}"; do
        [ -z "$e" ] && continue
        [ "${#cap_o_excess[@]}" -ge "$nx" ] && break
        rest="${e#*|}"; sel_nm="${rest%%|*}"
        [ -n "${o_blocked[$sel_nm]:-}" ] && continue
        cap_o_excess+=("$e")
      done
      o_over=$((live_origin - bcap - ${#cap_o_excess[@]}))
      if [ "$o_over" -gt 0 ]; then
        local -a rs=()
        for e in "${o_pop[@]:-}"; do
          [ -z "$e" ] && continue
          rest="${e#*|}"; sel_nm="${rest%%|*}"
          [ -n "${o_blocked[$sel_nm]:-}" ] && rs+=("${o_blocked[$sel_nm]}")
        done
        o_surv_reasons="$(printf '%s\n' "${rs[@]:-}" | grep -v '^$' | sort -u | paste -sd, -)"
      fi
    fi
    emit_cap_over() {
      # $1 = side, $2 = live, $3 = over, $4 = survivors
      echo "BRANCH-CAP-OVER repo=$slug side=$1 live=$2 cap=$bcap over=$3 survivors=$4" >>"$RESULT_FILE"
      echo "act=branch-cap-over repo=$slug side=$1 live=$2 cap=$bcap over=$3 survivors=$4 epoch=$NOW" >>"$LEDGER_FILE"
    }
    if [ "${#cap_l_excess[@]}" -eq 0 ] && [ "${#cap_o_excess[@]}" -eq 0 ]; then
      # nothing selectable: no archive is staged for refs
      # that will not move; a blocked overage is reported
      # and ends the pass partial
      if [ "$l_over" -gt 0 ] || [ "$o_over" -gt 0 ]; then
        [ "$l_over" -gt 0 ] && emit_cap_over local "$live_local" "$l_over" "$l_surv_reasons"
        [ "$o_over" -gt 0 ] && emit_cap_over origin "$live_origin" "$o_over" "$o_surv_reasons"
        partial=3
      fi
      return 0
    fi

    # --- archive-before-delete: one bundle per repo per pass
    local cap_dir="$ARCHIVE_ROOT/$TODAY/${slug}-branch-cap"
    local bundle="$cap_dir/branches.bundle"
    local manifest="$cap_dir/manifest.tsv"
    local cap_fail=""
    # ref -> this pass's sides ("local", "origin", or
    # "local,origin"); a branch whose local and origin tips
    # differ stages its origin tip under <branch>@origin so
    # both tips survive.
    declare -A new_side=()
    # final archive ref -> this pass's staged "sha|epoch"
    declare -A pass_row=()
    local -a stage_refs=()
    local sha ep ref cur heads_n=""
    # This pass's staging lives in its own ref namespace
    # and its own bundle file, both keyed by the worker's
    # pid: concurrent passes over this repo share neither,
    # so neither can stage over, bundle over, or clean up
    # the other's in-flight archive work.
    local stage_ns="refs/archive-cap-stage-$$"
    local staged_bundle="$cap_dir/branches.bundle.staged-$$"
    mkdir -p "$cap_dir" 2>/dev/null || cap_fail="archive-unwritable"
    if [ -z "$cap_fail" ]; then
      for e in "${cap_l_excess[@]:-}"; do
        [ -z "$e" ] && continue
        ep="${e%%|*}"; rest="${e#*|}"; nm="${rest%%|*}"; sha="${rest#*|}"
        ref="refs/archive-cap/$nm"
        $GIT -C "$main_dir" update-ref "$stage_ns/$nm" "$sha" 2>/dev/null || { cap_fail="archive-stage-failed"; break; }
        stage_refs+=("$stage_ns/$nm")
        pass_row["$ref"]="$sha|$ep"
        new_side["$ref"]="local"
      done
    fi
    if [ -z "$cap_fail" ]; then
      for e in "${cap_o_excess[@]:-}"; do
        [ -z "$e" ] && continue
        ep="${e%%|*}"; rest="${e#*|}"; nm="${rest%%|*}"; sha="${rest#*|}"
        ref="refs/archive-cap/$nm"
        if [ -n "${pass_row[$ref]:-}" ] && [ "${pass_row[$ref]%%|*}" != "$sha" ] && [ "${new_side[$ref]:-}" = "local" ]; then
          ref="refs/archive-cap/$nm@origin"
          $GIT -C "$main_dir" update-ref "$stage_ns/$nm@origin" "$sha" 2>/dev/null || { cap_fail="archive-stage-failed"; break; }
          stage_refs+=("$stage_ns/$nm@origin")
          pass_row["$ref"]="$sha|$ep"
          new_side["$ref"]="origin"
        else
          # A same-tip branch in excess on both sides
          # stages ONE ref: the local loop already laid
          # it, and a duplicate stage_refs entry makes
          # the bundle's head count fall short of the
          # staged count, failing the pass's own verify
          # below (bundle-verify-failed on every
          # both-sides excess). Only the side bookkeeping
          # moves here.
          if [ -z "${pass_row[$ref]:-}" ]; then
            $GIT -C "$main_dir" update-ref "$stage_ns/$nm" "$sha" 2>/dev/null || { cap_fail="archive-stage-failed"; break; }
            stage_refs+=("$stage_ns/$nm")
          fi
          pass_row["$ref"]="$sha|$ep"
          if [ "${new_side[$ref]:-}" = "local" ]; then
            new_side["$ref"]="local,origin"
          else
            new_side["$ref"]="origin"
          fi
        fi
      done
    fi
    # This pass's bundle, staged alone and verified before
    # it touches the standing archive. From here on the
    # staged FILE is this pass's durable copy of its
    # excess; the staging refs are scratch and are dropped
    # whatever the outcome — the file, not the namespace,
    # is what a failure leaves behind, named in the
    # failure line.
    if [ -z "$cap_fail" ]; then
      rm -f "$staged_bundle"
      if ! $GIT -C "$main_dir" bundle create "$staged_bundle" "${stage_refs[@]}" >/dev/null 2>&1; then
        cap_fail="bundle-create-failed"
      elif ! $GIT -C "$main_dir" bundle verify "$staged_bundle" >/dev/null 2>&1; then
        cap_fail="bundle-verify-failed"
      else
        heads_n="$($GIT -C "$main_dir" bundle list-heads "$staged_bundle" 2>/dev/null | wc -l)"
        [ "$heads_n" -ne "${#stage_refs[@]}" ] && cap_fail="bundle-verify-failed"
      fi
      for ref in "${stage_refs[@]:-}"; do
        [ -n "$ref" ] && $GIT -C "$main_dir" update-ref -d "$ref" 2>/dev/null
      done
    fi
    # --- merge into the standing archive, under the
    # per-archive-directory flock: the standing bundle and
    # this pass's staged bundle are fetched into the
    # archive ref namespace, the union bundle is written
    # to a fresh temp file, verified, and renamed over the
    # standing bundle; the manifest is rewritten the same
    # way (temp file, rename) inside the same lock. The
    # standing archive is only ever replaced whole, by a
    # verified union — and passes serialize only here,
    # never on bundle creation above.
    local cap_lock="$cap_dir/.merge.lock"
    local merge_tmp="$cap_dir/.branches.bundle.merge-$$"
    local manifest_tmp="$cap_dir/.manifest.tsv.merge-$$"
    local cap_lock_fd=""
    if [ -z "$cap_fail" ]; then
      if ! : >>"$cap_lock" 2>/dev/null; then
        cap_fail="archive-unwritable"
      else
        exec {cap_lock_fd}>"$cap_lock"
        flock -x "$cap_lock_fd" 2>/dev/null || cap_fail="archive-lock-failed"
      fi
    fi
    if [ -z "$cap_fail" ] && [ -f "$bundle" ]; then
      # union an earlier same-day pass's bundle in: its
      # refs restage alongside this pass's, and the
      # rewritten bundle below carries the union — never
      # a clobber. The read happens inside the lock, so
      # the bundle read here is the one the rename below
      # replaces: a concurrent pass's merge is either
      # wholly before this read or wholly after it.
      timeout 60 $GIT -C "$main_dir" fetch --quiet "$bundle" \
        'refs/archive-cap/*:refs/archive-cap/*' >/dev/null 2>&1 \
        || cap_fail="prior-bundle-unreadable"
    fi
    if [ -z "$cap_fail" ]; then
      # this pass's staged refs join the namespace under
      # their final archive names; on a name the standing
      # bundle also carries, this pass's tip governs —
      # the newest staging wins, as the pre-lock staging
      # order had it.
      timeout 60 $GIT -C "$main_dir" fetch --quiet "$staged_bundle" \
        "$stage_ns/*:refs/archive-cap/*" >/dev/null 2>&1 \
        || cap_fail="staged-bundle-unreadable"
    fi
    # The bundle's rows: every staged archive ref (this
    # pass's excess unioned with any earlier same-day rows).
    # Sides for rows this pass did not touch are recovered
    # from the standing manifest, keyed by branch+sha —
    # read inside the lock, so the read is never torn by a
    # concurrent pass's rewrite.
    local -a staged=()
    local sref ssha sep mb ms msha mside
    declare -A old_side=()
    if [ -z "$cap_fail" ]; then
      if [ -f "$manifest" ]; then
        while IFS=$'\t' read -r mb msha _ mside; do
          case "$mb" in ""|\#*|branch) continue ;; esac
          old_side["$mb|$msha"]="$mside"
        done <"$manifest"
      fi
      while IFS=$'\t' read -r sref ssha sep; do
        [ -z "$sref" ] && continue
        staged+=("$sref|$ssha|$sep")
      done < <($GIT -C "$main_dir" for-each-ref --format='%(refname)%09%(objectname)%09%(committerdate:unix)' refs/archive-cap 2>/dev/null)
      [ "${#staged[@]}" -eq 0 ] && cap_fail="archive-stage-failed"
    fi
    if [ -z "$cap_fail" ]; then
      local -a ref_args=()
      for e in "${staged[@]:-}"; do
        [ -n "$e" ] && ref_args+=("${e%%|*}")
      done
      rm -f "$merge_tmp"
      if ! $GIT -C "$main_dir" bundle create "$merge_tmp" "${ref_args[@]}" >/dev/null 2>&1; then
        cap_fail="bundle-create-failed"
      elif ! $GIT -C "$main_dir" bundle verify "$merge_tmp" >/dev/null 2>&1; then
        cap_fail="bundle-verify-failed"
      else
        heads_n="$($GIT -C "$main_dir" bundle list-heads "$merge_tmp" 2>/dev/null | wc -l)"
        [ "$heads_n" -ne "${#staged[@]}" ] && cap_fail="bundle-verify-failed"
      fi
    fi
    if [ -n "$cap_fail" ]; then
      rm -f "$merge_tmp" "$manifest_tmp"
      if [ -n "$cap_lock_fd" ]; then
        flock -u "$cap_lock_fd" 2>/dev/null
        exec {cap_lock_fd}>&-
      fi
      # the staged file, when one stands, is left in place
      # and named: it is this pass's only copy of its
      # excess until a later pass merges it.
      local fail_line="BRANCH-CAP-FAIL repo=$slug reason=$cap_fail bundle=$bundle"
      [ -e "$staged_bundle" ] && fail_line="$fail_line staged=$staged_bundle"
      echo "$fail_line" >>"$RESULT_FILE"
      echo "act=branch-cap-fail repo=$slug reason=$cap_fail epoch=$NOW" >>"$LEDGER_FILE"
      partial=3
      return 0
    fi
    mv "$merge_tmp" "$bundle"
    # Manifest: header carries the exact restore commands;
    # one row per bundle head (branch, tip sha, tip date
    # ISO, sides trimmed). Written to a temp file and
    # renamed over, inside the lock, so the manifest on
    # disk always stands whole beside the bundle it rows.
    {
      echo "# branch-cap archive repo=$slug epoch=$NOW"
      echo "# bundle=$bundle"
      echo "# restore_1=git -C $main_dir fetch $bundle refs/archive-cap/<branch>"
      echo "# restore_2=git -C $main_dir branch <branch> FETCH_HEAD"
      printf 'branch\ttip_sha\ttip_date\tsides\n'
      local bname sside
      for e in "${staged[@]:-}"; do
        [ -z "$e" ] && continue
        sref="${e%%|*}"; rest="${e#*|}"; ssha="${rest%%|*}"; sep="${rest##*|}"
        bname="${sref#refs/archive-cap/}"
        sside="${new_side[$sref]:-${old_side[$bname|$ssha]:-prior}}"
        case "$bname" in
          *@origin)
            bname="${bname%@origin}"
            [ "$sside" = "prior" ] && sside="origin"
            ;;
        esac
        printf '%s\t%s\t%s\t%s\n' "$bname" "$ssha" "$(iso_of "$sep")" "$sside"
      done
    } >"$manifest_tmp"
    mv "$manifest_tmp" "$manifest"
    # The package's purge manifest (owner ruling,
    # 2026-11-26: bundles are inside the trim regime,
    # past their grace like any archive): the clean
    # script purges by the in-dir manifest form, so the
    # branch-cap package carries one — repo and expiry,
    # no branch (its branches are already deleted; the
    # bundle is their record, and the record expires on
    # the archive's own 1-hour grace, refreshed at every
    # union write).
    {
      echo "repo=$slug"
      echo "tree=${slug}-branch-cap"
      echo "kind=branch-cap"
      echo "expiry_epoch=$EXPIRY_EPOCH"
    } >"$cap_dir/manifest.txt"
    for e in "${staged[@]:-}"; do
      [ -z "$e" ] && continue
      sref="${e%%|*}"
      if [ -n "${new_side[$sref]:-}" ]; then
        rest="${e#*|}"; ssha="${rest%%|*}"
        bname="${sref#refs/archive-cap/}"; bname="${bname%@origin}"
        echo "BRANCH-ARCHIVED repo=$slug branch=$bname sides=${new_side[$sref]} sha=$ssha bundle=$bundle" >>"$RESULT_FILE"
        echo "act=branch-archived repo=$slug branch=$bname sides=${new_side[$sref]} sha=$ssha epoch=$NOW" >>"$LEDGER_FILE"
      fi
      $GIT -C "$main_dir" update-ref -d "$sref" 2>/dev/null
    done
    flock -u "$cap_lock_fd" 2>/dev/null
    exec {cap_lock_fd}>&-
    # merged: the staged file's copy now stands in the
    # archive, so the per-pass file goes.
    rm -f "$staged_bundle"
    # --- deletions, only now that the archive verifies ---
    # The selected excess is never a checked-out branch
    # (blocked at census, above), so no worktree is ever
    # detached to free a ref — the pre-cure phase did
    # exactly that, and the 2026-11-23 hourly pass failed
    # at it against a tree the same pass held as unlanded.
    # A branch checked out mid-pass (after the census)
    # fails its delete inside trim_local_branch and
    # records BRANCH-LOCAL-FAIL, as any delete failure
    # does — an outcome, not an exemption.
    for e in "${cap_l_excess[@]:-}"; do
      [ -z "$e" ] && continue
      rest="${e#*|}"; nm="${rest%%|*}"; sha="${rest#*|}"
      trim_local_branch "$nm" || partial=3
    done
    for e in "${cap_o_excess[@]:-}"; do
      [ -z "$e" ] && continue
      rest="${e#*|}"; nm="${rest%%|*}"; sha="${rest#*|}"
      enqueue_branch "$nm" "$sha" cap
    done
    if [ "${#cap_l_excess[@]}" -gt 0 ]; then
      echo "BRANCH-CAP repo=$slug side=local live=$live_local cap=$bcap archived=${#cap_l_excess[@]}" >>"$RESULT_FILE"
      echo "act=branch-cap repo=$slug side=local live=$live_local cap=$bcap archived=${#cap_l_excess[@]} epoch=$NOW" >>"$LEDGER_FILE"
    fi
    if [ "${#cap_o_excess[@]}" -gt 0 ]; then
      echo "BRANCH-CAP repo=$slug side=origin live=$live_origin cap=$bcap archived=${#cap_o_excess[@]}" >>"$RESULT_FILE"
      echo "act=branch-cap repo=$slug side=origin live=$live_origin cap=$bcap archived=${#cap_o_excess[@]} epoch=$NOW" >>"$LEDGER_FILE"
    fi
    if [ "$l_over" -gt 0 ] || [ "$o_over" -gt 0 ]; then
      # the selectable population could not cover the
      # excess: the side(s) end over the bound, held by
      # the blocked survivors the OVER line names
      [ "$l_over" -gt 0 ] && emit_cap_over local "$live_local" "$l_over" "$l_surv_reasons"
      [ "$o_over" -gt 0 ] && emit_cap_over origin "$live_origin" "$o_over" "$o_surv_reasons"
      partial=3
    fi
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
    local mf b mp mh adir src
    for mf in "$ARCHIVE_ROOT"/*/"${slug}__"*/manifest.txt "$ARCHIVE_ROOT"/*/"${slug}__"*.manifest.txt; do
      [ -f "$mf" ] || continue
      case "$mf" in
        *.manifest.txt) adir="${mf%.manifest.txt}" ;;
        *) adir="$(dirname "$mf")" ;;
      esac
      [ -d "$adir" ] && continue  # archive stands: rescue window open
      b="$(sed -n 's/^branch=//p' "$mf" | head -1)"
      mp="$(sed -n 's/^path=//p' "$mf" | head -1)"
      mh="$(sed -n 's/^head=//p' "$mf" | head -1)"
      case "$b" in ""|DETACHED) continue ;; esac
      # a principal branch is never charged (2026-11-23
      # cure) — the principal union set (is_principal:
      # the derived pair plus any deployment-declared
      # principals; the seed acts on both scopes, so it
      # tests the same set as the sweep, the cap, and
      # the drain)
      is_principal "$b" && continue
      if [ -n "$mp" ] && is_in "$mp" "${census_paths[@]:-}"; then continue; fi
      if [ -n "$mh" ]; then
        # the manifest's recorded head is the evaluation
        # the trim is charged against: the local delete
        # re-verifies a moved ref against it, and the
        # origin charge carries it as a guarded seed
        trim_local_branch "$b" "$mh"; src=$?
        if [ "$src" -ne 0 ] && [ "$src" -ne 2 ]; then partial=3; fi
        enqueue_branch "$b" "$mh" seed
      else
        trim_local_branch "$b" || partial=3
        enqueue_branch "$b"
      fi
    done
  }

  # --- pass facts (per pass, before the census) -----------------
  # Origin tips for the manifest's record (one read per pass;
  # an unreachable origin simply leaves the map empty).
  declare -A origin_tips=()
  local ob os
  while IFS=$'\t' read -r os ob; do
    [ -n "$ob" ] && origin_tips["${ob#refs/heads/}"]="$os"
  done < <($GIT -C "$main_dir" ls-remote --heads origin 2>/dev/null | head -200)
  # auto_commit_tree <path> <branch>: commits the tree's
  # full working state in place, on its checked-out
  # branch — for a detached tree, on the deterministic
  # trim/autocommit-<tree> branch (suffixed with the
  # tree's admin id when that name already stands at
  # another tip). On success prints "<branch><TAB><head>";
  # on failure prints "step=<step> reason=<reason>" and
  # returns 1. The commit carries the repo's configured
  # identity and a message naming the trim as the actor;
  # no identity is ever invented here — its absence is
  # the no-identity failure the caller reports by name.
  auto_commit_tree() {
    local ac_path="$1" ac_branch="$2"
    local ac_tname; ac_tname="$(basename "$ac_path")"
    if [ "$ac_branch" = "DETACHED" ]; then
      local ac_name="trim/autocommit-$ac_tname"
      if $GIT -C "$ac_path" show-ref --verify --quiet "refs/heads/$ac_name"; then
        if [ "$($GIT -C "$ac_path" rev-parse "$ac_name" 2>/dev/null)" = "$($GIT -C "$ac_path" rev-parse HEAD 2>/dev/null)" ]; then
          $GIT -C "$ac_path" switch "$ac_name" >/dev/null 2>&1 || { echo "step=switch reason=switch-failed"; return 1; }
        else
          local ac_gitdir ac_admin
          ac_gitdir="$(sed -n 's/^gitdir: //p' "$ac_path/.git" 2>/dev/null | head -1)"
          ac_admin="$(basename "$ac_gitdir")"
          ac_name="trim/autocommit-$ac_tname-$ac_admin"
          if $GIT -C "$ac_path" show-ref --verify --quiet "refs/heads/$ac_name"; then
            echo "step=switch reason=branch-exists"; return 1
          fi
          $GIT -C "$ac_path" switch -c "$ac_name" >/dev/null 2>&1 || { echo "step=switch reason=switch-failed"; return 1; }
        fi
      else
        $GIT -C "$ac_path" switch -c "$ac_name" >/dev/null 2>&1 || { echo "step=switch reason=switch-failed"; return 1; }
      fi
      ac_branch="$ac_name"
    fi
    $GIT -C "$ac_path" add -A >/dev/null 2>&1 || { echo "step=add reason=add-failed"; return 1; }
    local ac_err
    if ! ac_err="$($GIT -C "$ac_path" commit -m "worktree-trim: auto-commit of uncommitted work in $ac_tname (tier $TIER pass)" 2>&1)"; then
      if [ -n "$($GIT -C "$ac_path" status --porcelain 2>/dev/null)" ]; then
        case "$ac_err" in
          *"unable to auto-detect"*|*"empty ident"*|*"no name was provided"*)
            echo "step=commit reason=no-identity" ;;
          *) echo "step=commit reason=commit-failed" ;;
        esac
        return 1
      fi
      # the state raced clean between census and commit:
      # nothing to commit is the success outcome
    fi
    printf '%s\t%s\n' "$ac_branch" "$($GIT -C "$ac_path" rev-parse HEAD 2>/dev/null)"
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
      echo "CENSUS repo=$slug tree=$(basename "$p") branch=$b activity=$(iso_of "$act") ahead=$a merged=$m dirty=$d cap=$cap tier=$TIER" >>"$RESULT_FILE"
    done < <(sort -t$'\t' -k1,1rn -k2,2 "$rows_file")
    rm -f "$rows_file"
    return 0
  fi

  # --- branch trims owed from earlier archives ------------------
  if [ "$BRANCH_TRIM" = "on" ]; then
    seed_branch_queue
    branch_sweep
    drain_queue
  else
    echo "act=branch-standdown repo=$slug epoch=$NOW" >>"$LEDGER_FILE"
  fi

  # --- rank + cut ----------------------------------------------
  # Auto-commit first: every dirty tree is committed in
  # place and re-enters this same ranking as a clean tree
  # — no state holds a tree out of the cap (the header's
  # no-held-set contract). A failed auto-commit is
  # reported by name and ends the pass partial; the tree
  # still ranks, its dirty state riding the archive if
  # the cut takes it. Then the whole population ranks:
  # the cap binds every tree alike.
  local -a ranked_rows=()
  while IFS=$'\t' read -r act p b h a m d; do
    if [ "$d" = "1" ] && [ -d "$p" ]; then
      local ac_out
      if ac_out="$(auto_commit_tree "$p" "$b")"; then
        b="${ac_out%%$'\t'*}"; h="${ac_out##*$'\t'}"
        a="$($GIT -C "$p" rev-list --count "$base_branch..HEAD" 2>/dev/null || echo -1)"
        m=0; $GIT -C "$p" merge-base --is-ancestor HEAD "$base_branch" 2>/dev/null && m=1
        d=0
        echo "AUTOCOMMIT repo=$slug tree=$(basename "$p") branch=$b head=$h" >>"$RESULT_FILE"
        echo "act=autocommit repo=$slug tree=$(basename "$p") branch=$b head=$h epoch=$NOW" >>"$LEDGER_FILE"
      else
        local ac_step="${ac_out%% *}" ac_reason="${ac_out##* }"
        echo "AUTOCOMMIT-FAILED repo=$slug tree=$(basename "$p") branch=$b $ac_step $ac_reason" >>"$RESULT_FILE"
        echo "act=autocommit-failed repo=$slug tree=$(basename "$p") branch=$b $ac_step $ac_reason epoch=$NOW" >>"$LEDGER_FILE"
        partial=3
      fi
    fi
    ranked_rows+=("$act|$p|$b|$h|$a|$m|$d")
  done <"$rows_file"
  rm -f "$rows_file"

  # keep set: newest CAP trees (activity desc, path asc).
  local -a keep=()
  local n=0
  while IFS='|' read -r act p b h a m d; do
    n=$((n+1))
    [ "$n" -le "$cap" ] && keep+=("$p")
  done < <(printf '%s\n' "${ranked_rows[@]:-}" | grep -v '^$' | sort -t'|' -k1,1rn -k2,2)

  # trim set: every ranked tree not kept, acted on oldest first.
  local -a trimset=()
  while IFS='|' read -r act p b h a m d; do
    if ! is_in "$p" "${keep[@]:-}"; then trimset+=("$act|$p|$b|$h|$a|$m|$d"); fi
  done < <(printf '%s\n' "${ranked_rows[@]:-}" | grep -v '^$' | sort -t'|' -k1,1n -k2,2)

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
