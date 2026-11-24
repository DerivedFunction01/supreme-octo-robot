"""Session-side bundle fetch with a prerequisite pre-flight.

A gate wrap clones the on-session checkout and fetches a staged
bundle for lineage. The fetch fails — and the gate dies before
any verdict — when the clone lacks the bundle's prerequisite
commit. That prerequisite is unobtainable session-side when it
sits on unpushed local lineage, and obtainable from origin when
the clone is merely stale. This module is the single seam for
that step: it verifies the prerequisite is present, heals the
stale-clone variant by fetching origin into the PRIVATE clone,
and fails fast with a NAMED verdict (never a bare "bundle fetch
failed") when the prerequisite is on no reachable remote.

Stdlib only. It runs on the session, standalone — it must never
import venue modules. The runner uploads it beside every job's
wrap (main.py, on the wrap's own import marker); the wrap does
`import bundle_fetch` and calls `fetch_bundle` in place of its
bare `git fetch <bundle> <ref>`.

The shared session checkout is never refreshed here: the
substrate is shared state and a wrap must not move it under
other lanes. The origin fetch lands in the wrap's private clone
only.
"""

import re
import subprocess

_PREREQ_RE = re.compile(r"^([0-9a-f]{40}) ", re.MULTILINE)


def _run(argv, timeout):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def _present(clone, sha):
    return _run(["git", "-C", clone, "cat-file", "-e", sha + "^{commit}"], 60).returncode == 0


def _prerequisites(bundle_path):
    """The commits `git bundle verify` says the bundle requires.

    A root snapshot bundle requires none — the pre-flight is then
    vacuous and the fetch proceeds. On any verify failure the
    empty list is returned and the caller falls back to the
    declared base, so a verify quirk never blocks a fetch the
    pre-flight cannot judge.
    """
    try:
        r = _run(["git", "bundle", "verify", str(bundle_path)], 120)
    except Exception:
        return []
    if r.returncode != 0:
        return []
    out = r.stdout + r.stderr
    marker = "prerequisite commits:"
    if marker not in out:
        return []
    section = out.split(marker, 1)[1]
    return _PREREQ_RE.findall(section)


def fetch_bundle(clone, bundle_path, ref, base, origin_url, branch="main", log=None):
    """Fetch a bundle into a private clone, after its pre-flight.

    clone: the wrap's private clone path. bundle_path: the staged
    bundle. ref: the bundle ref to fetch. base: the declared delta
    base (fallback prerequisite when verify names none).
    origin_url: the repo's origin URL (from the resident checkout's
    remote.origin.url); used only to heal a stale clone.
    Returns (returncode, verdict) where verdict is a dict with at
    least "verdict" in {"ok", "healed_via_origin",
    "prereq_absent"}; on "prereq_absent" the fetch never ran.
    """
    log = log or (lambda msg: None)
    want = _prerequisites(bundle_path) or ([base] if base else [])
    missing = [sha for sha in want if not _present(clone, sha)]
    if missing:
        log(f"bundle prerequisite absent from clone: {missing} — fetching origin {branch}")
        if origin_url:
            healed = _run(
                ["git", "-C", clone, "fetch", origin_url, branch], 600
            )
            log(healed.stderr[-1000:])
        missing = [sha for sha in want if not _present(clone, sha)]
        if missing:
            return 2, {
                "verdict": "prereq_absent",
                "missing": missing,
                "error": (
                    "bundle prerequisite absent: "
                    + ", ".join(missing)
                    + " — the bundle was built on lineage not in the session clone "
                    + "and on no reachable remote; re-bundle on origin lineage or "
                    + "as a root snapshot"
                ),
            }
        log("bundle prerequisite healed via origin fetch")
        verdict = "healed_via_origin"
    else:
        verdict = "ok"
    fetch = _run(
        ["git", "-C", clone, "fetch", str(bundle_path), ref], 1200
    )
    log(fetch.stderr[-2000:])
    if fetch.returncode != 0:
        return 2, {
            "verdict": "fetch_failed",
            "error": "bundle fetch failed",
        }
    return 0, {"verdict": verdict}
