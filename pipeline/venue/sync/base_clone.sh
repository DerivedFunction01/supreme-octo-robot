#!/usr/bin/env bash
# Run ON the Colab VM: base HTTPS clone of the origin tip, the substrate the
# snapshot bundle fast-forwards. Usage: base_clone.sh [repo_url] [dest]
# Optional branch form (branch transport): base_clone.sh [repo_url] [dest]
# [branch] [sha] — fetch the named branch and pin the clone to its tip; a
# named sha is the announced tip, and a fetched tip that differs refuses.
set -euo pipefail
# Argument surface: four optional positionals, no flags.
# The parse below is a vendored positional core of the
# unified argv contract (contract home:
# pipeline/platform/argv.py; bash adapter: argv.sh in
# the same home) — vendored, not sourced, because the
# runner uploads this file ALONE to the VM (sync/runner/
# launch.py) and runs it from the upload directory,
# where no checkout stands beside it. It carries the
# contract's clauses for a flags-free declaration: a
# flag-shaped token before `--` is a usage refusal, a
# fifth positional is a usage refusal, --help prints
# usage, and positionals after `--` are taken literally.
# Sync obligation: if the contract's positional clauses
# change in argv.sh, this block changes with them.
_argv_positionals=()
_argv_after_sep=0
for _argv_token in "$@"; do
  if [ "$_argv_after_sep" = 0 ] && [ "$_argv_token" = "--" ]; then
    _argv_after_sep=1
    continue
  fi
  if [ "$_argv_after_sep" = 0 ]; then
    if [ "$_argv_token" = "--help" ] || [ "$_argv_token" = "-h" ]; then
      echo "usage: base_clone.sh [repo_url] [dest] [branch] [sha]"
      exit 0
    fi
    case "$_argv_token" in
      --*|-*)
        echo "base_clone: unknown flag $_argv_token" >&2
        echo "usage: base_clone.sh [repo_url] [dest] [branch] [sha]" >&2
        exit 2
        ;;
    esac
  fi
  _argv_positionals+=("$_argv_token")
done
if [ "${#_argv_positionals[@]}" -gt 4 ]; then
  echo "base_clone: surplus positional ${_argv_positionals[4]}" >&2
  echo "usage: base_clone.sh [repo_url] [dest] [branch] [sha]" >&2
  exit 2
fi
URL="${_argv_positionals[0]:-${VENUE_REPO_URL:-${COLAB_REPO_URL:-}}}"  # step6-retire: COLAB_ dual-read fallback
DEST="${_argv_positionals[1]:-}"
BRANCH="${_argv_positionals[2]:-}"
SHA="${_argv_positionals[3]:-}"
unset _argv_positionals _argv_after_sep _argv_token
if [ -z "$URL" ]; then
  echo "base_clone: no repo URL given (arg 1 or VENUE_REPO_URL)" >&2; exit 2
fi
if [ -z "$DEST" ]; then
  echo "base_clone: no dest given (arg 2; the registry entry's dest under /content)" >&2; exit 2
fi
if [ ! -d "$DEST/.git" ]; then
  git clone "$URL" "$DEST"
fi
if [ -n "$BRANCH" ]; then
  # Branch transport: the fetched branch tip IS the tree under test — the
  # branch is transport only, never a landing, so the clone detaches at
  # the tip and any local state from a previous pin is discarded by the
  # reset, exactly as the main pin below discards a diverged snapshot.
  git -C "$DEST" fetch origin "$BRANCH"
  TIP="$(git -C "$DEST" rev-parse FETCH_HEAD)"
  if [ -n "$SHA" ] && [ "$TIP" != "$SHA" ]; then
    echo "base_clone: branch $BRANCH tip $TIP != announced sha $SHA; refusing" >&2; exit 3
  fi
  git -C "$DEST" checkout -q --detach "$TIP"
  git -C "$DEST" reset --hard "$TIP"
  echo "base clone at $(git -C "$DEST" rev-parse HEAD) tree $(git -C "$DEST" rev-parse 'HEAD^{tree}')"
  exit 0
fi
git -C "$DEST" fetch origin main
git -C "$DEST" checkout main
# The clone is a scratch substrate whose only job is to sit at the origin
# tip before a snapshot apply; a previous apply leaves local main on a
# snapshot commit that diverges once origin moves, so pin by reset —
# a fast-forward merge fatals on that divergence and strands the clone.
git -C "$DEST" reset --hard origin/main
echo "base clone at $(git -C "$DEST" rev-parse HEAD) tree $(git -C "$DEST" rev-parse 'HEAD^{tree}')"
