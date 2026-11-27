# trim_transport.sh — the worktree trim's branch
# transport: the origin-deletion queue and its drain,
# the containment sweep, and the archive-manifest
# seeding. Sourced by ops/worktree_trim.sh; the
# functions read and write the worker's locals (slug,
# main_dir, base_branch, partial) through bash dynamic
# scoping. The branch cap phase lives in
# trim_branchcap.sh (sourced after this file;
# branch_sweep calls it).
#
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
