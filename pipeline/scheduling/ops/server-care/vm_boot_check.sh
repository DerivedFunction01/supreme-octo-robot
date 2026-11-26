#!/usr/bin/env bash
# VM restart detector: compare the kernel boot id
# (/proc/sys/kernel/random/boot_id) with the value recorded by the
# previous run in this job's state file. A reboot or a VM replacement
# always changes the boot id; a scheduler-server restart never does.
#
# Exit codes: 0 = same boot (silence), baseline adopted (silence), or
# boot changed (exactly one RESTART line, plus one LOST line per
# environment probe that fails); 3 = the boot-id source is unreadable
# on this host, so the check cannot run — a distinct outcome the
# entry declares, so a platform change is loud rather than silently
# never firing.
#
# On a detected boot change the same run probes what a replacement
# drops outside the persisted home: the fleet's systemd units (files
# present, units active) and the four surfaces the two units serve.
# Enablement is deliberately not probed:
# workhorse.service is active but disabled on this machine —
# the runtime starts it after each boot — so a disabled verdict
# would false-fire on every real restart. Python installs are not
# probed either — every one the fleet depends on lives in the
# persisted home and survives a replacement by construction.
#
# Paths are derived from this script's own location (portability
# rule: no hardcoded home/workspace paths in tracked files);
# SCHEDULER_VM_BOOT_STATE / SCHEDULER_VM_BOOT_ID_FILE override.
set -uo pipefail
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/paths.sh"

# Argument surface: none. The empty declaration is
# parsed by the unified argv contract's bash adapter
# (contract home: pipeline/platform/argv.py; adapter:
# argv.sh in the same home, resolved from this script's
# own location): any argument is a usage refusal
# (exit 2); --help prints the generated usage. The
# refusal stands apart from this script's own verdict
# exits (0 / 3) documented above.
. "$SCHED_OPS_DIR/../../platform/argv.sh"
argv_tool vm_boot_check.sh "VM restart detector: compare the kernel boot id with the previous run's record."
argv_parse "$@" || exit 2
[ "$ARGV_HELP" = 1 ] && exit 0
REPO_ROOT="$SCHED_REPO_ROOT"
STATE_FILE="${SCHEDULER_VM_BOOT_STATE:-$REPO_ROOT/state/vm-boot/last_boot_id}"
BOOT_ID_FILE="${SCHEDULER_VM_BOOT_ID_FILE:-/proc/sys/kernel/random/boot_id}"
UNITS="workhorse.service workbench.service venue.service"
# The three units serve four surfaces (scheduler and attention
# on workhorse.service; the workbench on workbench.service;
# the lease panel on venue.service — process boundaries follow
# coupling, 2026-11-15); a unit that is up with a dead surface
# is a loss the boot report should name.
SURFACES="scheduler:8796:/health workbench:8792:/api/health attention:8797:/health lease-panel:8793:/"

if [ ! -r "$BOOT_ID_FILE" ]; then
  echo "vm-boot-check: boot id source unreadable: $BOOT_ID_FILE"
  exit 3
fi
CURRENT="$(tr -d '[:space:]' < "$BOOT_ID_FILE")"
if [ -z "$CURRENT" ]; then
  echo "vm-boot-check: boot id source unreadable: $BOOT_ID_FILE"
  exit 3
fi

RECORDED=""
if [ -r "$STATE_FILE" ]; then
  RECORDED="$(head -n 1 "$STATE_FILE" | tr -d '[:space:]')"
fi

record() {
  local dir tmp
  dir="$(dirname "$STATE_FILE")"
  mkdir -p "$dir"
  tmp="$STATE_FILE.tmp.$$"
  printf '%s\n' "$CURRENT" > "$tmp"
  mv "$tmp" "$STATE_FILE"
}

if [ -z "$RECORDED" ]; then
  record
  exit 0
fi

if [ "$RECORDED" = "$CURRENT" ]; then
  exit 0
fi

record
BOOTED="$(uptime -s 2>/dev/null || echo unknown)"
echo "RESTART: boot changed $RECORDED -> $CURRENT (booted $BOOTED)"
for unit in $UNITS; do
  if [ ! -f "/etc/systemd/system/$unit" ]; then
    echo "LOST: systemd unit file missing: $unit"
  elif ! systemctl is-active --quiet "$unit" 2>/dev/null; then
    echo "LOST: systemd unit not active: $unit"
  fi
done
for spec in $SURFACES; do
  name="${spec%%:*}"; rest="${spec#*:}"; port="${rest%%:*}"; path="${rest#*:}"
  if ! curl -sf --max-time 5 "http://127.0.0.1:$port$path" >/dev/null 2>&1; then
    echo "LOST: surface not answering: $name http://127.0.0.1:$port$path"
  fi
done
exit 0
