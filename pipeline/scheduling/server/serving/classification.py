"""The served classification axis (contract 09, amendment
2026-11-13): every job view carries `audience`, and for
built-ins `family` + `open_in`. The client renders the axis
and never derives it, so it is served from here.

Home decision (recorded in contract 09's pipeline-serving
section): the axis is fleet taxonomy, ruled at the fleet
level by the amendment — it is not per-entry authored data,
so it does not ride the entry form (contract 14 carries no
classification fields); it lives in this module as pipeline
data beside the registry it classifies, and the API joins
it onto the view. An id the table does not list falls back
to operator / null / null — the fallback the contract's
fleet table itself implies (an unclassified job is the
operator's own until an amendment classifies it).
"""

# (audience, family, open_in) per entry id — the amendment's
# fleet table, verbatim. Family built-ins name their owning
# pipeline family and the shell surface their detail opens
# in; direct built-ins and operator jobs carry both as None.
_FLEET = {
    # Operator (3)
    "memory-index-watchdog": ("operator", None, None),
    "weekly-gmail-otp-cleanup": ("operator", None, None),
    "weekly-gmail-stale-jobs-cleanup": ("operator", None, None),
    # Built-in · family Venue (7) — open in Runner
    "colab-extend-guard": ("builtin", "venue", "runner"),
    "colab-liveness-brisk-rocket-38": ("builtin", "venue", "runner"),
    "colab-liveness-cozy-pilot-61-r1794547171": ("builtin", "venue", "runner"),
    "colab-liveness-dawn-tower-93": ("builtin", "venue", "runner"),
    "colab-runner-transient-restore": ("builtin", "venue", "runner"),
    "colab-store-prune": ("builtin", "venue", "runner"),
    "venue-healthcheck": ("builtin", "venue", "runner"),
    # Built-in · family Workbench (2) — open in Workbench
    "workbench-healthcheck": ("builtin", "workbench", "workbench"),
    "workbench-viewer-doctor": ("builtin", "workbench", "workbench"),
    # Built-in · family Dispatch (2) — open in Dispatch
    "bridge-drain": ("builtin", "dispatch", "dispatch"),
    "bridge-wake": ("builtin", "dispatch", "dispatch"),
    # Built-in · direct (9) — the app's own machinery
    "card-watch": ("builtin", None, None),
    "file-registry-check": ("builtin", None, None),
    "flap-watch": ("builtin", None, None),
    "local-test-watch": ("builtin", None, None),
    "restart-reconcile": ("builtin", None, None),
    "stale-mockup-cleanup": ("builtin", None, None),
    "storage-watch": ("builtin", None, None),
    "vm-restart-detector": ("builtin", None, None),
    "workhorse-healthcheck": ("builtin", None, None),
}

_FALLBACK = ("operator", None, None)


def classify(job_id):
    """The served triple for one entry id:
    {"audience": ..., "family": ..., "open_in": ...}."""
    audience, family, open_in = _FLEET.get(job_id, _FALLBACK)
    return {"audience": audience, "family": family, "open_in": open_in}
