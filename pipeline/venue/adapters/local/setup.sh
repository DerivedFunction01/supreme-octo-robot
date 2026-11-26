#!/bin/bash
# One-command setup for a local compute venue host (WSL2 + Docker).
#
# Usage (from a clone of this repo):
#   pipeline/venue/adapters/local/setup.sh [--target DIR] [options]
#
# It copies the tracked template/ into the target, writes the
# instance .env + authorized_keys from the values given (prompting
# for any that are missing), creates the capped workspace image,
# installs the disk-guard cron, builds and starts the containers,
# and smokes the result. Every value can be a flag, an env var, or
# a prompt answer — the operator never edits a file by hand and
# never pastes a heredoc.
#
# Options:
#   --target DIR          install dir (default: $HOME/agent-workspace)
#   --name NAME           tailnet node name (default: agent-ubuntu;
#                         name each machine, e.g. its branding —
#                         never the tailnet's counter-suffixed name)
#   --authkey KEY         Tailscale auth key (or env TS_AUTHKEY)
#   --cpus N              workspace CPU cap      (default 4)
#   --mem SIZE            workspace memory cap   (default 8g)
#   --workspace-gb N      workspace image size   (default 96)
#   --total-gb N          total disk budget      (default 128)
#   --authorized-key KEY  one SSH public key line for authorized_keys
#   --github-key-file F   private key file for GitHub clones from
#                         inside the container; copied into the
#                         instance at mode 600 and planted by the
#                         entrypoint on every start (preserved on
#                         re-runs, like the auth key)
#   --vercel-auth-file F  Vercel CLI auth.json (the login state);
#                         copied into the instance at mode 600
#                         as vercel-auth.json and planted by the
#                         entrypoint on every start, on the
#                         --github-key-file pattern (preserved
#                         on re-runs)
#   --skip-mount          do not create/mount the workspace image
#   --skip-docker         generate files only; do not build or start
#   --yes                 never prompt (missing authkey is an error)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$HERE/template"

# Argument surface, declared once and parsed by the
# unified argv contract's bash adapter (contract home:
# pipeline/platform/argv.py; adapter: argv.sh in the
# same home). This script executes from inside a
# checkout (its usage form), so the adapter resolves
# from the script's own location — no Python dependency
# is taken. Both --flag value and --flag=value are the
# same flag; an unknown flag or a value flag missing
# its value is a usage refusal (exit 2); --help prints
# the usage generated from this declaration.
. "$HERE/../../../platform/argv.sh"
argv_tool setup.sh "One-command setup for a local compute venue host (WSL2 + Docker)."
argv_global_flag target value "default=${HOME}/agent-workspace"
argv_global_flag name value
argv_global_flag authkey value
argv_global_flag cpus value default=4
argv_global_flag mem value default=8g
argv_global_flag workspace-gb value default=96
argv_global_flag total-gb value default=128
argv_global_flag authorized-key value
argv_global_flag github-key-file value
argv_global_flag vercel-auth-file value
argv_global_flag skip-mount bool
argv_global_flag skip-docker bool
argv_global_flag yes bool
argv_parse "$@" || exit 2
[ "$ARGV_HELP" = 1 ] && exit 0

TARGET="${ARGV_FLAGS[target]}"
VENUE_NAME="${TS_HOSTNAME:-}"
[ -n "${ARGV_PRESENT[name]:-}" ] && VENUE_NAME="${ARGV_FLAGS[name]}"
AUTHKEY="${TS_AUTHKEY:-}"
[ -n "${ARGV_PRESENT[authkey]:-}" ] && AUTHKEY="${ARGV_FLAGS[authkey]}"
CPUS="${ARGV_FLAGS[cpus]}"; MEM="${ARGV_FLAGS[mem]}"
WORKSPACE_GB="${ARGV_FLAGS[workspace-gb]}"; TOTAL_GB="${ARGV_FLAGS[total-gb]}"
AUTH_KEY_LINE="${ARGV_FLAGS[authorized-key]}"
GH_KEY_FILE="${ARGV_FLAGS[github-key-file]}"
VERCEL_AUTH_FILE="${ARGV_FLAGS[vercel-auth-file]}"
SKIP_MOUNT=0; [ "${ARGV_FLAGS[skip-mount]}" = true ] && SKIP_MOUNT=1
SKIP_DOCKER=0; [ "${ARGV_FLAGS[skip-docker]}" = true ] && SKIP_DOCKER=1
ASSUME_YES=0; [ "${ARGV_FLAGS[yes]}" = true ] && ASSUME_YES=1

prompt() { # prompt VAR "label" [silent]
  local var="$1" label="$2" silent="${3:-}"
  [ -n "${!var}" ] && return 0
  [ "$ASSUME_YES" = 1 ] && { echo "missing value: $label (and --yes given)" >&2; exit 2; }
  if [ -n "$silent" ]; then read -rsp "$label: " "$var"; echo; else read -rp "$label: " "$var"; fi
}

# Preserve an existing .env authkey on re-runs (key rotation is an
# explicit --authkey, never a side effect of re-running setup).
if [ -z "$AUTHKEY" ] && [ -f "$TARGET/.env" ]; then
  AUTHKEY=$(grep -oP '^TS_AUTHKEY=\K.+' "$TARGET/.env" || true)
fi
# Same preservation for the node name: a re-run keeps the name the
# instance registered with; renaming is an explicit --name.
if [ -z "$VENUE_NAME" ] && [ -f "$TARGET/.env" ]; then
  VENUE_NAME=$(grep -oP '^TS_HOSTNAME=\K.+' "$TARGET/.env" || true)
fi
[ -n "$VENUE_NAME" ] || VENUE_NAME=agent-ubuntu
prompt AUTHKEY "Tailscale auth key (from the tailnet that will use this venue)" silent
[ -n "$AUTHKEY" ] || { echo "no auth key given" >&2; exit 2; }
case "$AUTHKEY" in tskey-*) : ;; *) echo "warning: auth key does not start with tskey-" >&2 ;; esac
if [ -z "$AUTH_KEY_LINE" ] && [ ! -f "$TARGET/authorized_keys" ]; then
  prompt AUTH_KEY_LINE "SSH public key for the connecting agent (ssh-ed25519 ...)"
fi

echo "==> target $TARGET (name=$VENUE_NAME cpus=$CPUS mem=$MEM workspace=${WORKSPACE_GB}G total=${TOTAL_GB}G)"
mkdir -p "$TARGET/workspace"
for f in Dockerfile docker-compose.yml entrypoint.sh disk-guard.sh .dockerignore .gitignore crontab.example known_hosts_github; do
  cp "$TEMPLATE/$f" "$TARGET/$f"
done
chmod +x "$TARGET/entrypoint.sh" "$TARGET/disk-guard.sh"

# Instance files: .env is the only place the key and limits live.
{
  echo "TS_AUTHKEY=$AUTHKEY"
  echo "TS_HOSTNAME=$VENUE_NAME"
  echo "COMPUTE_MEM=$MEM"
  echo "COMPUTE_CPUS=$CPUS"
  echo "DISK_WARN_GB=$((TOTAL_GB - 8))"
  echo "DISK_STOP_GB=$TOTAL_GB"
} > "$TARGET/.env"
chmod 600 "$TARGET/.env"
[ -n "$AUTH_KEY_LINE" ] && printf '%s\n' "$AUTH_KEY_LINE" > "$TARGET/authorized_keys"
# The GitHub clone key is instance state beside authorized_keys:
# given once via --github-key-file, preserved on re-runs (setup
# never removes it), and planted into the container by the
# entrypoint on every start.
if [ -n "$GH_KEY_FILE" ]; then
  cp "$GH_KEY_FILE" "$TARGET/id_github"
  chmod 600 "$TARGET/id_github"
fi
# The Vercel auth copy is instance state the same way: given
# once via --vercel-auth-file, preserved on re-runs, planted
# into the container by the entrypoint on every start.
if [ -n "$VERCEL_AUTH_FILE" ]; then
  cp "$VERCEL_AUTH_FILE" "$TARGET/vercel-auth.json"
  chmod 600 "$TARGET/vercel-auth.json"
fi

# Workspace hard cap: fixed-size ext4 image, loop-mounted.
if [ "$SKIP_MOUNT" = 0 ]; then
  if mountpoint -q "$TARGET/workspace"; then
    echo "==> workspace already mounted, leaving it as is"
  else
    [ -f "$TARGET/workspace.img" ] || { truncate -s "${WORKSPACE_GB}G" "$TARGET/workspace.img"; mkfs.ext4 -q "$TARGET/workspace.img"; }
    sudo mount -o loop "$TARGET/workspace.img" "$TARGET/workspace"
    sudo chown "$USER:$USER" "$TARGET/workspace"
    grep -q "$TARGET/workspace.img" /etc/fstab 2>/dev/null || \
      echo "$TARGET/workspace.img $TARGET/workspace ext4 loop,defaults 0 0" | sudo tee -a /etc/fstab >/dev/null
  fi
fi

# Disk guard cron (idempotent: replaces any prior disk-guard line).
# The guard needs a cron binary: install the package when missing
# rather than silently skipping the guard.
if ! command -v crontab >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
  echo "==> installing cron (the disk guard needs it)"
  sudo apt-get install -y cron || true
fi
if command -v crontab >/dev/null 2>&1; then
  (crontab -l 2>/dev/null | grep -v disk-guard || true; echo "*/15 * * * *  $TARGET/disk-guard.sh") | crontab -
  echo "==> disk-guard cron installed"
else
  echo "warning: no crontab available; disk-guard cron not installed" >&2
fi

# The build pulls public images only, and a credential-store
# entry naming a helper that cannot execute in this distro —
# Docker Desktop's .exe, planted in the docker config by its
# WSL integration — breaks every pull. Drop desktop-helper
# store references; a working in-distro helper is untouched,
# and no pull here needs credentials.
DOCKER_CFG="${DOCKER_CONFIG:-$HOME/.docker}/config.json"
if [ -f "$DOCKER_CFG" ] && grep -q 'desktop' "$DOCKER_CFG" && command -v python3 >/dev/null 2>&1; then
  python3 -c '
import json, sys
p = sys.argv[1]
try:
    with open(p) as fh:
        d = json.load(fh)
except Exception:
    sys.exit(0)
changed = False
if "desktop" in str(d.get("credsStore", "")):
    d.pop("credsStore"); changed = True
helpers = d.get("credHelpers")
if isinstance(helpers, dict):
    for reg in [k for k, v in helpers.items() if "desktop" in str(v)]:
        helpers.pop(reg); changed = True
if changed:
    with open(p, "w") as fh:
        json.dump(d, fh, indent=2)
    print("==> removed Docker Desktop credential-store entries (public pulls need none)")
' "$DOCKER_CFG"
fi

if [ "$SKIP_DOCKER" = 1 ]; then
  echo "==> files generated (--skip-docker); start with: (cd $TARGET && docker compose up -d --build)"
  exit 0
fi

echo "==> building and starting"
(cd "$TARGET" && docker compose up -d --build && docker compose ps)
echo "==> tailscale status (must list the venue's other nodes as peers)"
docker exec agent-tailscale tailscale status || true
echo "==> toolchain smoke"
docker exec agent-workspace bash -lc 'python3 --version; node --version; uv --version; git --version; fd --version; sqlite3 --version; df -h /workspace /tmp | grep -v Filesystem; cat /sys/fs/cgroup/cpu.max; cat /sys/fs/cgroup/memory.max'
echo "==> done: venue is up at $VENUE_NAME on the tailnet"
