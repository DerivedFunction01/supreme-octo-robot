#!/usr/bin/env bash
# The per-unit watchdog ladder: one ladder per systemd
# unit (workhorse, workbench, venue), selected by
# WORKHORSE_UNIT, each with its own episode marker and
# its own health verdict (healthcheck.py --unit). The
# ladder's verdict is supervision itself — an answering
# port never counts as recovered unless the responder is
# the supervised unit's own process.
#
# Doctrine change (the survival build, 2026-11-15): the
# S11 ladder refused to render units — a missing unit
# file was a fail-loud freeze act, because the render
# carried the ATTENTION_DATA binding. That refusal is
# retired. The render's values are not freeze-time
# literals: install-units.sh derives every one of them
# from its own location and the environment (ROOT,
# PYTHON, HOME, and ATTENTION_DATA as the platform's own
# state path under ROOT), exactly as the originals'
# installers did, so a render made at any time from this
# tree is the render the freeze would have made. The
# refusal's cost was measured: a VM replacement wipes
# /etc, every unit vanished, and nothing re-rendered
# them — detection reported LOST and stopped there.
#
# Rungs, in order:
#   set survival (before the per-unit rungs, on every
#     invocation): the nine unit files of units-spec.json
#     stand in the unit dir, or they do not. Presence is
#     the sentinel — file existence only, one spec read
#     plus one stat per unit, silent when whole. On any
#     absence: the full install pass (install-units.sh,
#     no unit argument — every missing/stale entry
#     installed, current ones untouched), then every
#     watchdog timer not active is started (a mid-life
#     install enables timers but does not start them).
#     This rung starts no service: a service whose file
#     was missing is classified and acted on by its own
#     unit's ladder, driven by its now-armed timer
#     within one tick. A failed install pass is UNKNOWN
#     state — fail loud, supervise nothing against it.
#     Why this rung exists: the 2026-11-16 reboot
#     (05:05Z) wiped /etc; the only boot-reachable
#     driver, the scheduler keeper hook, invokes this
#     ladder bare (its own unit, workhorse), so the
#     per-unit rung below healed workhorse and nothing
#     else — workbench, venue, and all six watchdog
#     units (the per-unit drivers are /etc units
#     themselves) stayed missing until a hand restore
#     at 05:16Z. Any invocation now heals the set it
#     belongs to, the keeper's bare call above all.
#   unit survival (before any health classification,
#     the originals' presence-before-health):
#       missing -> quiet install via install-units.sh
#                  (render + staged install + enable),
#                  then classification continues
#       stale   -> re-render/reinstall the same way
#       unknown -> fail loud (1): a unit whose state
#                  cannot be classified, or whose
#                  reinstall failed, is never restarted
#                  against and never read as supervised
#   healthy + supervised        -> silent 0 (the
#                                  workhorse ladder also
#                                  heals the short
#                                  command names,
#                                  install-links.sh)
#   a surface answers but the   -> FOREIGN: fail loud
#     unit is not active          (1); never race a
#                                  foreign process for
#                                  the ports
#   unit in the failed state    -> FAILED-UNIT
#     (start-limit exhaustion     recovery: reset-failed,
#      is the measured case)       then start, confirmed
#                                  on the restore window;
#                                  NOT gated by the
#                                  episode marker — a
#                                  bare restart cannot
#                                  clear start-limit
#                                  state, and gating this
#                                  rung behind the marker
#                                  would leave a settled
#                                  tree unstarted for the
#                                  whole episode; the
#                                  driver cadence (one act
#                                  per tick) is the gate
#   unit not active (and not    -> NOT-ACTIVE recovery:
#     failed)                       start when the unit
#                                  was never loaded at
#                                  this pass's entry,
#                                  restart when it stood
#                                  loaded (the originals'
#                                  load-state verb keying,
#                                  survival-contract v1
#                                  rung 6), confirmed on
#                                  the restore window,
#                                  one attempt per repair
#                                  episode. NOT gated by
#                                  the down streak: the
#                                  streak protects a
#                                  running serve whose
#                                  probe is merely silent;
#                                  a unit with no process
#                                  is systemd's own hard
#                                  signal, the same class
#                                  as the failed state.
#                                  The shape that turns
#                                  on it is the survival
#                                  rungs' own product: a
#                                  freshly installed unit
#                                  is enabled, not started
#                                  (install is presence),
#                                  and under the streak
#                                  alone it counted probe
#                                  failures until a hand
#                                  start (2026-11-18).
#   down + unit loaded          -> ONE restart per
#                                  episode (per-unit
#                                  marker, 900s),
#                                  confirmed against the
#                                  unit's own surfaces
#                                  on the 60s restore
#                                  window; a pass inside
#                                  a fresh episode
#                                  escalates (1) instead
#                                  of re-running the
#                                  repair. The down path
#                                  is reached only after
#                                  DOWN_STREAK_REQUIRED
#                                  consecutive failed
#                                  probes (the down-streak
#                                  rung at the act site):
#                                  one slow probe never
#                                  restarts a live unit.
#
# Values derive from this script's own location. The
# driver is systemd itself: each unit's watchdog timer
# (rendered by the same unit machinery, units-spec.json)
# starts this ladder for its own unit every 60s. The
# driver form before this cure — scheduler registry
# entries — ran inside workhorse.service, so that unit's
# failure silenced every unit's ladder at once
# (2026-11-16: no ladder ran 01:32–01:36Z while the unit
# sat in start-limit exhaustion, and recovery waited on
# a hand-issued reset-failed). A per-unit lock makes the
# ladder single-flight: overlapping invocations (a timer
# tick against a manual run) stand down silently.
set -u

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Argument surface: none (the unit rides WORKHORSE_UNIT).
# The empty declaration is parsed by the unified argv
# contract's bash adapter (contract home:
# pipeline/platform/argv.py; adapter: argv.sh in the
# same home, resolved from this script's own location):
# any argument is a usage refusal (exit 2); --help
# prints the generated usage.
. "$OPS_DIR/../argv.sh"
argv_tool watchdog.sh "The per-unit watchdog ladder: one ladder per systemd unit, selected by WORKHORSE_UNIT."
argv_parse "$@" || exit 2
[ "$ARGV_HELP" = 1 ] && exit 0

ROOT="$(cd "$OPS_DIR/../../.." && pwd)"
UNIT="${WORKHORSE_UNIT:-workhorse}"
STATE_DIR="$ROOT/pipeline/platform/var"
MARKER="$STATE_DIR/watchdog-episode-$UNIT"
STREAK="$STATE_DIR/watchdog-downstreak-$UNIT"
EPISODE_S="${WORKHORSE_WATCHDOG_EPISODE_S:-900}"
RESTORE_WINDOW_S="${WORKHORSE_WATCHDOG_RESTORE_WINDOW_S:-60}"
DOWN_STREAK_REQUIRED="${WORKHORSE_WATCHDOG_DOWN_STREAK:-3}"
PYTHON="${WORKHORSE_PYTHON:-python3}"
# The ladder's probe budget, exported for its own
# healthcheck invocations only (a hand-run probe keeps
# the probe's 5s default). 5s is an interactive budget:
# a supervised serve mid-assembly on a contended box
# can take longer than that to answer a health route
# that itself never computes — the answer queues for a
# thread slice behind the assembly's fan-out — and one
# such answer over budget read as death (2026-11-16:
# the workbench ladder restarted its unit 28 times in
# a day, 26 of them "restored" by the restart itself,
# including a clean stop of a mid-assembly serve at
# 23:50Z). 20s stands over ten times the worst healthy
# answer measured under assembly load (1.91s of 90
# probes at load 7–11) and still lands well inside the
# 60s driver tick. An explicit value in the environment
# wins, as with every seam in this file.
export WORKHORSE_HEALTH_TIMEOUT_S="${WORKHORSE_HEALTH_TIMEOUT_S:-20}"
# The installer's drill seams, adopted by the ladder so
# one override governs the whole machinery (a rehearsal
# that stubs the installer but not the ladder would
# rehearse against the live systemctl): inert unset.
UNIT_DIR="${WORKHORSE_UNIT_DIR:-/etc/systemd/system}"
SYSTEMCTL="${WORKHORSE_SYSTEMCTL:-systemctl}"
SPEC="$OPS_DIR/units-spec.json"
# The set read below parses the spec with the same
# interpreter resolution install-units.sh uses — NOT
# the WORKHORSE_PYTHON seam, which exists to simulate
# the health probe only.
if [ -x /usr/bin/python3 ]; then
    SPEC_PYTHON=/usr/bin/python3
else
    SPEC_PYTHON="$(command -v python3 || true)"
fi

mkdir -p "$STATE_DIR"

# Single-flight: one ladder run per unit at a time. A
# tick that finds its unit's ladder already running
# stands down silently (exit 0) — the running instance
# owns this tick's verdict, and a healthy tick is
# silent by design.
if command -v flock >/dev/null 2>&1; then
    exec 9>"$STATE_DIR/watchdog-$UNIT.lock"
    flock -n 9 || exit 0
fi

healthy() {
    "$PYTHON" "$OPS_DIR/healthcheck.py" --unit "$UNIT" \
        >/dev/null 2>&1
}

unit_active() {
    "$SYSTEMCTL" is-active --quiet "$UNIT" 2>/dev/null
}

unit_loaded() {
    [ "$("$SYSTEMCTL" show -p LoadState --value "$UNIT" \
        2>/dev/null)" = "loaded" ]
}

# Load state at entry — read before any rung acts,
# because the survival rungs below can install the
# unit during this very pass and change it. The
# originals key the repair verb on this reading: a
# unit systemd had never loaded when the pass began
# is the fresh-restore shape even though it stands
# loaded by the time anything acts.
LOADED_AT_ENTRY=0
unit_loaded && LOADED_AT_ENTRY=1

# Set survival rung — before the per-unit rungs, on
# every invocation, under this unit's flock. The unit
# set of record is units-spec.json; its installed names
# are read from the spec here (never a second hardcoded
# list that could drift from it). Presence is the whole
# sentinel: a stat per unit file. When the set is whole
# the rung is silent and costs that one read — the
# per-unit rung below still owns its own unit's
# missing/stale/unknown classification, staleness
# included; absence was the gap, because an absent
# unit's own ladder has no driver left to run it.
set_names="$("$SPEC_PYTHON" - "$SPEC" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    entries = json.load(fh)
for entry in entries:
    print(entry["out"])
PY
)" || set_names=""
if [ -z "$set_names" ]; then
    echo "watchdog: the unit set could not be read from $SPEC — state UNKNOWN; failing loud" >&2
    exit 1
fi
set_missing=""
for set_out in $set_names; do
    [ -f "$UNIT_DIR/$set_out" ] || set_missing="$set_missing $set_out"
done
if [ -n "$set_missing" ]; then
    echo "watchdog: unit set incomplete (missing:$set_missing); running the full install pass" >&2
    if ! "$OPS_DIR/install-units.sh" >/dev/null 2>&1; then
        echo "watchdog: unit set incomplete (missing:$set_missing) and the install pass failed — state UNKNOWN; failing loud instead of supervising against it" >&2
        exit 1
    fi
    # Arm the drivers: a mid-life install enables the
    # watchdog timers but does not start them, and an
    # enabled-but-unstarted timer drives nothing. An
    # already-active timer makes the start a no-op.
    # Services are deliberately NOT started here — each
    # service is classified and acted on by its own
    # unit's ladder, which its now-armed timer drives
    # within one tick (OnBootSec/OnUnitActiveSec=60).
    for set_out in $set_names; do
        case "$set_out" in
            *.timer)
                if ! "$SYSTEMCTL" is-active --quiet \
                        "$set_out" 2>/dev/null; then
                    if ! "$SYSTEMCTL" start "$set_out" \
                            2>/dev/null; then
                        echo "watchdog: timer $set_out could not be started after the install pass — the driver set is incomplete; failing loud" >&2
                        exit 1
                    fi
                    echo "watchdog: timer $set_out armed" >&2
                fi
                ;;
        esac
    done
    echo "watchdog: unit set restored (missing was:$set_missing); the full set stands installed" >&2
fi

# Unit survival rungs — before any health classification.
# install-units.sh --check prints "<unit>: <state>"; the
# state word is the classification. A check that cannot
# classify (its output names nothing) reads unknown. The
# check's stderr is captured, never discarded: an empty
# classification used to reach this rung with its cause
# thrown away (the 2026-11-20 outage's UNKNOWN verdicts),
# so the fail-loud line below carries the check's own
# error text.
check_err="$STATE_DIR/.check-stderr-$UNIT"
unit_state="$("$OPS_DIR/install-units.sh" --check "$UNIT" \
    2>"$check_err" | sed -n "s/^$UNIT: //p")"
if [ -z "$unit_state" ]; then
    # The direct check died without a verdict. In the
    # keeper/agent process class the host's intermittent
    # write-denial wave kills install-units' Python steps
    # while the unit being classified is healthy — the
    # false "server down" wake shape (three on 2026-11-21
    # alone). Re-run the same check through the scheduler
    # ops route: the scheduler server process is never
    # denied, so a healthy server's check classifies.
    # Only a check that yields nothing there too is
    # UNKNOWN. Under the systemd driver the direct check
    # classifies and this fallback never runs.
    SCHED="${WORKHORSE_SCHED:-$ROOT/pipeline/scheduling/bin/sched}"
    if [ -x "$SCHED" ]; then
        unit_state="$("$SCHED" exec \
            --caller "${WORKHORSE_SCHED_CALLER:-workhorse}" \
            --timeout 120 -- \
            bash "$OPS_DIR/install-units.sh" --check "$UNIT" \
            2>>"$check_err" | sed -n "s/^$UNIT: //p")"
    fi
fi
case "$unit_state" in
    current)
        ;;
    missing|stale)
        if ! "$OPS_DIR/install-units.sh" "$UNIT" \
                >/dev/null 2>&1; then
            echo "watchdog: unit $UNIT is $unit_state and its reinstall failed — state UNKNOWN; failing loud instead of restarting against it" >&2
            exit 1
        fi
        echo "watchdog: unit $UNIT was $unit_state; reinstalled from its tracked template render" >&2
        ;;
    *)
        err_tail="$(tail -n 3 "$check_err" 2>/dev/null \
            | tr '\n' ' ')"
        echo "watchdog: unit $UNIT state could not be classified (install-units --check gave '${unit_state:-nothing}'; its stderr: ${err_tail:-none captured}) — state UNKNOWN; failing loud" >&2
        exit 1
        ;;
esac

if healthy; then
    # Any answering verdict clears the down streak: the
    # count below is consecutive failures, never a
    # cumulative tally across recoveries.
    rm -f "$STREAK"
    if unit_active; then
        # The short command names (install-links.sh)
        # heal on the workhorse ladder's cadence only:
        # a missing or stale link is repaired in place,
        # speaking only when it acts. A heal failure is
        # noted on stderr, never a ladder verdict — the
        # ladder's verdict is supervision of the service
        # itself.
        if [ "$UNIT" = workhorse ]; then
            "$OPS_DIR/install-links.sh" --quiet || \
                echo "watchdog: link heal failed; run install-links.sh for the naming" >&2
        fi
        exit 0
    fi
    echo "watchdog: surfaces answer but unit $UNIT is not active — foreign process holds the ports; refusing to race it" >&2
    exit 1
fi

# Failed-unit rung — before the down path, and not
# gated by its episode marker. A unit systemd has
# marked failed — above all a unit in start-limit
# exhaustion, its StartLimitBurst spent inside
# StartLimitIntervalSec — cannot be recovered by the
# down path's act: a bare restart or start is refused
# ("start request repeated too quickly") until the
# failed state is reset, and the refused attempt would
# still burn the repair episode, suppressing retries
# for 900s. The act here is the manual recovery,
# mechanized: reset-failed, then start, confirmed
# against the unit's own surfaces on the restore
# window. systemd has already applied its own backoff
# (the burst limit is what produced this state), so
# the rung is gated only by the driver cadence — one
# act per tick: a tree still broken fails again and is
# retried next tick; a tree that has settled recovers
# on the first tick that sees it whole.
if "$SYSTEMCTL" is-failed --quiet "$UNIT" 2>/dev/null; then
    echo "watchdog: unit $UNIT is in the failed state; resetting the failed state and starting it (failed-unit recovery)" >&2
    if ! "$SYSTEMCTL" reset-failed "$UNIT" 2>/dev/null; then
        echo "watchdog: reset-failed failed for unit $UNIT" >&2
        exit 1
    fi
    if ! "$SYSTEMCTL" start "$UNIT" 2>/dev/null; then
        echo "watchdog: start failed for unit $UNIT after reset-failed" >&2
        exit 1
    fi
    deadline=$(( $(date +%s) + RESTORE_WINDOW_S ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if healthy; then
            echo "watchdog: unit $UNIT restored; its surfaces answer" >&2
            exit 0
        fi
        sleep 3
    done
    echo "watchdog: unit $UNIT did not answer within ${RESTORE_WINDOW_S}s of the failed-unit recovery" >&2
    exit 1
fi

# Not-active rung — before the down-streak rung, and
# not gated by it, for the failed-unit rung's reason:
# systemd's state is a hard signal, not the ladder's
# inference from a silent probe. The streak below
# protects a RUNNING serve whose health answer may
# only be slow — mid-assembly, the answer queues
# behind the fan-out — and for that shape three
# consecutive silent probes are the price of acting.
# A unit that is not active has no serve to protect:
# no process exists whose answer could be queued.
# The shape that turns on it is the survival rungs'
# own product — a host replacement wipes the unit
# set, the rungs above reinstall and enable it, and
# install is presence, not motion: the service
# stands loaded and enabled but never started, and
# under the streak alone it counted probe failures
# ("consecutive failure 1 of 3; not acting") until a
# hand start recovered it (2026-11-18, boot
# ab0acf72; workhorse started by hand at 15:29:24Z).
# The originals' shape separation (the starter kit's
# ladder; survival-contract v1 rung 6, the
# load-state repair verb) classifies this shape from
# systemd's state and acts on the pass that sees it:
# a unit that was never loaded at this pass's entry
# is STARTED, a unit that stood loaded is RESTARTED
# — restarting a unit that was never loaded is spent
# motion — confirmed against the unit's own surfaces
# on the restore window. One attempt per repair
# episode, like the down path's act: a start that
# does not take is escalated inside the episode, not
# retried into a start loop.
if ! unit_active; then
    now="$(date +%s)"
    if [ -f "$MARKER" ]; then
        last="$(cat "$MARKER" 2>/dev/null || echo 0)"
        case "$last" in *[!0-9]*) last=0 ;; esac
        if [ $((now - last)) -lt "$EPISODE_S" ]; then
            echo "watchdog: unit $UNIT is not active and this episode already had its repair attempt (last attempt ${last}); escalating instead of re-running" >&2
            exit 1
        fi
    fi
    if ! "$SYSTEMCTL" cat "$UNIT" >/dev/null 2>&1; then
        echo "watchdog: unit $UNIT is not loaded although its file stands — state UNKNOWN; failing loud" >&2
        exit 1
    fi
    echo "$now" > "$MARKER"
    if [ "$LOADED_AT_ENTRY" -eq 1 ]; then
        verb=restart
    else
        verb=start
    fi
    echo "watchdog: unit $UNIT is not active; ${verb}ing it (not-active recovery — a unit with no process is acted on, not streak-counted)" >&2
    if ! "$SYSTEMCTL" "$verb" "$UNIT" 2>/dev/null; then
        echo "watchdog: $verb failed for unit $UNIT" >&2
        exit 1
    fi
    deadline=$(( $(date +%s) + RESTORE_WINDOW_S ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if healthy; then
            echo "watchdog: unit $UNIT restored; its surfaces answer" >&2
            exit 0
        fi
        sleep 3
    done
    echo "watchdog: unit $UNIT did not answer within ${RESTORE_WINDOW_S}s of the not-active recovery" >&2
    exit 1
fi

# Down-streak rung — before the down path's act, and
# deliberately NOT before the failed-unit rung above:
# a unit systemd has marked failed is a hard signal
# (a crash loop that spent its start limit), recovered
# per tick exactly as before. What is gated here is
# the ladder's own inference from a silent probe. A
# probe reads a serve's worst moment, not its state:
# mid-assembly the health answer queues behind the
# fan-out on a contended box, and the 2026-11-16
# ladder — one failed probe, one restart — killed
# healthy serves all day, each restart "restoring" a
# process that had never been dead (and the fresh
# process's own warm-up assembly then failed further
# probes inside the episode). So the down act now
# requires DOWN_STREAK_REQUIRED consecutive failed
# probes across driver ticks (~65s apart): a serve
# that answers even once inside that window is never
# restarted, and a truly dead serve — which answers
# never — is acted on after ~3 ticks of sustained
# silence, the named trade against the old ~1 tick.
streak=0
if [ -f "$STREAK" ]; then
    streak="$(cat "$STREAK" 2>/dev/null || echo 0)"
    case "$streak" in *[!0-9]*) streak=0 ;; esac
fi
streak=$((streak + 1))
echo "$streak" > "$STREAK"
if [ "$streak" -lt "$DOWN_STREAK_REQUIRED" ]; then
    echo "watchdog: unit $UNIT surfaces down (consecutive failure $streak of $DOWN_STREAK_REQUIRED); not acting — a slow-but-alive serve is not restarted" >&2
    exit 1
fi
rm -f "$STREAK"

# Down. One repair attempt per episode.
now="$(date +%s)"
if [ -f "$MARKER" ]; then
    last="$(cat "$MARKER" 2>/dev/null || echo 0)"
    case "$last" in *[!0-9]*) last=0 ;; esac
    if [ $((now - last)) -lt "$EPISODE_S" ]; then
        echo "watchdog: still down inside the repair episode (last attempt ${last}); escalating instead of re-running" >&2
        exit 1
    fi
fi

if ! "$SYSTEMCTL" cat "$UNIT" >/dev/null 2>&1; then
    echo "watchdog: unit $UNIT is not loaded although its file stands — state UNKNOWN; failing loud" >&2
    exit 1
fi

echo "$now" > "$MARKER"
echo "watchdog: unit $UNIT surfaces down; restarting unit $UNIT (one attempt this episode)" >&2
"$SYSTEMCTL" restart "$UNIT" 2>/dev/null || \
    "$SYSTEMCTL" start "$UNIT" 2>/dev/null || {
        echo "watchdog: restart command failed for unit $UNIT" >&2
        exit 1
    }

deadline=$((now + RESTORE_WINDOW_S))
while [ "$(date +%s)" -lt "$deadline" ]; do
    if healthy; then
        echo "watchdog: unit $UNIT restored; its surfaces answer" >&2
        exit 0
    fi
    sleep 3
done
echo "watchdog: unit $UNIT did not answer within ${RESTORE_WINDOW_S}s of the restart" >&2
exit 1
