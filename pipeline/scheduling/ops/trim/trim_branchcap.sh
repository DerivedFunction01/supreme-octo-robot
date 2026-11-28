# trim_branchcap.sh — the worktree trim's branch cap
# phase: archive-before-delete binding of each side's
# surviving branch population to the branch cap.
# Sourced by ops/worktree_trim.sh after
# trim_transport.sh; called from branch_sweep. Reads
# the sweep's locals (l_surv, o_surv, l_blocked,
# o_blocked, origin_ok, have_base) through bash
# dynamic scoping.
#
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
#        default — a tenant repo lands through dev while
#        both derivations resolve to main — declares it
#        in repos.conf's optional 4th field, and it is
#        principal in every phase (sweep, cap census,
#        seed, drain). The 2026-11-24 hourly pass
#        cap-archived a tenant repo's origin dev at
#        00fb3e09 and deleted the ref: the cap ranked it
#        as an ordinary lane branch because no derivation
#        could see it. The declaration is deployment data
#        in the same untracked config that names the
#        target set and the caps; the script still
#        carries no name literals, and an undeclared repo
#        behaves exactly as before.
#        The 2026-11-23 hourly pass cap-archived
#        the tenant repo's main — strictly contained in its
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
  local cap_err=""
  local cap_err_tmp="$cap_dir/.cap-err.$$"
  # cap_run <cmd...>: a covered command run with its
  # stdout discarded and its stderr captured into
  # cap_err — sanitized to one line of at most 300
  # chars — so the step that sets cap_fail also keeps
  # the command's own error text for the
  # BRANCH-CAP-FAIL line. Returns the command's status.
  cap_run() {
    local raw rc
    raw="$("$@" 2>&1 >/dev/null)"; rc=$?
    cap_err="$(printf '%s' "$raw" | tr '\n' ' ' | cut -c 1-300)"
    return "$rc"
  }
  # cap_err_load: fold the stderr a stdout-carrying
  # covered command (list-heads, for-each-ref) left in
  # cap_err_tmp into cap_err, same sanitization.
  cap_err_load() {
    [ -f "$cap_err_tmp" ] || return 0
    cap_err="$(tr '\n' ' ' <"$cap_err_tmp" | cut -c 1-300)"
  }
  # cap_fetch_timeout <bundle-file>: the merge fetch's
  # bound, priced by the work — a floor of 60s plus 2s
  # per MiB of bundle, capped at 600s. A fixed bound
  # misprices the largest repos: their fetches are the
  # biggest, and a pass's own parallel workers are the
  # load the fetch runs under (an idle fetch of a 58 MiB
  # bundle reads in ~1.5s; the same fetch crossed a
  # fixed 60s under the pass's convoy and died silently,
  # misreported as an unreadable bundle — the bundle had
  # already passed bundle verify in the same pass).
  cap_fetch_timeout() {
    local sz t
    sz="$(stat -c %s "$1" 2>/dev/null || echo 0)"
    t=$((60 + sz / 524288))
    [ "$t" -gt 600 ] && t=600
    echo "$t"
  }
  # cap_fetch_fail <side> <status>: the merge fetch's
  # failure reason — a death by the bound (status 124)
  # is a timeout and names itself; anything else is the
  # bundle's readability, with the command's error text
  # already in cap_err.
  cap_fetch_fail() {
    if [ "$2" -eq 124 ]; then
      echo "$1-bundle-timeout"
    else
      echo "$1-bundle-unreadable"
    fi
  }
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
  [ -z "$cap_fail" ] && : >"$cap_err_tmp"
  if [ -z "$cap_fail" ]; then
    for e in "${cap_l_excess[@]:-}"; do
      [ -z "$e" ] && continue
      ep="${e%%|*}"; rest="${e#*|}"; nm="${rest%%|*}"; sha="${rest#*|}"
      ref="refs/archive-cap/$nm"
      cap_run $GIT -C "$main_dir" update-ref "$stage_ns/$nm" "$sha" || { cap_fail="archive-stage-failed"; break; }
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
        cap_run $GIT -C "$main_dir" update-ref "$stage_ns/$nm@origin" "$sha" || { cap_fail="archive-stage-failed"; break; }
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
          cap_run $GIT -C "$main_dir" update-ref "$stage_ns/$nm" "$sha" || { cap_fail="archive-stage-failed"; break; }
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
    if ! cap_run $GIT -C "$main_dir" bundle create "$staged_bundle" "${stage_refs[@]}"; then
      cap_fail="bundle-create-failed"
    elif ! cap_run $GIT -C "$main_dir" bundle verify "$staged_bundle"; then
      cap_fail="bundle-verify-failed"
    else
      heads_n="$($GIT -C "$main_dir" bundle list-heads "$staged_bundle" 2>"$cap_err_tmp" | wc -l)"
      if [ "$heads_n" -ne "${#stage_refs[@]}" ]; then
        cap_fail="bundle-verify-failed"; cap_err_load
      fi
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
    cap_run timeout "$(cap_fetch_timeout "$bundle")" $GIT -C "$main_dir" fetch --quiet "$bundle" \
      'refs/archive-cap/*:refs/archive-cap/*'
    local prior_rc=$?
    [ "$prior_rc" -ne 0 ] && cap_fail="$(cap_fetch_fail prior "$prior_rc")"
  fi
  if [ -z "$cap_fail" ]; then
    # this pass's staged refs join the namespace under
    # their final archive names; on a name the standing
    # bundle also carries, this pass's tip governs —
    # the newest staging wins, as the pre-lock staging
    # order had it.
    cap_run timeout "$(cap_fetch_timeout "$staged_bundle")" $GIT -C "$main_dir" fetch --quiet "$staged_bundle" \
      "$stage_ns/*:refs/archive-cap/*"
    local staged_rc=$?
    [ "$staged_rc" -ne 0 ] && cap_fail="$(cap_fetch_fail staged "$staged_rc")"
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
    done < <($GIT -C "$main_dir" for-each-ref --format='%(refname)%09%(objectname)%09%(committerdate:unix)' refs/archive-cap 2>"$cap_err_tmp")
    if [ "${#staged[@]}" -eq 0 ]; then
      cap_fail="archive-stage-failed"; cap_err_load
    fi
  fi
  if [ -z "$cap_fail" ]; then
    local -a ref_args=()
    for e in "${staged[@]:-}"; do
      [ -n "$e" ] && ref_args+=("${e%%|*}")
    done
    rm -f "$merge_tmp"
    if ! cap_run $GIT -C "$main_dir" bundle create "$merge_tmp" "${ref_args[@]}"; then
      cap_fail="bundle-create-failed"
    elif ! cap_run $GIT -C "$main_dir" bundle verify "$merge_tmp"; then
      cap_fail="bundle-verify-failed"
    else
      heads_n="$($GIT -C "$main_dir" bundle list-heads "$merge_tmp" 2>"$cap_err_tmp" | wc -l)"
      if [ "$heads_n" -ne "${#staged[@]}" ]; then
        cap_fail="bundle-verify-failed"; cap_err_load
      fi
    fi
  fi
  if [ -n "$cap_fail" ]; then
    rm -f "$merge_tmp" "$manifest_tmp" "$cap_err_tmp"
    if [ -n "$cap_lock_fd" ]; then
      flock -u "$cap_lock_fd" 2>/dev/null
      exec {cap_lock_fd}>&-
    fi
    # the staged file, when one stands, is left in place
    # and named: it is this pass's only copy of its
    # excess until a later pass merges it.
    local fail_line="BRANCH-CAP-FAIL repo=$slug reason=$cap_fail bundle=$bundle"
    [ -e "$staged_bundle" ] && fail_line="$fail_line staged=$staged_bundle"
    [ -n "$cap_err" ] && fail_line="$fail_line err=$cap_err"
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
  rm -f "$staged_bundle" "$cap_err_tmp"
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
