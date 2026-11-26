#!/usr/bin/env python3
"""Publish proof — the served-data proof for a published
workhorse artifact (contract 09 rebuild, design section 4).

The proof exercises the PUBLISHED artifact's own action
channel, per app, and cross-checks what comes back against
direct reads of the same backends. It never takes a verdict
from the backends directly: a backend read is evidence, the
artifact's served payload is the thing judged. This is the
mechanism whose absence let the mock-fed v37 embed pass a
bundle-hash check while its apps never reached a server.

Per app, four assertions (the design's five, with the
honest-unreachable leg separated — see below):

  1. bridge liveness — the app's health/overview action
     returns through the artifact's bridge with a real
     HTTP status and the bridge envelope's error null.
  2. live markers — the served payload carries values only
     a live backend produces now: the scheduler overview's
     served_at inside a freshness window and its registry
     totals; the workbench feeds/projects carrying the live
     project set; the runner's records carrying venue
     "colab"; the attention glance/today served shapes.
  3. cross-check equality — stable identity sets/counts in
     the served payload equal a direct backend read of the
     same surface (runner session ids + CU balance vs
     /api/state; scheduler job count vs /api/v1/jobs;
     workbench project slugs vs the direct read; attention
     counts vs the direct glance/today). Direct reads are
     taken before and after the artifact call; equality
     with either discharges the check, so a value that
     legitimately moves mid-proof does not flake it.
  4. seed/mock absence — the served payload contains none
     of the SEED_MARKERS below. The marker list is data,
     harvested from the apps' own mock/seed sources (the
     runner seed leases and display names in
     apps/runner/frontend/src/venue, the 412 CU seed
     opening balance, the workbench seed project slugs in
     apps/workbench/frontend/src/lib/seed.ts, the
     scheduler mock seed ids in
     apps/scheduler/frontend/src/mock/seeds.ts, the
     attention seed item titles/ids from the dropped
     standalone app's seed — standing as data below). A marker
     hit means the artifact is serving compiled-in seed
     data, whatever its bundle hash says. For workbench
     the scan is structural — the seed slugs are checked
     against the served PROJECT SET, not the raw feeds
     text: the live 58 MB document legitimately quotes
     the seed source itself inside repo diffs (the mega
     repo is one of its own projects), so a raw substring
     scan false-fires on live data, while the mock-fed
     form serves the seed projects AS the project set,
     which the structural check catches exactly.

  5. the honest-unreachable leg (--leg dead-port) — run
     against a staging publish whose bridge config points
     the runner at a dead port: the proof passes only when
     the artifact surfaces the bridge's status 0 with a
     null payload and the unreachable sentence, and NO
     fabricated data. This leg runs at rebuild acceptance,
     not per publish; it is a named, separately-invoked
     mode of this script.

Channels (how the proof reaches the artifact's actions):

  --channel http --base-url URL — POST {action, args} to
  URL/actions, the serving-shape protocol (the step-3
  local serve speaks it; a published space whose actions
  endpoint is directly fetchable would too). This is the
  only channel that attempts the workbench getFeeds
  document end-to-end: the document is ~58 MB.

  --channel bridge --bridge-dir DIR — the file bridge for
  artifacts reachable only through the platform's action
  tooling: the proof writes requests/<n>.json and waits
  for results/<n>.json, serviced by the publish-act agent
  through the artifact action tools. The workbench leg on
  this channel proves health + the live project set; the
  58 MB feeds document is NOT hauled over the tool bridge
  (its result would not survive the tool channel) — the
  report names the substitution, and the feeds assertions
  run on the http channel in the prep verification and in
  the acceptance drive.

  --channel static --mirror DIR — a static artifact has
  no action channel: assertions 1 and 3 fail by
  construction, and assertion 4 scans the files the
  artifact serves (the mirror's entry document + assets,
  which a static publish serves byte-for-byte). This is
  the channel the deliberately mock-fed staging publish
  is proved against.

Report: JSON at --report, shape {artifact_slug,
artifact_version, channel, proved_at, apps: {<app>:
{verdict, assertions: {...}}}, verdict}. The cutover
preflight's published-surface check consumes exactly this
shape: per-app verdicts all pass, artifact_version equal
to the freeze record's live_version, proved_at after the
recorded publish instant.

Exit 0 = the proof passes; 1 = it fails (the report says
where); 2 = usage error (channel unreachable, bridge
timeout, unreadable mirror). Read-only against the
backends; the only writes are the report and the bridge
request files.
"""

import importlib.util as _importlib_util
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

# The argv contract home, loaded through the platform paths module.
_ps = _importlib_util.spec_from_file_location(
    "platform_paths", Path(__file__).parent.parent / "paths.py")
_paths = _importlib_util.module_from_spec(_ps); _ps.loader.exec_module(_paths)
_as = _importlib_util.spec_from_file_location(
    "pipeline_platform_argv", os.path.join(_paths.PACKAGE_DIR, "argv.py"))
platform_argv = _importlib_util.module_from_spec(_as)
_as.loader.exec_module(platform_argv)

DECLARATION = {
    "name": "publish_proof",
    "flags": {
        "slug": {"takes_value": True, "required": True},
        "version": {"takes_value": True, "required": True},
        "channel": {"takes_value": True, "required": True,
                    "choices": ["http", "bridge", "static"]},
        "base-url": {"takes_value": True},
        "bridge-dir": {"takes_value": True},
        "mirror": {"takes_value": True},
        "apps": {"takes_value": True, "default": "workbench,scheduler,runner,attention"},
        "leg": {"takes_value": True, "choices": ["dead-port"]},
        "report": {"takes_value": True, "required": True},
    },
}

# ------------------------------------------------------------------
# Seed markers (assertion 4) — data, harvested from the apps'
# mock/seed sources as the module docstring records. Substring
# markers are matched against the JSON-serialized served
# payload for the app; the runner balance marker is structural
# (the seed opening balance as the served budget balance).
# ------------------------------------------------------------------

SEED_MARKERS = {
    "runner": [
        "cozy-pilot-61", "ember-comet-32", "storm-compass-26",
        "Cozy Pilot 61", "Ember Comet 32", "Storm Compass 26",
    ],
    "workbench": [
        "fennelwick", "sablebrook", "wintermere", "sorrelfield",
        "Superapp storyboard — launcher",
    ],
    "scheduler": [
        "01mock00000000000000seed", "b41d77aa09c3",
    ],
    "attention": [
        "Northwind cutover rehearsal", "main:northwind-rehearsal", "Rig 12 — renewal due",
    ],
}

RUNNER_SEED_BALANCE_CU = 412

BACKENDS = {
    "workbench": "http://127.0.0.1:8792",
    "runner": "http://127.0.0.1:8793",
    "scheduler": "http://127.0.0.1:8796",
    "attention": "http://127.0.0.1:8797",
}

FRESHNESS_WINDOW_S = 180
BALANCE_EPSILON_CU = 0.05


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(text):
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _http_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


# ------------------------------------------------------------------
# Channels
# ------------------------------------------------------------------

class ChannelError(Exception):
    pass


class HttpChannel:
    name = "http"

    def __init__(self, base_url):
        self.base = base_url.rstrip("/")

    def call(self, action, args):
        body = json.dumps({"action": action, "args": args}).encode("utf-8")
        req = urllib.request.Request(
            self.base + "/actions", data=body,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as res:
                reply = json.loads(res.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 — the channel is the evidence
            raise ChannelError(f"POST {self.base}/actions failed: {exc}")
        if isinstance(reply, dict) and reply.get("error"):
            return {"ok": False, "error": str(reply["error"]), "data": None}
        return {"ok": True, "error": None,
                "data": reply.get("data") if isinstance(reply, dict) else reply}


class BridgeChannel:
    name = "bridge"

    def __init__(self, bridge_dir, timeout=900):
        self.dir = bridge_dir
        self.timeout = timeout
        self.seq = 0
        os.makedirs(os.path.join(bridge_dir, "requests"), exist_ok=True)
        os.makedirs(os.path.join(bridge_dir, "results"), exist_ok=True)

    def call(self, action, args):
        self.seq += 1
        req_id = f"{self.seq:03d}-{action}"
        req_path = os.path.join(self.dir, "requests", req_id + ".json")
        res_path = os.path.join(self.dir, "results", req_id + ".json")
        with open(req_path, "w", encoding="utf-8") as fh:
            json.dump({"id": req_id, "action": action, "args": args}, fh)
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if os.path.isfile(res_path):
                with open(res_path, encoding="utf-8") as fh:
                    result = json.load(fh)
                if result.get("ok"):
                    return {"ok": True, "error": None,
                            "data": result.get("data")}
                return {"ok": False, "data": None,
                        "error": str(result.get("error"))}
            time.sleep(2)
        raise ChannelError(
            f"bridge request {req_id} unserviced after {self.timeout}s")


class StaticChannel:
    name = "static"

    def __init__(self, mirror):
        self.mirror = mirror

    def call(self, action, args):
        return {"ok": False, "data": None,
                "error": "static artifact: no action channel exists"}

    def served_text(self):
        chunks = []
        for root, _dirs, files in os.walk(self.mirror):
            if ".space-build" in root or "/." in root:
                continue
            for name in sorted(files):
                if name.endswith((".html", ".js", ".css", ".json")):
                    path = os.path.join(root, name)
                    try:
                        with open(path, encoding="utf-8",
                                  errors="replace") as fh:
                            chunks.append(fh.read())
                    except OSError:
                        continue
        return "\n".join(chunks)


# ------------------------------------------------------------------
# Assertion helpers
# ------------------------------------------------------------------

def _bridge_reply(data):
    """The apps' actions return the bridge envelope
    {status, payload, error}; anything else is not a bridge
    reply at all."""
    if isinstance(data, dict) and "status" in data and "payload" in data:
        return data
    return None


def _liveness(reply_data):
    reply = _bridge_reply(reply_data)
    if reply is None:
        return False, "action result is not a bridge reply {status, payload, error}"
    if reply.get("error") is not None:
        return False, f"bridge error non-null: {reply.get('error')}"
    status = reply.get("status")
    if not isinstance(status, int) or status < 200 or status >= 300:
        return False, f"bridge status {status!r} is not a real 2xx HTTP status"
    return True, f"bridge status {status}, error null"


def _project_slugs(node, depth=0):
    """Project slug set from a projects payload in any of the
    shapes the backend serves it: a bare list, {projects:
    [...]}, or the feeds document whose projects member is
    itself {projects: [...], errors: [...]}."""
    if isinstance(node, list):
        return {p.get("slug") for p in node if isinstance(p, dict)}
    if isinstance(node, dict) and depth < 3:
        inner = node.get("projects")
        if isinstance(inner, (list, dict)):
            return _project_slugs(inner, depth + 1)
    return None


def _marker_scan(app, payload_text):
    hits = [m for m in SEED_MARKERS.get(app, []) if m in payload_text]
    return hits


def _direct(app, path, timeout=30):
    return _http_json(BACKENDS[app] + path, timeout=timeout)


def _bracketed(app, path, timeout=120):
    """Direct reads before/after the artifact call; either
    may discharge a cross-check."""
    reads = []
    for _ in range(2):
        try:
            reads.append(_direct(app, path, timeout=timeout))
        except Exception as exc:  # noqa: BLE001
            reads.append({"__error__": str(exc)})
    return reads


# ------------------------------------------------------------------
# Per-app legs. Each returns (verdict, assertions dict, served
# payload text for the marker scan).
# ------------------------------------------------------------------

def _fail_all(reason):
    return {name: {"pass": False, "detail": reason}
            for name in ("bridge_liveness", "live_markers",
                         "cross_check", "seed_absence")}


def leg_workbench(channel):
    assertions = {}
    served = []
    health = channel.call("getHealth", {})
    if not health["ok"]:
        return "fail", _fail_all(
            f"getHealth did not return through the channel: {health['error']}"), ""
    served.append(json.dumps(health["data"]))
    ok, detail = _liveness(health["data"])
    assertions["bridge_liveness"] = {"pass": ok, "detail": detail}

    projects_reply = channel.call("listProjects", {})
    feeds_reply = None
    if channel.name == "http":
        feeds_reply = channel.call("getFeeds", {})
    if projects_reply["ok"]:
        served.append(json.dumps(projects_reply["data"]))
    if feeds_reply and feeds_reply["ok"]:
        # Only the feeds document's projects member joins
        # the marker scan (see the module docstring: the
        # document's diff payloads legitimately quote the
        # seed source on live data).
        freply = _bridge_reply(feeds_reply["data"])
        if freply and isinstance(freply.get("payload"), dict):
            served.append(json.dumps(
                freply["payload"].get("projects")))

    # Live markers + cross-check: the live project set.
    direct = _bracketed("workbench", "/api/projects")
    direct_sets = []
    for read in direct:
        slugs = _project_slugs(read)
        if slugs is not None:
            direct_sets.append(slugs)
    served_slugs = None
    payload = _bridge_reply(projects_reply["data"]) if projects_reply["ok"] else None
    if payload:
        served_slugs = _project_slugs(payload.get("payload"))
    feeds_slugs = None
    if feeds_reply and feeds_reply["ok"]:
        freply = _bridge_reply(feeds_reply["data"])
        if freply:
            feeds_slugs = _project_slugs(freply.get("payload"))
    marker_ok = bool(served_slugs) and any(
        served_slugs == s for s in direct_sets)
    assertions["live_markers"] = {
        "pass": marker_ok,
        "detail": ("served project set carries the live projects: "
                   + ", ".join(sorted(served_slugs))) if marker_ok else
                  f"served project slugs {sorted(served_slugs or [])} "
                  f"match no direct /api/projects read "
                  f"{[sorted(s) for s in direct_sets]}"}
    cross_ok = marker_ok
    cross_detail = assertions["live_markers"]["detail"]
    if feeds_slugs is not None:
        feeds_match = any(feeds_slugs == s for s in direct_sets)
        cross_ok = cross_ok and feeds_match
        cross_detail += ("; feeds document project set "
                         + ("equals the direct read"
                            if feeds_match else
                            f"{sorted(feeds_slugs)} equals no direct read"))
    elif channel.name == "bridge":
        cross_detail += ("; the 58 MB feeds document is not hauled over "
                         "the tool bridge — its project-set equality runs "
                         "on the http channel (prep verification) and in "
                         "the acceptance drive")
    assertions["cross_check"] = {"pass": cross_ok, "detail": cross_detail}

    text = "\n".join(served)
    hits = _marker_scan("workbench", text)
    assertions["seed_absence"] = {
        "pass": not hits,
        "detail": ("no seed markers in the served payload" if not hits
                   else f"seed markers served: {hits}")}
    verdict = "pass" if all(a["pass"] for a in assertions.values()) else "fail"
    return verdict, assertions, text


def leg_scheduler(channel):
    assertions = {}
    served = []
    overview = channel.call("getOverview", {})
    if not overview["ok"]:
        return "fail", _fail_all(
            f"getOverview did not return through the channel: {overview['error']}"), ""
    served.append(json.dumps(overview["data"]))
    ok, detail = _liveness(overview["data"])
    assertions["bridge_liveness"] = {"pass": ok, "detail": detail}
    reply = _bridge_reply(overview["data"])
    payload = reply.get("payload") if reply else None

    # Live markers: served_at fresh + registry totals present.
    marker_bits = []
    marker_ok = isinstance(payload, dict)
    if marker_ok:
        served_at = _parse_iso(str(payload.get("served_at", "")))
        if served_at is None:
            marker_ok = False
            marker_bits.append("overview carries no parseable served_at")
        else:
            age = abs((_now() - served_at).total_seconds())
            if age > FRESHNESS_WINDOW_S:
                marker_ok = False
            marker_bits.append(f"served_at age {age:.0f}s "
                               f"(window {FRESHNESS_WINDOW_S}s)")
        registry = payload.get("registry") or {}
        if not isinstance(registry.get("total"), int):
            marker_ok = False
            marker_bits.append("registry.total missing")
        else:
            marker_bits.append(f"registry.total {registry['total']}")
    else:
        marker_bits.append("overview payload is not an object")
    assertions["live_markers"] = {"pass": marker_ok,
                                  "detail": "; ".join(marker_bits)}

    # Cross-check: artifact job set vs direct /api/v1/jobs.
    jobs = channel.call("getJobs", {})
    if jobs["ok"]:
        served.append(json.dumps(jobs["data"]))
    jreply = _bridge_reply(jobs["data"]) if jobs["ok"] else None
    jpayload = jreply.get("payload") if jreply else None
    served_ids = None
    if isinstance(jpayload, dict) and isinstance(jpayload.get("jobs"), list):
        served_ids = {j.get("id") for j in jpayload["jobs"]
                      if isinstance(j, dict)}
    direct = _bracketed("scheduler", "/api/v1/jobs")
    direct_sets = []
    for read in direct:
        if isinstance(read, dict) and isinstance(read.get("jobs"), list):
            direct_sets.append({j.get("id") for j in read["jobs"]
                                if isinstance(j, dict)})
    cross_ok = served_ids is not None and any(
        served_ids == s for s in direct_sets)
    assertions["cross_check"] = {
        "pass": cross_ok,
        "detail": (f"artifact job set ({len(served_ids)} jobs) equals a "
                   f"direct /api/v1/jobs read" if cross_ok else
                   f"artifact job ids {sorted(served_ids or [])} match no "
                   f"direct read {[sorted(s) for s in direct_sets]}")}

    text = "\n".join(served)
    hits = _marker_scan("scheduler", text)
    assertions["seed_absence"] = {
        "pass": not hits,
        "detail": ("no seed markers in the served payload" if not hits
                   else f"seed markers served: {hits}")}
    verdict = "pass" if all(a["pass"] for a in assertions.values()) else "fail"
    return verdict, assertions, text


def leg_runner(channel):
    assertions = {}
    served = []
    state = channel.call("getState", {})
    if not state["ok"]:
        return "fail", _fail_all(
            f"getState did not return through the channel: {state['error']}"), ""
    served.append(json.dumps(state["data"]))
    ok, detail = _liveness(state["data"])
    assertions["bridge_liveness"] = {"pass": ok, "detail": detail}
    reply = _bridge_reply(state["data"])
    payload = reply.get("payload") if reply else None

    # Live markers: every record carries venue "colab".
    records = payload.get("records") if isinstance(payload, dict) else None
    venues = []
    session_ids = set()
    if isinstance(records, list):
        for entry in records:
            rec = entry.get("record") if isinstance(entry, dict) else None
            if isinstance(rec, dict):
                venues.append(rec.get("venue"))
                if rec.get("session"):
                    session_ids.add(rec["session"])
    marker_ok = bool(records) and all(v == "colab" for v in venues) \
        and payload.get("venue") == "colab"
    assertions["live_markers"] = {
        "pass": marker_ok,
        "detail": (f"{len(records or [])} records, venues "
                   f"{sorted(set(venues))}, panel venue "
                   f"{payload.get('venue') if isinstance(payload, dict) else None!r}")}

    # Cross-check: session id set + CU balance vs direct /api/state.
    direct = _bracketed("runner", "/api/state")
    direct_sets = []
    direct_balances = []
    for read in direct:
        if isinstance(read, dict) and isinstance(read.get("records"), list):
            ids = set()
            for entry in read["records"]:
                rec = entry.get("record") if isinstance(entry, dict) else None
                if isinstance(rec, dict) and rec.get("session"):
                    ids.add(rec["session"])
            direct_sets.append(ids)
            budget = read.get("budget") or {}
            if isinstance(budget.get("balance"), (int, float)):
                direct_balances.append(budget["balance"])
    served_balance = None
    if isinstance(payload, dict):
        budget = payload.get("budget") or {}
        if isinstance(budget.get("balance"), (int, float)):
            served_balance = budget["balance"]
    ids_ok = any(session_ids == s for s in direct_sets)
    bal_ok = served_balance is not None and any(
        abs(served_balance - b) <= BALANCE_EPSILON_CU
        for b in direct_balances)
    assertions["cross_check"] = {
        "pass": ids_ok and bal_ok,
        "detail": (f"session ids {'equal' if ids_ok else 'DIFFER'} "
                   f"({len(session_ids)} served); balance served "
                   f"{served_balance} vs direct {direct_balances} "
                   f"(epsilon {BALANCE_EPSILON_CU} CU)")}

    text = "\n".join(served)
    hits = _marker_scan("runner", text)
    if served_balance == RUNNER_SEED_BALANCE_CU:
        hits.append(f"budget.balance == {RUNNER_SEED_BALANCE_CU} "
                    f"(the seed opening balance)")
    assertions["seed_absence"] = {
        "pass": not hits,
        "detail": ("no seed markers in the served payload" if not hits
                   else f"seed markers served: {hits}")}
    verdict = "pass" if all(a["pass"] for a in assertions.values()) else "fail"
    return verdict, assertions, text


def leg_attention(channel):
    assertions = {}
    served = []
    glance = channel.call("getGlance", {})
    if not glance["ok"]:
        return "fail", _fail_all(
            f"getGlance did not return through the channel: {glance['error']}"), ""
    served.append(json.dumps(glance["data"]))
    ok, detail = _liveness(glance["data"])
    assertions["bridge_liveness"] = {"pass": ok, "detail": detail}
    reply = _bridge_reply(glance["data"])
    payload = reply.get("payload") if reply else None

    today = channel.call("getToday", {})
    if today["ok"]:
        served.append(json.dumps(today["data"]))
    treply = _bridge_reply(today["data"]) if today["ok"] else None
    tpayload = treply.get("payload") if treply else None

    # Live markers: the glance/today served shapes.
    marker_bits = []
    marker_ok = isinstance(payload, dict)
    if marker_ok:
        if payload.get("contract") != "api/1":
            marker_ok = False
            marker_bits.append(f"glance contract {payload.get('contract')!r}")
        if not isinstance(payload.get("decision_count"), int):
            marker_ok = False
            marker_bits.append("glance decision_count missing")
        else:
            marker_bits.append(f"decision_count {payload['decision_count']}")
        if not isinstance(payload.get("presence"), dict):
            marker_ok = False
            marker_bits.append("glance presence missing")
    else:
        marker_bits.append("glance payload is not an object")
    today_items = None
    if isinstance(tpayload, dict) and isinstance(tpayload.get("bands"), list):
        today_items = sum(len(b.get("items") or [])
                          for b in tpayload["bands"] if isinstance(b, dict))
        marker_bits.append(f"today bands {len(tpayload['bands'])}, "
                           f"items {today_items}")
    else:
        marker_ok = False
        marker_bits.append("today payload carries no bands list")
    assertions["live_markers"] = {"pass": marker_ok,
                                  "detail": "; ".join(marker_bits)}

    # Cross-check: glance decision_count + today item count vs direct.
    direct_glance = _bracketed("attention", "/api/v1/glance")
    direct_today = _bracketed("attention", "/api/v1/today")
    served_dc = payload.get("decision_count") if isinstance(payload, dict) else None
    dc_ok = any(isinstance(r, dict) and r.get("decision_count") == served_dc
                for r in direct_glance)
    dt_counts = []
    for read in direct_today:
        if isinstance(read, dict) and isinstance(read.get("bands"), list):
            dt_counts.append(sum(len(b.get("items") or [])
                                 for b in read["bands"]
                                 if isinstance(b, dict)))
    items_ok = today_items is not None and today_items in dt_counts
    assertions["cross_check"] = {
        "pass": bool(dc_ok and items_ok),
        "detail": (f"decision_count served {served_dc} "
                   f"({'equals' if dc_ok else 'DIFFERS from'} direct); "
                   f"today items served {today_items} vs direct {dt_counts}")}

    text = "\n".join(served)
    hits = _marker_scan("attention", text)
    assertions["seed_absence"] = {
        "pass": not hits,
        "detail": ("no seed markers in the served payload" if not hits
                   else f"seed markers served: {hits}")}
    verdict = "pass" if all(a["pass"] for a in assertions.values()) else "fail"
    return verdict, assertions, text


LEGS = {
    "workbench": leg_workbench,
    "scheduler": leg_scheduler,
    "runner": leg_runner,
    "attention": leg_attention,
}


def leg_dead_port(channel):
    """Assertion 5: against a staging publish whose runner
    bridge points at a dead port, the artifact must surface
    status 0, a null payload, and the unreachable sentence —
    and no data."""
    state = channel.call("getState", {})
    if not state["ok"]:
        return "fail", {"honest_unreachable": {
            "pass": False,
            "detail": f"getState did not return through the channel: "
                      f"{state['error']}"}}
    reply = _bridge_reply(state["data"])
    if reply is None:
        return "fail", {"honest_unreachable": {
            "pass": False,
            "detail": "action result is not a bridge reply"}}
    status = reply.get("status")
    payload = reply.get("payload")
    error = reply.get("error")
    ok = (status == 0 and payload is None
          and isinstance(error, str) and "unreachable" in error)
    return ("pass" if ok else "fail"), {"honest_unreachable": {
        "pass": ok,
        "detail": f"status {status!r}, payload "
                  f"{'null' if payload is None else 'NON-NULL (fabricated?)'}, "
                  f"error {error!r}"}}


def main(argv=None):
    try:
        parsed = platform_argv.parse(DECLARATION,
                                     sys.argv[1:] if argv is None else argv)
    except platform_argv.UsageError as exc:
        print(f"publish_proof: {exc}", file=sys.stderr)
        print(platform_argv.help_text(DECLARATION), file=sys.stderr, end="")
        return platform_argv.USAGE_EXIT
    if "help" in parsed:
        print(parsed["help"], end="")
        return 0
    _f = parsed["flags"]
    apps = [a.strip() for a in _f["apps"].split(",") if a.strip()]
    if not apps or (_f["channel"] != "static" and any(a not in LEGS for a in apps)):
        # BT10: an empty or unknown --apps refuses, never zero legs and a pass.
        print("publish_proof: --apps names no known app leg", file=sys.stderr)
        return platform_argv.USAGE_EXIT
    # The body's argument attributes are the flag names, dash as underscore.
    args = SimpleNamespace(**{k.replace("-", "_"): v for k, v in _f.items()})

    if args.channel == "http":
        if not args.base_url:
            print("FAIL --channel http needs --base-url")
            return 2
        channel = HttpChannel(args.base_url)
    elif args.channel == "bridge":
        if not args.bridge_dir:
            print("FAIL --channel bridge needs --bridge-dir")
            return 2
        channel = BridgeChannel(args.bridge_dir)
    else:
        if not args.mirror or not os.path.isdir(args.mirror):
            print("FAIL --channel static needs an existing --mirror dir")
            return 2
        channel = StaticChannel(args.mirror)

    report = {
        "artifact_slug": args.slug,
        "artifact_version": args.version,
        "channel": args.channel,
        "proved_at": _iso(_now()),
        "apps": {},
    }
    try:
        if args.leg == "dead-port":
            verdict, assertions = leg_dead_port(channel)
            report["leg"] = "dead-port"
            report["apps"]["runner"] = {
                "verdict": verdict, "assertions": assertions}
            report["verdict"] = verdict
        elif args.channel == "static":
            text = channel.served_text()
            for app in [a.strip() for a in args.apps.split(",") if a.strip()]:
                hits = _marker_scan(app, text)
                if app == "runner" and f'"balance_cu": {RUNNER_SEED_BALANCE_CU}' in text:
                    hits.append(f"seed balance_cu {RUNNER_SEED_BALANCE_CU}")
                assertions = _fail_all(
                    "static artifact: no action channel exists, so no "
                    "bridge liveness can be shown")
                assertions["cross_check"] = {
                    "pass": False,
                    "detail": "static artifact serves no action payload "
                              "to equal a backend read"}
                assertions["seed_absence"] = {
                    "pass": not hits,
                    "detail": ("no seed markers in the served files"
                               if not hits else
                               f"seed markers in the served files: {hits}")}
                report["apps"][app] = {"verdict": "fail",
                                       "assertions": assertions}
            report["verdict"] = "fail"
        else:
            for app in [a.strip() for a in args.apps.split(",") if a.strip()]:
                verdict, assertions, _text = LEGS[app](channel)
                report["apps"][app] = {"verdict": verdict,
                                       "assertions": assertions}
            report["verdict"] = (
                "pass" if all(a["verdict"] == "pass"
                              for a in report["apps"].values()) else "fail")
    except ChannelError as exc:
        print(f"FAIL channel error: {exc}")
        report["verdict"] = "fail"
        report["channel_error"] = str(exc)

    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
    for app, entry in report["apps"].items():
        print(f"{entry['verdict'].upper()} {app}")
        for name, assertion in entry.get("assertions", {}).items():
            print(f"  {'PASS' if assertion['pass'] else 'FAIL'} "
                  f"{name} — {assertion['detail']}")
    print(f"SUMMARY {json.dumps({'verdict': report['verdict'], 'report': args.report}, sort_keys=True)}")
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
