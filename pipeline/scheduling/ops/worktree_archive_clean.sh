#!/usr/bin/env bash
# Worktree archive clean — the permanent-removal half of the
# worktree trim job.
#
# Every archive the trim script writes carries a manifest
# with expiry_epoch = creation + exactly 1 hour: a sibling
# <archive>.manifest.txt beside the moved tree (current
# format), or a manifest.txt inside the archive directory
# (the retired bundle format — still honored until the last
# such archive expires). This script permanently removes
# every archive whose expiry has passed — no exemption, no
# knob — and prints one PURGED line per removal. The purge
# is also where the archived tree's branch is trimmed
# (2026-11-21 cure: the trim itself no longer touches the
# branch while the archive stands, so restoration inside
# the window is mechanical). In the act that removes an
# expired archive, the branch is dealt with — but ONLY
# when it provably is the archive's own: it still points
# at the manifest's recorded head AND that head is landed
# in the repo's base branch. Then the local branch is
# deleted and the branch is enqueued in the trim job's
# per-repo origin-deletion queue
# (state/worktree-trim/remote-pending-<repo>.txt), so the
# origin trim is never lost. A branch a seat moved since
# the trim, one still carrying unlanded commits, or one
# whose manifest records no head is left entirely alone —
# local ref and origin copy both — and the PURGED line
# reports branch_local=kept-moved / kept-unlanded /
# kept-unrecorded (an unverifiable branch is never the
# purge's to destroy — the Stage-4 specimen's
# unreferenced-commit recovery is the failure this
# refuses to repeat). The WT_TRIM_BRANCH_TRIM kill-switch
# (off) stands both branch acts down. It is run by
# worktree_trim.sh at the head of every pass, and can be
# run standalone.
#
# Exit codes: 0 = clean pass complete (silent when nothing
# expired, or when no archive folder exists yet);
# 1 = the archive folder exists but cannot be scanned.
#
# Paths derive from this script's location via ops/paths.sh.
# Overrides (tests, fixtures): WORKTREE_ARCHIVE_ROOT,
# WORKTREE_TRIM_STATE_DIR, WORKTREE_TRIM_NOW (epoch seconds,
# the fake-clock seam), --dry-run prints WOULD-PURGE lines
# and removes nothing (and enqueues nothing).
set -uo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=paths.sh
. "$OPS_DIR/paths.sh"

ARCHIVE_ROOT="${WORKTREE_ARCHIVE_ROOT:-$SCHED_WS_ROOT/worktree-archive}"
STATE_DIR="${WORKTREE_TRIM_STATE_DIR:-$SCHED_STATE_DIR/worktree-trim}"
NOW="${WORKTREE_TRIM_NOW:-$(date +%s)}"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

if [ ! -d "$ARCHIVE_ROOT" ]; then
  exit 0
fi
if [ ! -r "$ARCHIVE_ROOT" ]; then
  echo "CLEAN-ERROR archive root unreadable: $ARCHIVE_ROOT"
  exit 1
fi

field() { sed -n "s/^$2=//p" "$1" | head -1; }

enqueue_branch() {
  # $1 = repo slug, $2 = branch. The obligation to delete the
  # branch on origin outlives the archive that carried it.
  case "$2" in ""|DETACHED) return 0 ;; esac
  [ -n "$1" ] || return 0
  mkdir -p "$STATE_DIR"
  local qf="$STATE_DIR/remote-pending-$1.txt"
  touch "$qf"
  grep -Fxq "$2" "$qf" || echo "$2" >>"$qf"
}

purge_local_branch() {
  # $1 = repo, $2 = branch, $3 = recorded head, $4 = base.
  # Echoes the disposition; deletes the local branch only
  # when it is provably the archived tree's own unmoved,
  # landed branch. Anything unverifiable is kept.
  local repo="$1" branch="$2" head="$3" base="$4"
  case "$branch" in ""|DETACHED) echo "none"; return 0 ;; esac
  if [ "${WT_TRIM_BRANCH_TRIM:-on}" != "on" ]; then echo "stood-down"; return 0; fi
  local main_dir="$SCHED_WS_ROOT/$repo"
  [ -d "$main_dir" ] || { echo "no-repo"; return 0; }
  git -c core.fsync=none -C "$main_dir" rev-parse --git-dir >/dev/null 2>&1 || { echo "no-repo"; return 0; }
  local tip
  tip="$(git -c core.fsync=none -C "$main_dir" rev-parse --verify --quiet "refs/heads/$branch" 2>/dev/null)"
  [ -z "$tip" ] && { echo "absent"; return 0; }
  [ -z "$head" ] && { echo "kept-unrecorded"; return 0; }
  [ "$tip" != "$head" ] && { echo "kept-moved"; return 0; }
  [ -z "$base" ] && base="main"
  if ! git -c core.fsync=none -C "$main_dir" merge-base --is-ancestor "$head" "$base" 2>/dev/null; then
    echo "kept-unlanded"; return 0
  fi
  if git -c core.fsync=none -C "$main_dir" branch -D "$branch" >/dev/null 2>&1; then
    echo "trimmed"
  else
    echo "delete-failed"
  fi
}

purge_one() {
  # $1 = manifest file, $2 = archive directory to remove,
  # $3 = "sibling" when the manifest itself must also go.
  local manifest="$1" adir="$2" sibling="${3:-}"
  local expiry repo tree branch head base
  expiry="$(field "$manifest" expiry_epoch)"
  repo="$(field "$manifest" repo)"
  tree="$(field "$manifest" tree)"
  branch="$(field "$manifest" branch)"
  head="$(field "$manifest" head)"
  base="$(field "$manifest" base)"
  case "$expiry" in
    ''|*[!0-9]*) echo "CLEAN-SKIP no expiry in manifest: $adir"; return 0 ;;
  esac
  if [ "$NOW" -ge "$expiry" ]; then
    local bytes
    bytes="$(du -sb "$adir" 2>/dev/null | cut -f1)"
    if [ "$DRY_RUN" -eq 1 ]; then
      echo "WOULD-PURGE repo=${repo:-?} tree=${tree:-?} archive=$adir bytes=${bytes:-0}"
    else
      local branch_local
      branch_local="$(purge_local_branch "$repo" "$branch" "$head" "$base")"
      # The origin-deletion queue is charged only when the
      # branch proved to be the archive's own (trimmed
      # above, or already absent locally): a moved or
      # unlanded branch is a seat's live work, and its
      # origin copy is a backup, never the purge's to take.
      case "$branch_local" in
        trimmed|absent) enqueue_branch "$repo" "$branch" ;;
      esac
      rm -rf "$adir"
      [ "$sibling" = "sibling" ] && rm -f "$manifest"
      echo "PURGED repo=${repo:-?} tree=${tree:-?} archive=$adir bytes=${bytes:-0} branch_local=$branch_local"
    fi
  fi
}

# Current layout: <root>/<YYYY-MM-DD>/<repo>__<tree> is the
# moved tree itself; its manifest is the sibling file
# <root>/<YYYY-MM-DD>/<repo>__<tree>.manifest.txt
for manifest in "$ARCHIVE_ROOT"/*/*.manifest.txt; do
  [ -f "$manifest" ] || continue
  purge_one "$manifest" "${manifest%.manifest.txt}" sibling
done

# Retired layout: <root>/<YYYY-MM-DD>/<repo>__<tree>/manifest.txt
for manifest in "$ARCHIVE_ROOT"/*/*/manifest.txt; do
  [ -f "$manifest" ] || continue
  purge_one "$manifest" "$(dirname "$manifest")"
done

# Drop date directories left empty by the purge.
if [ "$DRY_RUN" -eq 0 ]; then
  for d in "$ARCHIVE_ROOT"/*/; do
    [ -d "$d" ] && rmdir "$d" 2>/dev/null
  done
fi
exit 0
