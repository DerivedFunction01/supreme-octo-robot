#!/usr/bin/env bash
# Short command names for the pipeline entries (owner
# commission, 2026-11-15): the names lanes and the owner
# type — wb, sched, harness, colab-run, colab-lease,
# runner — installed as symlinks in $HOME/.local/bin pointing
# at the real entries in this repo. Symlinks, never
# wrappers or copies: the name resolves to the entry
# itself, so the entry's own location-derived paths are
# the ones that run.
#
# Idempotent, safe to run at any time: a link that
# already points at its target is left untouched; a
# missing, dangling, or wrong-target link is
# (re)created; nothing else in $HOME/.local/bin is touched,
# and a non-symlink sitting on one of the six names is
# refused, never replaced. Every run reports one line
# per name — created / repaired / already-correct — and
# fails loud (exit 1), naming the entry, if a target is
# missing or not executable.
#
# The watchdog's healthy path re-runs this on its
# cadence (--quiet: speak only when a link is created or
# repaired), so the names heal with the service instead
# of depending on anyone remembering to restore them:
# /etc-side state does not survive VM replacement, and
# $HOME/.local/bin is only on PATH for login shells, so the
# links are the durable half and this heal is the other.
#
# Values derive from this script's own location; the
# link dir derives from $HOME (the unit renders HOME
# explicitly, so the watchdog's re-runs land in the
# owner's bin, not the service's).
set -u

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$OPS_DIR/../../.." && pwd)"
BIN_DIR="${HOME:?install-links: HOME is not set}/.local/bin"

QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

# name:target, the target relative to the repo root.
# runner is the owner's own name for the colab-run
# funnel: two names, one entry.
LINKS="
wb:pipeline/workrecord/wb
sched:pipeline/scheduling/bin/sched
harness:pipeline/scheduling/bin/harness
colab-run:pipeline/venue/bin/colab-run
colab-lease:pipeline/venue/bin/colab-lease
runner:pipeline/venue/bin/colab-run
"

mkdir -p "$BIN_DIR"

failed=0
for pair in $LINKS; do
    name="${pair%%:*}"
    target="$ROOT/${pair#*:}"
    link="$BIN_DIR/$name"
    if [ ! -x "$target" ]; then
        echo "install-links: $name: target $target is missing or not executable" >&2
        failed=1
        continue
    fi
    if [ -L "$link" ] && [ "$(readlink "$link")" = "$target" ]; then
        [ "$QUIET" -eq 0 ] || continue
        echo "$name: already-correct -> $target"
        continue
    fi
    if [ -e "$link" ] && [ ! -L "$link" ]; then
        echo "install-links: $name: $link exists and is not a symlink; refusing to replace it" >&2
        failed=1
        continue
    fi
    action=created
    [ -L "$link" ] && action=repaired
    # Stage the link beside its home and rename over:
    # the rename is the atomic act, and a failed stage
    # leaves any existing link untouched.
    staging="$link.install-links.tmp"
    rm -f "$staging"
    ln -s "$target" "$staging" && mv -f "$staging" "$link" || {
        echo "install-links: $name: could not install $link" >&2
        rm -f "$staging"
        failed=1
        continue
    }
    echo "$name: $action -> $target"
done
exit "$failed"
