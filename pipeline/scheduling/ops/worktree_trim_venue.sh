#!/usr/bin/env bash
# Worktree trim, venue form — the same trim system running
# on a local venue (owner ruling, 2026-11-26: the same
# workhorse repo/cron system maintains the venues' disk
# under the identical rules, so a venue never fills up
# waiting on a manual rescue — the hp-envy C:-drive
# outage is this failure's venue form). Dispatched hourly
# by the venue-trim-hourly scheduler entry through the
# venue runner; the script itself runs ON the venue,
# against the venue home it is pointed at.
#
# The venue's surfaces, and the identical rules on each:
#   run trees ($HOME/runs/<run-id>/): the runner's
#     per-fire scratch. Capped by count, ranked by
#     activity (directory mtime — a live run's tree is
#     the newest by construction); the excess oldest are
#     removed whole. Run RECORDS live on the controller
#     side permanently; the tree is scratch. The same
#     store is also capped by bytes: past the count leg,
#     if the store's measured total exceeds the byte
#     budget the same ranked list keeps cutting
#     oldest-first until the measured cuts cover the
#     excess — the count cap alone cannot see one huge
#     tree, and the byte leg is what binds before the
#     venue's disk warn line does.
#   clones (every git repo rooted within depth 3 of
#     $HOME, outside runs/): job clones, mirrors, lane
#     worktrees. A dirty clone is auto-committed in
#     place first — on its checked-out branch, or for a
#     detached clone onto trim/autocommit-<basename> —
#     with the clone's configured identity, never an
#     invented one; then the population ranks by
#     activity (newest of the root, .git/index and
#     .git/FETCH_HEAD mtimes) and the excess oldest are
#     removed. A worktree clone's removal prunes its
#     registration from its main clone.
#   bundles (*.bundle within depth 4 of $HOME, outside
#     runs/): transport copies, cut past the same 24h
#     grace as the controller-side census; a bundle is
#     never a preservation claim.
#   caches (every sub-store of $HOME/.cache, plus
#     $HOME/.npm/_cacache as one entry): provisioning
#     residue — package and browser caches that regrow
#     with every fire and no other surface bounds.
#     Capped by total bytes; over budget, whole
#     sub-stores are cut oldest-first by newest-content
#     mtime. Two preservation rules: a sub-store whose
#     newest content is within the active window of
#     now is in-flight provisioning — it is skipped by
#     name (CACHE-ACTIVE-SKIP) and never cut in that
#     pass; and the ms-playwright store is cut per
#     browser build, oldest build first, the newest
#     build always kept.
# No state exempts a surface: not dirty, not unlanded,
# not a live process, not a claimed in-flight run. The
# one preservation rule the whole system keeps: work is
# never destroyed unpreserved — a clone whose
# auto-commit fails is reported by name
# (AUTOCOMMIT-FAILED), is not cut in that pass, and if
# it keeps its population over cap the pass reports
# CLONE-CAP-OVER and ends partial — the defect is
# named, never silently held. A surface still over cap
# at pass end for any other reason is likewise reported
# (RUN-CAP-OVER / CLONE-CAP-OVER) and the pass ends
# partial (exit 3).
#
# Exit codes: 0 = pass complete, population at cap;
# 3 = partial (a named failure above); 2 = refused
# (bad arguments, no venue home).
#
# Overrides (tests, fixtures): WORKTREE_TRIM_VENUE_HOME,
# WT_TRIM_VENUE_RUN_CAP (default 300),
# WT_TRIM_VENUE_RUN_BYTES (default 77309411328),
# WT_TRIM_VENUE_CLONE_CAP (default 40),
# WT_TRIM_VENUE_CACHE_BYTES (default 8589934592),
# WT_TRIM_VENUE_CACHE_ACTIVE_SECS (default 900),
# WORKTREE_TRIM_BUNDLE_GRACE_SECS (default 86400),
# WORKTREE_TRIM_NOW (epoch seconds, the fake-clock seam).
set -uo pipefail

GIT="git -c core.fsync=none"
NOW="${WORKTREE_TRIM_NOW:-$(date +%s)}"
VENUE_HOME="${WORKTREE_TRIM_VENUE_HOME:-$HOME}"
# The PATH anchor's value (ops/paths.sh SCHED_PATH), derived
# from this script's own home seam: the venue job copies this
# file out of the tree and runs it detached, so the shared
# module cannot be sourced here.
export PATH="$VENUE_HOME/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
RUN_CAP="${WT_TRIM_VENUE_RUN_CAP:-300}"
RUN_BYTES="${WT_TRIM_VENUE_RUN_BYTES:-77309411328}"
CLONE_CAP="${WT_TRIM_VENUE_CLONE_CAP:-40}"
CACHE_BYTES="${WT_TRIM_VENUE_CACHE_BYTES:-8589934592}"
CACHE_ACTIVE_SECS="${WT_TRIM_VENUE_CACHE_ACTIVE_SECS:-900}"
BUNDLE_GRACE="${WORKTREE_TRIM_BUNDLE_GRACE_SECS:-86400}"

case "$VENUE_HOME" in
  ""|/) echo "REFUSED venue home: '$VENUE_HOME'"; exit 2 ;;
esac
[ -d "$VENUE_HOME" ] || { echo "REFUSED venue home missing: $VENUE_HOME"; exit 2; }
case "$RUN_CAP$CLONE_CAP$RUN_BYTES$CACHE_BYTES$CACHE_ACTIVE_SECS" in
  *[!0-9]*) echo "REFUSED non-numeric cap"; exit 2 ;;
esac

partial=0

mtime_of() { stat -c %Y "$1" 2>/dev/null || echo 0; }

# du_bytes <path> <timeout-secs> — the path's total in
# bytes (du -sb: apparent size, the figure a budget is
# stated in), measured under a timeout so a wedged walk
# can never wedge the trim; prints nothing and returns
# 1 when the measurement fails or times out.
du_bytes() {
  local out
  out="$(timeout "$2" du -sb "$1" 2>/dev/null)" || return 1
  out="${out%%$'\t'*}"
  case "$out" in ""|*[!0-9]*) return 1 ;; esac
  printf '%s\n' "$out"
}

# auto_commit_clone <path> — the controller trim's
# auto-commit, venue form. Prints "<branch><TAB><head>"
# on success; on failure prints "step=<step>
# reason=<reason>" and returns 1.
auto_commit_clone() {
  local path="$1" branch head newname admin
  branch="$($GIT -C "$path" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  if [ -z "$branch" ]; then
    newname="trim/autocommit-$(basename "$path")"
    if $GIT -C "$path" show-ref --verify --quiet "refs/heads/$newname"; then
      if [ "$($GIT -C "$path" rev-parse "$newname")" = "$($GIT -C "$path" rev-parse HEAD)" ]; then
        branch="$newname"
      else
        admin="$(printf %s "$path" | md5sum | cut -c1-8)"
        newname="trim/autocommit-$(basename "$path")-$admin"
        if $GIT -C "$path" show-ref --verify --quiet "refs/heads/$newname"; then
          echo "step=switch reason=branch-exists"; return 1
        fi
        branch="$newname"
      fi
    else
      branch="$newname"
    fi
    if ! $GIT -C "$path" switch -c "$branch" >/dev/null 2>&1 \
        && ! $GIT -C "$path" switch "$branch" >/dev/null 2>&1; then
      echo "step=switch reason=switch-failed"; return 1
    fi
  fi
  if ! $GIT -C "$path" add -A >/dev/null 2>&1; then
    echo "step=add reason=add-failed"; return 1
  fi
  local cerr
  if ! cerr="$($GIT -C "$path" commit -m "worktree-trim: auto-commit of uncommitted work in $(basename "$path") (venue pass)" 2>&1 >/dev/null)"; then
    if [ -n "$($GIT -C "$path" status --porcelain 2>/dev/null)" ]; then
      case "$cerr" in
        *"unable to auto-detect"*|*"empty ident"*|*"no name was provided"*)
          echo "step=commit reason=no-identity" ;;
        *) echo "step=commit reason=commit-failed" ;;
      esac
      return 1
    fi
  fi
  head="$($GIT -C "$path" rev-parse HEAD 2>/dev/null || echo unknown)"
  printf '%s\t%s\n' "$branch" "$head"
}

# --- run trees ------------------------------------------------
runs_dir="$VENUE_HOME/runs"
if [ -d "$runs_dir" ]; then
  declare -a run_rows=()
  for d in "$runs_dir"/*/; do
    [ -d "$d" ] || continue
    run_rows+=("$(mtime_of "$d")"$'\t'"${d%/}")
  done
  run_before=${#run_rows[@]}
  cut_n=0
  declare -a run_sorted=()
  if [ "$run_before" -gt 0 ]; then
    mapfile -t run_sorted < <(printf '%s\n' "${run_rows[@]}" | sort -t$'\t' -k1,1n)
  fi
  if [ "$run_before" -gt "$RUN_CAP" ]; then
    cut_n=$((run_before - RUN_CAP))
    for ((i = 0; i < cut_n; i++)); do
      victim="${run_sorted[$i]#*$'\t'}"
      if rm -rf "$victim"; then
        echo "RUN-TREE-CUT path=$victim"
      else
        echo "RUN-TREE-CUT-FAILED path=$victim"
        partial=3
      fi
    done
  fi
  # Byte leg: the same ranked list, continuing past the
  # count leg's survivors, until the measured cuts cover
  # the excess over the byte budget. The store total is
  # measured once up front and once at the end; a
  # measurement that times out skips the leg by name —
  # the trim never wedges on measurement.
  if [ "$run_before" -gt 0 ]; then
    if run_bytes_before="$(du_bytes "$runs_dir" 120)"; then
      run_bytes_after="$run_bytes_before"
      if [ "$run_bytes_before" -gt "$RUN_BYTES" ]; then
        excess=$((run_bytes_before - RUN_BYTES))
        cut_bytes=0
        for ((i = cut_n; i < run_before && cut_bytes < excess; i++)); do
          victim="${run_sorted[$i]#*$'\t'}"
          vbytes="$(du_bytes "$victim" 30 || true)"
          if rm -rf "$victim"; then
            echo "RUN-TREE-CUT path=$victim"
            [ -n "$vbytes" ] && cut_bytes=$((cut_bytes + vbytes))
          else
            echo "RUN-TREE-CUT-FAILED path=$victim"
            partial=3
          fi
        done
        run_bytes_after="$(du_bytes "$runs_dir" 120 || echo unknown)"
      fi
      echo "RUN-BYTES before=$run_bytes_before after=$run_bytes_after budget=$RUN_BYTES"
      case "$run_bytes_after" in
        unknown) : ;;
        *) if [ "$run_bytes_after" -gt "$RUN_BYTES" ]; then
             echo "RUN-BYTES-OVER live=$run_bytes_after budget=$RUN_BYTES"
             partial=3
           fi ;;
      esac
    else
      echo "RUN-BYTES skipped=measure-timeout"
    fi
  fi
  run_after="$(find "$runs_dir" -mindepth 1 -maxdepth 1 -type d | wc -l)"
  echo "RUN-TREES before=$run_before after=$run_after cap=$RUN_CAP"
  if [ "$run_after" -gt "$RUN_CAP" ]; then
    echo "RUN-CAP-OVER live=$run_after cap=$RUN_CAP"
    partial=3
  fi
fi

# --- clones -----------------------------------------------------
declare -a clone_rows=()
while IFS= read -r gitmark; do
  repo_dir="$(dirname "$gitmark")"
  case "$repo_dir" in
    "$runs_dir"|"$runs_dir"/*) continue ;;
    "$VENUE_HOME") continue ;;
  esac
  act="$(mtime_of "$repo_dir")"
  for probe in "$gitmark/index" "$gitmark/FETCH_HEAD"; do
    pm="$(mtime_of "$probe")"; [ "$pm" -gt "$act" ] && act="$pm"
  done
  clone_rows+=("$act"$'\t'"$repo_dir")
done < <(find "$VENUE_HOME" -maxdepth 3 \( -name .git -type d -o -name .git -type f \) 2>/dev/null)

clone_before=${#clone_rows[@]}
declare -a clone_ranked=()
for row in "${clone_rows[@]:-}"; do
  [ -n "$row" ] || continue
  cdir="${row#*$'\t'}"
  if [ -n "$($GIT -C "$cdir" status --porcelain 2>/dev/null)" ]; then
    if ac_out="$(auto_commit_clone "$cdir")"; then
      ac_branch="${ac_out%%$'\t'*}"
      echo "AUTOCOMMIT clone=$cdir branch=$ac_branch"
      row="$(mtime_of "$cdir")"$'\t'"$cdir"
    else
      echo "AUTOCOMMIT-FAILED clone=$cdir ${ac_out:-step=commit reason=commit-failed}"
      partial=3
      continue  # unpreserved work is never cut (header)
    fi
  fi
  clone_ranked+=("$row")
done
if [ "${#clone_ranked[@]}" -gt "$CLONE_CAP" ]; then
  mapfile -t clone_sorted < <(printf '%s\n' "${clone_ranked[@]}" | sort -t$'\t' -k1,1n)
  cut_n=$((${#clone_ranked[@]} - CLONE_CAP))
  for ((i = 0; i < cut_n; i++)); do
    victim="${clone_sorted[$i]#*$'\t'}"
    main_gitdir=""
    if [ -f "$victim/.git" ]; then
      main_gitdir="$(sed -n 's/^gitdir: //p' "$victim/.git" | head -1)"
      case "$main_gitdir" in
        /*) : ;;
        *) main_gitdir="$victim/$main_gitdir" ;;
      esac
      main_gitdir="$(dirname "$(dirname "$main_gitdir")")"
    fi
    if rm -rf "$victim"; then
      echo "CLONE-CUT path=$victim"
      if [ -n "$main_gitdir" ] && [ -d "$main_gitdir" ]; then
        $GIT --git-dir="$main_gitdir" worktree prune >/dev/null 2>&1 || true
      fi
    else
      echo "CLONE-CUT-FAILED path=$victim"
      partial=3
    fi
  done
fi
clone_after=0
while IFS= read -r gitmark; do
  repo_dir="$(dirname "$gitmark")"
  case "$repo_dir" in
    "$runs_dir"|"$runs_dir"/*) continue ;;
    "$VENUE_HOME") continue ;;
  esac
  clone_after=$((clone_after + 1))
done < <(find "$VENUE_HOME" -maxdepth 3 \( -name .git -type d -o -name .git -type f \) 2>/dev/null)
echo "CLONES before=$clone_before after=$clone_after cap=$CLONE_CAP"
if [ "$clone_after" -gt "$CLONE_CAP" ]; then
  echo "CLONE-CAP-OVER live=$clone_after cap=$CLONE_CAP"
  partial=3
fi

# --- bundles ----------------------------------------------------
while IFS= read -r bf; do
  case "$bf" in "$runs_dir"/*) continue ;; esac
  bmt="$(mtime_of "$bf")"
  if [ $((NOW - bmt)) -gt "$BUNDLE_GRACE" ]; then
    if rm -f "$bf"; then
      echo "BUNDLE-CUT path=$bf age_h=$(( (NOW - bmt) / 3600 ))"
    else
      echo "BUNDLE-CUT-FAILED path=$bf"
      partial=3
    fi
  fi
done < <(find "$VENUE_HOME" -maxdepth 4 -path '*/.git' -prune -o -name '*.bundle' -type f -print 2>/dev/null)

# --- caches -----------------------------------------------------
# Every sub-store of $HOME/.cache, plus $HOME/.npm/_cacache
# as one entry, under one byte budget. Each store is
# measured once (timeout-guarded; an unmeasurable store
# is skipped by name and left alone) and ranked by its
# newest content mtime. Over budget, stores cut
# oldest-first until the measured cuts bring the total
# under budget — whole stores, except ms-playwright,
# which cuts per browser build (oldest build first, the
# newest build always kept). A store whose newest
# content is within the active window of NOW is
# in-flight provisioning: skipped by name, never cut.
cache_root="$VENUE_HOME/.cache"
declare -a cache_paths=()
if [ -d "$cache_root" ]; then
  for d in "$cache_root"/*/; do
    [ -d "$d" ] || continue
    cache_paths+=("${d%/}")
  done
fi
if [ -d "$VENUE_HOME/.npm/_cacache" ]; then
  cache_paths+=("$VENUE_HOME/.npm/_cacache")
fi
if [ "${#cache_paths[@]}" -gt 0 ]; then
  declare -a cache_rows=()
  cache_before=0
  for p in "${cache_paths[@]}"; do
    if pbytes="$(du_bytes "$p" 60)"; then
      newest="$(timeout 60 find "$p" -printf '%T@\n' 2>/dev/null | sort -g | tail -1)"
      newest="${newest%.*}"
      case "$newest" in ""|*[!0-9-]*) newest="$(mtime_of "$p")" ;; esac
      cache_rows+=("$newest"$'\t'"$p"$'\t'"$pbytes")
      cache_before=$((cache_before + pbytes))
    else
      echo "CACHE-MEASURE-SKIP path=$p"
    fi
  done
  cache_cut=0
  if [ "$cache_before" -gt "$CACHE_BYTES" ] && [ "${#cache_rows[@]}" -gt 0 ]; then
    mapfile -t cache_sorted < <(printf '%s\n' "${cache_rows[@]}" | sort -t$'\t' -k1,1n)
    for row in "${cache_sorted[@]}"; do
      [ $((cache_before - cache_cut)) -le "$CACHE_BYTES" ] && break
      newest="${row%%$'\t'*}"
      rest="${row#*$'\t'}"
      p="${rest%%$'\t'*}"
      pbytes="${rest#*$'\t'}"
      if [ $((NOW - newest)) -lt "$CACHE_ACTIVE_SECS" ]; then
        echo "CACHE-ACTIVE-SKIP path=$p"
        continue
      fi
      if [ "$(basename "$p")" = "ms-playwright" ]; then
        declare -a build_rows=()
        for b in "$p"/*/; do
          [ -d "$b" ] || continue
          build_rows+=("$(mtime_of "$b")"$'\t'"${b%/}")
        done
        if [ "${#build_rows[@]}" -gt 1 ]; then
          mapfile -t build_sorted < <(printf '%s\n' "${build_rows[@]}" | sort -t$'\t' -k1,1n)
          for ((j = 0; j < ${#build_sorted[@]} - 1; j++)); do
            [ $((cache_before - cache_cut)) -le "$CACHE_BYTES" ] && break
            bpath="${build_sorted[$j]#*$'\t'}"
            bbytes="$(du_bytes "$bpath" 60 || true)"
            if rm -rf "$bpath"; then
              echo "CACHE-CUT path=$bpath bytes=${bbytes:-unknown}"
              [ -n "$bbytes" ] && cache_cut=$((cache_cut + bbytes))
            else
              echo "CACHE-CUT-FAILED path=$bpath"
              partial=3
            fi
          done
        fi
      elif rm -rf "$p"; then
        echo "CACHE-CUT path=$p bytes=$pbytes"
        cache_cut=$((cache_cut + pbytes))
      else
        echo "CACHE-CUT-FAILED path=$p"
        partial=3
      fi
    done
  fi
  cache_after=$((cache_before - cache_cut))
  echo "CACHE before=$cache_before after=$cache_after budget=$CACHE_BYTES"
  if [ "$cache_after" -gt "$CACHE_BYTES" ]; then
    echo "CACHE-CAP-OVER live=$cache_after budget=$CACHE_BYTES"
    partial=3
  fi
fi

exit "$partial"
