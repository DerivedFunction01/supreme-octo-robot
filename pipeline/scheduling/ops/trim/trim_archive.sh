# trim_archive.sh — the worktree trim's archive phase:
# the auto-commit of dirty trees, the rank + cut, and
# the archive of each trimmed tree. Sourced by
# ops/worktree_trim.sh; the phase functions read and
# write the worker's locals (slug, main_dir,
# base_branch, partial, trimset, origin_tips) through
# bash dynamic scoping.
#
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

trim_rank_cut() {
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
  trimset=()
  while IFS='|' read -r act p b h a m d; do
    if ! is_in "$p" "${keep[@]:-}"; then trimset+=("$act|$p|$b|$h|$a|$m|$d"); fi
  done < <(printf '%s\n' "${ranked_rows[@]:-}" | grep -v '^$' | sort -t'|' -k1,1n -k2,2)
}

trim_targets() {
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
}
