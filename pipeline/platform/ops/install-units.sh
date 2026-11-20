#!/usr/bin/env bash
# Install the platform's systemd units from their tracked
# templates — the installer half of the VM-restart
# survival pattern (the originals' form: tracked template
# + installer, presence before health, render-when-
# invalid, staged install, enable on install).
#
# The render set of record is units-spec.json beside this
# script: one entry per unit — its template (in this
# directory), its installed name, and the value seams its
# template carries. The set carries the three fleet
# services and, per fleet unit, its watchdog driver pair
# (a oneshot ladder service and the timer that starts
# it): the ladder's driver is systemd itself, after the
# scheduler-entry form died with the unit it watched in
# the 2026-11-16 outage. An entry may carry
# "enable": false — the watchdog services carry it (no
# [Install]; their timers are the enablement) — and every
# other entry is enabled under its installed name. The
# spec names seams, never values: every value resolves
# here, at run time, from this script's own location and
# the environment —
#   ROOT           this repo's root (the script's
#                  location, three levels up)
#   PYTHON         /usr/bin/python3 where it exists,
#                  else the python3 on PATH
#   HOME           the caller's $HOME (the units render
#                  it explicitly, so a supervisor-run
#                  install lands in the owner's home,
#                  not the service's)
#   ATTENTION_DATA the migrated attention store's path,
#                  $ROOT/pipeline/platform/var/
#                  attention-state.json — a seam of the
#                  platform's own layout, derived from
#                  ROOT like every other value
# That derivation is what retires the old freeze-act
# objection to ladder-side rendering: no value is a
# freeze-time literal, so a render made at any time from
# this tree is the render the freeze would have made.
#
# Rendering itself is the cutover mechanism
# (ops/cutover/render_units.py): it substitutes the
# spec's values, refuses a render still carrying a
# token, and systemd-analyze-verifies every render — a
# render that cannot be verified does not install.
#
# Modes:
#   install-units.sh             install every unit whose
#                                installed file is missing
#                                or stale; enable every
#                                enableable entry
#   install-units.sh <unit>      the same, one unit (any
#                                unit key in the spec: a
#                                fleet unit, a watchdog
#                                service, a watchdog timer)
#   install-units.sh --check     install nothing; print
#     [--check] <unit>           "<unit>: missing|stale|
#                                current|unknown" per unit
#                                and exit 1 unless every
#                                selected unit is current
#
# An install stages the verified render beside the unit
# file (<unit>.tmp), hash-verifies the staged bytes
# against the render, and only then renames it over the
# unit — a denied or partial stage leaves the installed
# unit untouched. A daemon-reload follows any file
# change, and every selected enableable unit is enabled
# (the templates carry [Install]; a unit present but not
# enabled does not survive a boot, which is the failure
# this script exists to close). The watchdog services
# are the one exception: enable:false in the spec, no
# [Install] in their templates — their timers carry the
# [Install] and are what gets enabled. Each landed install
# leaves a receipt in the platform state dir
# (var/unit-<unit>.installed: the installed render's
# sha256 and the UTC time) — the registry entries name
# that receipt as the unit file's state of record,
# because the registry's portability rule cannot carry
# the unit file's own absolute path.
#
# Idempotent; one line per unit on stdout; failures are
# named on stderr and exit 1. No interactive input — the
# watchdog runs this on its cadence for its own unit's
# survival rung. Drill seams (env): WORKHORSE_UNIT_DIR
# (the systemd unit directory), WORKHORSE_SYSTEMCTL (the
# systemctl command).
set -u

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$OPS_DIR/../../.." && pwd)"
SPEC="$OPS_DIR/units-spec.json"
RENDER_UNITS="$OPS_DIR/cutover/render_units.py"
UNIT_DIR="${WORKHORSE_UNIT_DIR:-/etc/systemd/system}"
SYSTEMCTL="${WORKHORSE_SYSTEMCTL:-systemctl}"
STATE_DIR="$ROOT/pipeline/platform/var"

if [ -x /usr/bin/python3 ]; then
    PYTHON=/usr/bin/python3
else
    PYTHON="$(command -v python3 || true)"
fi
[ -n "$PYTHON" ] || {
    echo "install-units: no python3 available" >&2
    exit 1
}
: "${HOME:?install-units: HOME is not set}"
ATTENTION_DATA="$ROOT/pipeline/platform/var/attention-state.json"

MODE=install
ONLY=""
ONLY_CANDIDATE=""
for arg in "$@"; do
    case "$arg" in
        --check) MODE=check ;;
        *) ONLY_CANDIDATE="$arg" ;;
    esac
done

SCRATCH="$(mktemp -d)" || exit 1
trap 'rm -rf "$SCRATCH"' EXIT

# Generate one concrete render spec per unit from the
# render set of record, resolving the named seams to
# this host's values, plus the unit -> installed-name /
# enablement map the shell half resolves through. The
# unit list is read from the same generation, so the
# spec file is the only table.
"$PYTHON" - "$SPEC" "$OPS_DIR" "$SCRATCH" \
    "$ROOT" "$PYTHON" "$HOME" "$ATTENTION_DATA" <<'PY'
import json
import os
import sys

spec_path, ops_dir, scratch = sys.argv[1:4]
values = dict(zip(("ROOT", "PYTHON", "HOME",
                   "ATTENTION_DATA"), sys.argv[4:8]))
with open(spec_path, encoding="utf-8") as fh:
    entries = json.load(fh)
with open(os.path.join(scratch, "outs.tsv"), "w",
          encoding="utf-8") as map_fh:
    for entry in entries:
        concrete = [{
            "template": os.path.join(ops_dir,
                                     entry["template"]),
            "out": entry["out"],
            "values": {key: values[key]
                       for key in entry["values"]},
        }]
        out_path = os.path.join(scratch,
                                f"spec-{entry['unit']}.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(concrete, fh)
        enable = 0 if entry.get("enable") is False else 1
        map_fh.write(
            f"{entry['unit']}\t{entry['out']}\t{enable}\n")
PY
GENERATED_RC=$?
[ "$GENERATED_RC" -eq 0 ] || {
    echo "install-units: could not read $SPEC" >&2
    exit 1
}

declare -A OUT_FOR=()
declare -A ENABLE_FOR=()
while IFS=$'\t' read -r map_unit map_out map_enable; do
    [ -n "$map_unit" ] || continue
    OUT_FOR["$map_unit"]="$map_out"
    ENABLE_FOR["$map_unit"]="$map_enable"
done < "$SCRATCH/outs.tsv"

# The units to act on, in spec order (regenerated above;
# the list is re-read from the spec, not the generation's
# stdout, so a generation failure cannot invent units).
UNITS="$("$PYTHON" -c '
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    print(" ".join(e["unit"] for e in json.load(fh)))
' "$SPEC")" || {
    echo "install-units: could not list units in $SPEC" >&2
    exit 1
}
if [ -n "$ONLY_CANDIDATE" ]; then
    ONLY="$ONLY_CANDIDATE"
    case " $UNITS " in
        *" $ONLY "*) UNITS="$ONLY" ;;
        *) echo "install-units: $ONLY is not in $SPEC" >&2; exit 1 ;;
    esac
fi

# Render one unit into the scratch dir via the cutover
# mechanism. Returns non-zero when the render fails or
# cannot be verified; the render then does not exist.
render_one() {
    "$PYTHON" "$RENDER_UNITS" \
        --spec "$SCRATCH/spec-$1.json" \
        --out-dir "$SCRATCH/renders" >/dev/null 2>&1
}

render_sha() {
    local sha
    sha="$(sha256sum "$SCRATCH/renders/${OUT_FOR[$1]}" \
        2>/dev/null)" || return 1
    sha="${sha%% *}"
    [ -n "$sha" ] || return 1
    echo "$sha"
}

# missing | stale | current | unknown — a failed render
# or an unreadable unit hashes to unknown, never stale,
# so a render failure can never trigger a reinstall.
unit_state() {
    local unit="$1" expected actual
    render_one "$unit" || { echo unknown; return; }
    if [ ! -f "$UNIT_DIR/${OUT_FOR[$unit]}" ]; then
        echo missing
        return
    fi
    expected="$(render_sha "$unit")" || {
        echo unknown; return; }
    actual="$(sha256sum "$UNIT_DIR/${OUT_FOR[$unit]}" \
        2>/dev/null)" || { echo unknown; return; }
    actual="${actual%% *}"
    if [ "$actual" = "$expected" ]; then
        echo current
    else
        echo stale
    fi
}

# Stage the verified render beside the unit file, verify
# the staged bytes against the render, rename over.
install_one() {
    local unit="$1" expected staged_sha
    local out="${OUT_FOR[$unit]}"
    expected="$(render_sha "$unit")" || return 1
    cp "$SCRATCH/renders/$out" \
        "$UNIT_DIR/$out.tmp" 2>/dev/null || {
        rm -f "$UNIT_DIR/$out.tmp"
        return 1
    }
    staged_sha="$(sha256sum \
        "$UNIT_DIR/$out.tmp" 2>/dev/null)" || {
        rm -f "$UNIT_DIR/$out.tmp"
        return 1
    }
    staged_sha="${staged_sha%% *}"
    if [ "$staged_sha" != "$expected" ]; then
        rm -f "$UNIT_DIR/$out.tmp"
        return 1
    fi
    mv "$UNIT_DIR/$out.tmp" \
        "$UNIT_DIR/$out" || return 1
    mkdir -p "$STATE_DIR"
    local receipt="$STATE_DIR/unit-$unit.installed"
    printf '%s %s\n' "$expected" \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        > "$receipt.tmp" && mv -f "$receipt.tmp" "$receipt"
}

if [ "$MODE" = check ]; then
    failed=0
    for unit in $UNITS; do
        state="$(unit_state "$unit")"
        echo "$unit: $state"
        [ "$state" = current ] || failed=1
    done
    exit "$failed"
fi

failed=0
changed=0
for unit in $UNITS; do
    state="$(unit_state "$unit")"
    case "$state" in
        current)
            echo "$unit: current"
            ;;
        missing|stale)
            if install_one "$unit"; then
                changed=1
                if [ "$state" = missing ]; then
                    echo "$unit: installed"
                else
                    echo "$unit: re-rendered"
                fi
            else
                echo "install-units: $unit: install failed (state $state)" >&2
                failed=1
            fi
            ;;
        *)
            echo "install-units: $unit: state unknown; not installing" >&2
            failed=1
            ;;
    esac
done

if [ "$changed" -eq 1 ]; then
    "$SYSTEMCTL" daemon-reload 2>/dev/null || {
        echo "install-units: daemon-reload failed" >&2
        failed=1
    }
fi
# Enablement is part of the install: a unit systemd has
# not been told to start at boot is not survival, however
# current its file is. Enable is idempotent; its output
# is captured so the one-line-per-unit report stands.
# Entries the spec marks enable:false are skipped — the
# watchdog services, whose timers carry the enablement.
for unit in $UNITS; do
    [ "${ENABLE_FOR[$unit]}" = 1 ] || continue
    "$SYSTEMCTL" enable "${OUT_FOR[$unit]}" >/dev/null 2>&1 || {
        echo "install-units: $unit: systemctl enable failed" >&2
        failed=1
    }
done
exit "$failed"
