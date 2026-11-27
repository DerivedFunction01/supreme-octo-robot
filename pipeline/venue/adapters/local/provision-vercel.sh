#!/bin/bash
# Instance-scoped Vercel provisioning for a local venue container.
#
# Usage (inside the instance's container):
#   provision-vercel.sh [apply]
#   provision-vercel.sh login
#
# The generic fleet template carries no app tooling: the Vercel
# CLI and its login belong to the one instance whose workload
# deploys through Vercel, and are provisioned from that
# instance's own state. This script is that provisioning — run
# it inside the container, by hand or from a job manifest.
#
# Modes:
#   apply   (default) ensure the pinned CLI, plant the login
#           from the instance state copy, and verify with
#           `whoami`. With no state copy there is nothing to
#           plant: the absence is named, the exit is 3, and no
#           verification is attempted — run `login` once to
#           create the state.
#   login   ensure the pinned CLI, run the CLI's device login
#           in the foreground (a human approves in a browser),
#           capture the resulting auth file back into the
#           instance state, and verify with `whoami`.
#
# State and knobs (every value defaulted, overridable by env):
#   VERCEL_VERSION     the pinned CLI version (default 65.14.0)
#   VERCEL_CLI_HOME    the CLI install home
#                      (default $HOME/vercel-cli)
#   VERCEL_AUTH_SOURCE the instance's persistent auth copy
#                      (default /workspace/vercel-auth.json —
#                      /workspace is the instance's own disk
#                      image, the path that survives a rebuild)
# The login itself lands where the CLI keeps it:
# $HOME/.local/share/com.vercel.cli/auth.json. A rebuild wipes
# the container home — CLI and planted login with it — and
# `apply` restores both from instance state.
set -euo pipefail

VERCEL_VERSION="${VERCEL_VERSION:-65.14.0}"
CLI_HOME="${VERCEL_CLI_HOME:-$HOME/vercel-cli}"
AUTH_SOURCE="${VERCEL_AUTH_SOURCE:-/workspace/vercel-auth.json}"
AUTH_TARGET="$HOME/.local/share/com.vercel.cli/auth.json"
VC="$CLI_HOME/node_modules/vercel/dist/vc.js"

usage() {
  echo "usage: provision-vercel.sh [apply|login]"
  echo "  apply   ensure the pinned CLI, plant the login from instance state, verify (default)"
  echo "  login   device-login in the foreground, capture the auth into instance state, verify"
}

MODE="${1:-apply}"
case "$MODE" in
  apply|login) ;;
  --help|-h) usage; exit 0 ;;
  *) echo "provision-vercel: unknown mode: $MODE" >&2; usage >&2; exit 2 ;;
esac
[ $# -gt 1 ] && { echo "provision-vercel: unexpected argument: $2" >&2; exit 2; }

installed_version() {
  [ -f "$CLI_HOME/node_modules/vercel/package.json" ] || return 1
  sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
    "$CLI_HOME/node_modules/vercel/package.json" | head -n 1
}

ensure_cli() {
  local v=""
  if [ -f "$VC" ]; then v="$(installed_version || true)"; fi
  if [ -n "$v" ] && [ "$v" = "$VERCEL_VERSION" ]; then
    echo "vercel CLI: present at $v (the pin), in $CLI_HOME"
    return 0
  fi
  echo "vercel CLI: installing $VERCEL_VERSION into $CLI_HOME (found: ${v:-none})"
  mkdir -p "$CLI_HOME"
  npm install --prefix "$CLI_HOME" "vercel@$VERCEL_VERSION"
  v="$(installed_version || true)"
  if [ "$v" != "$VERCEL_VERSION" ]; then
    echo "vercel CLI: install did not land $VERCEL_VERSION (found: ${v:-none})" >&2
    exit 1
  fi
  echo "vercel CLI: installed $v"
}

verify() {
  local out rc=0
  out="$(node "$VC" whoami 2>&1)" || rc=$?
  if [ $rc -eq 0 ]; then
    echo "vercel whoami: $out"
  else
    echo "vercel whoami: failed (exit $rc): $out" >&2
  fi
  return $rc
}

do_apply() {
  ensure_cli
  if [ ! -s "$AUTH_SOURCE" ]; then
    echo "vercel auth: no instance state at $AUTH_SOURCE — nothing to plant;" >&2
    echo "run 'provision-vercel.sh login' once to create it" >&2
    exit 3
  fi
  local src_sha dst_sha=""
  src_sha="$(sha256sum "$AUTH_SOURCE" | cut -d' ' -f1)"
  [ -f "$AUTH_TARGET" ] && dst_sha="$(sha256sum "$AUTH_TARGET" | cut -d' ' -f1)"
  if [ "$src_sha" = "$dst_sha" ]; then
    echo "vercel auth: the planted copy already matches instance state ($AUTH_TARGET)"
  else
    mkdir -p "$(dirname "$AUTH_TARGET")"
    cp "$AUTH_SOURCE" "$AUTH_TARGET"
    chmod 600 "$AUTH_TARGET"
    echo "vercel auth: planted from instance state ($AUTH_SOURCE -> $AUTH_TARGET)"
  fi
  if ! verify; then
    echo "vercel auth: the planted token was rejected. The CLI may have" >&2
    echo "consumed the planted copy at $AUTH_TARGET; the instance state at" >&2
    echo "$AUTH_SOURCE is untouched — re-running apply re-plants from it." >&2
    echo "If the state copy itself is stale, run 'provision-vercel.sh login'." >&2
    exit 1
  fi
}

do_login() {
  ensure_cli
  node "$VC" login
  if [ ! -s "$AUTH_TARGET" ]; then
    echo "vercel login: no auth file at $AUTH_TARGET after login" >&2
    exit 1
  fi
  mkdir -p "$(dirname "$AUTH_SOURCE")"
  cp "$AUTH_TARGET" "$AUTH_SOURCE"
  chmod 600 "$AUTH_SOURCE"
  echo "vercel auth: captured into instance state ($AUTH_SOURCE)"
  verify
}

case "$MODE" in
  apply) do_apply ;;
  login) do_login ;;
esac
