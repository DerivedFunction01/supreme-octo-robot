"""Launch-outcome classification: one pure verdict over a
terminal run record's own evidence, homed in a leaf module
so every record writer classes through the one home.

The measurement that prices this (wall-clock plan, step 1):
43.8% of fires ended with no verdict at all, and 82% of
those died before the job started — in upload, lease, or
launch. A record that says only "failed" cannot separate a
fire that never ran from a payload that ran and went red,
so the closing account cannot price the sink's movement.
This module is the separation: every terminal record gains
an `outcome_class` (stamped by records._prepare on every
save, so the local and Colab writers class identically),
drawn from exactly six classes:

- manifest — the fire's declared form was defective: a
  declared upload absent on disk, an invocation form the
  runner refuses. No venue work was attempted.
- transport — the tree or its bytes never arrived: a branch
  pin that does not resolve, a bundle seed that failed, the
  local venue's transport faces (unreachable, still warming).
- launch — the launch window died: the lease stage refused
  (budget included), an upload / mkdir / launch step failed,
  or the launch never landed. Upload and lease deaths ride
  this class — the window the record's stages name is the
  launch window, and the record cannot separate its steps
  further than their error text does.
- dispatch-blocked — the dispatch itself died in its firing
  context before the runner could act: the daemonized form's
  driver dead pre-launch, an orphaned record with no launch
  evidence. The approval-card deaths leave no record at all;
  these are the record-visible members of the class.
- ran-red — the payload ran and its outcome is red: a
  non-zero exit code, a payload-exit error, a session that
  died under a launched run.
- ran-green — the run completed.

THE MAPPING from today's state vocabulary (complete /
failed / orphaned — records.TERMINAL_STATES), applied in
order, first match wins:

1. A non-terminal state classes None — the field stays
   absent on non-terminal records.
2. complete → ran-green.
3. orphaned → launch when the record carries launch
   evidence (launch_at / launch_confirmed_at: it landed,
   and its loss sits in the post-launch window the record
   cannot separate from collection), else dispatch-blocked
   (nothing ever executed).
4. failed:
   a. A non-zero exit_code → ran-red (the payload's own
      report; the local finalize stamps it, Colab's
      finalize reports the same fact as error text, leg e).
   b. Error text naming the daemon driver → dispatch-blocked
      (the sweep's daemon-orphan write-off: the firing
      context's child died before the launch began).
   c. Error text naming a manifest defect → manifest.
   d. Error text naming a transport stage → transport.
   e. Error text naming a payload outcome → ran-red.
   f. Error text naming a launch step, or the lease stage's
      JSON refusal dump → launch.
   g. launch_lost with no stage text left → launch (the
      sweep's stale-launcher write-offs).
   h. Launch evidence (launch_at / launch_confirmed_at)
      → ran-red: it launched, so the failure is a run
      failure whose text names no earlier stage.
   i. Nothing separable → launch. Stated plainly: an
      un-evidenced failure cannot be told apart from the
      launch window's deaths, which are where un-evidenced
      deaths concentrate (82% of no-verdicts); the class
      claims the window, never a ran verdict the record
      does not carry.

The function reads only the record dict — no filesystem,
no package imports — so the standalone module loaders in
the test suite reach it without the runner's foundation,
and a reader holding any terminal record can re-derive its
class and get the same answer the writer stamped.
"""

import json

TERMINAL_STATES = ("complete", "failed", "orphaned")

# Stage needles, by class, in the mapping's check order.
# Each needle is a text the record writers actually stamp
# (the launch front end, the launch window, the finalize,
# the sweep, the local launch) — never a paraphrase.
_MANIFEST_NEEDLES = (
    "manifest upload missing locally",  # a declared upload absent on disk
    "requires the lease path",  # an invocation form the runner refuses
)
_TRANSPORT_NEEDLES = (
    "branch transport:",  # the branch pin / drive refusals
    "bundle seed:",  # the bundle transport's build, upload, verify
    "manifest transport",  # the transport declaration's own defects
    "venue unreachable",  # the local transport never answered
    "venue warmup",  # the local transport was still coming up
)
_RAN_RED_NEEDLES = (
    "job payload exited",  # finalize: the payload's non-zero code
    "job exited before completing",  # the launched process died early
    "payload exited 0 but collected none",  # it ran; collection is the red
    "confirmed absent after",  # the session died under a launched run
)
_LAUNCH_NEEDLES = (
    "runner script upload:",
    "manifest upload failed:",
    "script upload failed:",
    "venue mkdir failed:",
    "launch failed:",
    "launch never landed",
    "no job footprint",
    "launch exec",
)


def _has_launch_evidence(rec: dict) -> bool:
    return bool(rec.get("launch_at") or rec.get("launch_confirmed_at"))


def _is_lease_refusal(error: str) -> bool:
    """The lease stage's refusal, as dispatch stamps it: the
    acquire verdict dumped as JSON (budget refusals ride
    this shape — {"action": "refused-budget", ...})."""
    if not error.startswith("{"):
        return False
    try:
        verdict = json.loads(error)
    except ValueError:
        return False
    return isinstance(verdict, dict) and "action" in verdict


def classify_outcome(rec: dict) -> "str | None":
    """The record's outcome class, or None when the record
    is not terminal. Pure: a function of the record's own
    state, exit code, error text, and launch stamps only."""
    state = rec.get("state")
    if state not in TERMINAL_STATES:
        return None
    if state == "complete":
        return "ran-green"
    if state == "orphaned":
        return "launch" if _has_launch_evidence(rec) else "dispatch-blocked"
    # state == "failed"
    exit_code = rec.get("exit_code")
    if isinstance(exit_code, int) and exit_code != 0:
        return "ran-red"
    error = str(rec.get("error") or "")
    if "daemon" in error:
        return "dispatch-blocked"
    if any(needle in error for needle in _MANIFEST_NEEDLES):
        return "manifest"
    if any(needle in error for needle in _TRANSPORT_NEEDLES):
        return "transport"
    if any(needle in error for needle in _RAN_RED_NEEDLES):
        return "ran-red"
    if (
        any(needle in error for needle in _LAUNCH_NEEDLES)
        or (error.startswith("upload ") and " failed:" in error)
        or _is_lease_refusal(error)
    ):
        return "launch"
    if rec.get("launch_lost"):
        return "launch"
    if _has_launch_evidence(rec):
        return "ran-red"
    return "launch"
