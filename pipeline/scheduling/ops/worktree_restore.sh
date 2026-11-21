#!/usr/bin/env bash
# Worktree restore — the mechanical inverse of the trim's
# archive act (2026-11-21 cure: restoration was a manual
# drill — move the tree back, move the admin directory
# back, re-create the branch at its recorded tip from the
# object store when the trim had deleted it, verify by
# hand; two documented specimens needed exactly that
# archaeology). This verb performs the whole sequence
# deterministically from the archive's manifest and
# verifies the result before it speaks:
#
#   worktree_restore.sh <archive-dir>
#
# Steps: read the manifest (inside the archive dir, or
# the sibling <archive>.manifest.txt) → refuse loud when
# the tree already stands registered (already restored),
# when the target path is occupied by anything else, when
# the branch now points somewhere other than the recorded
# head (a seat moved it — never move a seat's branch), or
# when the admin path is already occupied → re-create the
# branch at the recorded head when it is missing (the
# pre-cure trims deleted it; post-cure archives keep it,
# so this is normally a no-op check) → move the tree and
# its admin directory back → prune → verify the worktree
# is registered, its HEAD is the recorded head, and its
# checked-out branch is the recorded branch → remove the
# emptied archive and print RESTORED. Any failure prints
# RESTORE-FAIL step=<step> and leaves everything it can
# untouched, so the archive remains the record of truth.
#
# Exit codes: 0 = restored and verified; 2 = refused or
# failed (the line names the step).
#
# Paths derive from this script's location via ops/paths.sh.
set -uo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export GIT_TERMINAL_PROMPT=0

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=paths.sh
. "$OPS_DIR/paths.sh"

GIT="git -c core.fsync=none"

fail() { echo "RESTORE-FAIL step=$1 archive=${ADIR:-?} detail=$2"; exit 2; }

[ $# -eq 1 ] || { echo "usage: worktree_restore.sh <archive-dir>" >&2; exit 2; }
ADIR="${1%/}"
[ -d "$ADIR" ] || fail manifest "archive directory not found: $ADIR"

MANIFEST=""
if [ -f "$ADIR/manifest.txt" ]; then
  MANIFEST="$ADIR/manifest.txt"
elif [ -f "$ADIR.manifest.txt" ]; then
  MANIFEST="$ADIR.manifest.txt"
else
  fail manifest "no manifest in or beside $ADIR"
fi
field() { sed -n "s/^$1=//p" "$MANIFEST" | head -1; }
REPO="$(field repo)"; TREE="$(field tree)"; TPATH="$(field path)"
BRANCH="$(field branch)"; HEAD="$(field head)"; ADMIN_PATH="$(field admin_path)"
[ -n "$REPO" ] && [ -n "$TPATH" ] && [ -n "$HEAD" ] || fail manifest "manifest lacks repo/path/head"
[ -d "$ADIR/tree" ] || fail layout "archive holds no tree/ (retired bundle layout is not restorable as a worktree)"
[ -d "$ADIR/worktree-admin" ] || fail layout "archive holds no worktree-admin/"

MAIN_DIR="$SCHED_WS_ROOT/$REPO"
[ -d "$MAIN_DIR" ] || fail repo "main checkout not found: $MAIN_DIR"
$GIT -C "$MAIN_DIR" rev-parse --git-dir >/dev/null 2>&1 || fail repo "$MAIN_DIR is not a git repo"

# Already restored? The path stands registered.
if $GIT -C "$MAIN_DIR" worktree list --porcelain 2>/dev/null | grep -Fxq "worktree $TPATH"; then
  fail already-restored "$TPATH is a registered worktree"
fi
if [ -e "$TPATH" ]; then
  fail occupied "target path exists and is not the archive's tree: $TPATH"
fi
if [ -e "$ADMIN_PATH" ]; then
  fail occupied "admin path already exists: $ADMIN_PATH"
fi

# The branch: present at the recorded head is the normal
# post-cure case; missing is re-created at the head; moved
# is a refusal — a seat's advanced branch is never reset.
if [ -n "$BRANCH" ] && [ "$BRANCH" != "DETACHED" ]; then
  tip="$($GIT -C "$MAIN_DIR" rev-parse --verify --quiet "refs/heads/$BRANCH" 2>/dev/null || true)"
  if [ -z "$tip" ]; then
    $GIT -C "$MAIN_DIR" branch "$BRANCH" "$HEAD" >/dev/null 2>&1 || fail branch "could not re-create branch $BRANCH at $HEAD"
  elif [ "$tip" != "$HEAD" ]; then
    fail branch-moved "branch $BRANCH is at $tip, manifest records $HEAD"
  fi
fi

mkdir -p "$(dirname "$TPATH")" "$(dirname "$ADMIN_PATH")" || fail move "could not create parent directories"
mv "$ADIR/tree" "$TPATH" || fail move "could not move the tree back to $TPATH"
if ! mv "$ADIR/worktree-admin" "$ADMIN_PATH"; then
  mv "$TPATH" "$ADIR/tree" 2>/dev/null
  fail move "could not move the admin directory back to $ADMIN_PATH (tree rolled back)"
fi
$GIT -C "$MAIN_DIR" worktree prune >/dev/null 2>&1

# Verify against the manifest before speaking success.
$GIT -C "$MAIN_DIR" worktree list --porcelain 2>/dev/null | grep -Fxq "worktree $TPATH" \
  || fail verify "$TPATH is not registered after the move-back"
got_head="$($GIT -C "$TPATH" rev-parse HEAD 2>/dev/null || true)"
[ "$got_head" = "$HEAD" ] || fail verify "restored HEAD is ${got_head:-unreadable}, manifest records $HEAD"
if [ -n "$BRANCH" ] && [ "$BRANCH" != "DETACHED" ]; then
  got_branch="$($GIT -C "$TPATH" branch --show-current 2>/dev/null || true)"
  [ "$got_branch" = "$BRANCH" ] || fail verify "restored tree has branch ${got_branch:-DETACHED}, manifest records $BRANCH"
fi

rm -rf "$ADIR"
[ "$MANIFEST" = "$ADIR.manifest.txt" ] && rm -f "$MANIFEST"
echo "RESTORED repo=$REPO tree=$TREE path=$TPATH branch=${BRANCH:-DETACHED} head=$HEAD"
exit 0
