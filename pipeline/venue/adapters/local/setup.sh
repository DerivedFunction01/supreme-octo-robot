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
#   --target DIR          install dir (default: $HOME/muse-compute)
#   --authkey KEY         Tailscale auth key (or env TS_AUTHKEY)
#   --cpus N              workspace CPU cap      (default 4)
#   --mem SIZE            workspace memory cap   (default 8g)
#   --workspace-gb N      workspace image size   (default 96)
#   --total-gb N          total disk budget      (default 128)
#   --authorized-key KEY  one SSH public key line for authorized_keys
#   --skip-mount          do not create/mount the workspace image
#   --skip-docker         generate files only; do not build or start
#   --yes                 never prompt (missing authkey is an error)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$HERE/template"
TARGET="${HOME}/muse-compute"
AUTHKEY="${TS_AUTHKEY:-}"
CPUS=4; MEM=8g; WORKSPACE_GB=96; TOTAL_GB=128
AUTH_KEY_LINE=""; SKIP_MOUNT=0; SKIP_DOCKER=0; ASSUME_YES=0

while [ $# -gt 0 ]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --authkey) AUTHKEY="$2"; shift 2 ;;
    --cpus) CPUS="$2"; shift 2 ;;
    --mem) MEM="$2"; shift 2 ;;
    --workspace-gb) WORKSPACE_GB="$2"; shift 2 ;;
    --total-gb) TOTAL_GB="$2"; shift 2 ;;
    --authorized-key) AUTH_KEY_LINE="$2"; shift 2 ;;
    --skip-mount) SKIP_MOUNT=1; shift ;;
    --skip-docker) SKIP_DOCKER=1; shift ;;
    --yes) ASSUME_YES=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

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
prompt AUTHKEY "Tailscale auth key (from the tailnet that will use this venue)" silent
[ -n "$AUTHKEY" ] || { echo "no auth key given" >&2; exit 2; }
case "$AUTHKEY" in tskey-*) : ;; *) echo "warning: auth key does not start with tskey-" >&2 ;; esac
if [ -z "$AUTH_KEY_LINE" ] && [ ! -f "$TARGET/authorized_keys" ]; then
  prompt AUTH_KEY_LINE "SSH public key for the connecting agent (ssh-ed25519 ...)"
fi

echo "==> target $TARGET (cpus=$CPUS mem=$MEM workspace=${WORKSPACE_GB}G total=${TOTAL_GB}G)"
mkdir -p "$TARGET/workspace"
for f in Dockerfile docker-compose.yml entrypoint.sh disk-guard.sh .dockerignore .gitignore crontab.example; do
  cp "$TEMPLATE/$f" "$TARGET/$f"
done
chmod +x "$TARGET/entrypoint.sh" "$TARGET/disk-guard.sh"

# Instance files: .env is the only place the key and limits live.
{
  echo "TS_AUTHKEY=$AUTHKEY"
  echo "COMPUTE_MEM=$MEM"
  echo "COMPUTE_CPUS=$CPUS"
  echo "DISK_WARN_GB=$((TOTAL_GB - 8))"
  echo "DISK_STOP_GB=$TOTAL_GB"
} > "$TARGET/.env"
chmod 600 "$TARGET/.env"
[ -n "$AUTH_KEY_LINE" ] && printf '%s\n' "$AUTH_KEY_LINE" > "$TARGET/authorized_keys"

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
if command -v crontab >/dev/null 2>&1; then
  (crontab -l 2>/dev/null | grep -v disk-guard || true; echo "*/15 * * * *  $TARGET/disk-guard.sh") | crontab -
  echo "==> disk-guard cron installed"
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
echo "==> done: venue is up at agent-ubuntu on the tailnet"
