"""Registry: strict YAML-subset parsing, entry schema, validation.

Entries are hand-edited for years, so the format is YAML — but the
stdlib has no YAML parser, so this module carries a small strict one
(spec Q1) limited to the schema's flat shapes: nested maps by
two-space indentation, lists of scalars (`- item` lines or a flow
`[a, b]`), and scalar values (bare, single- or double-quoted,
integers, booleans, null). Anything outside the subset is an error,
never a guess.
"""
import os
import re
from zoneinfo import ZoneInfo

KINDS = ("scripted", "agent")
STATUSES = ("active", "suspended")
CADENCE_TYPES = ("interval", "daily", "weekly")
REPORT_WHEN = ("never", "on_failure", "always", "on_output")
LIFETIMES = ("permanent", "until_complete")
DOWS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

TOP_FIELDS = {
    "id", "title", "kind", "status", "suspend_reason", "suspended_on",
    "cadence", "timezone", "owner", "owner_reason", "run", "body",
    "executor", "escalate_body", "timeout_secs", "report", "state_paths",
    "classification", "lifetime", "self_removal",
    "catalog", "source", "config",
}
# An agent job's executor names the surface that claims and
# works its pings — a cron id, a named worker, a seat, a
# thread's registered name. The field is the admission
# contract for the agent kind: the server never runs an
# agent job, it only mints pings, so an agent entry with no
# designated executing surface is a job whose pings no one
# is charged with working (the gap-closure-sweep twin stood
# exactly so, its occurrences coalescing unworked). A value
# that is only a gesture at a surface — a lone generic word
# or a to-be-decided marker — is a placeholder, not a
# designation, and fails the same way an absent field does.
EXECUTOR_PLACEHOLDERS = {
    "tbd", "todo", "none", "unknown", "n/a", "na", "placeholder",
    "example", "agent", "worker", "seat", "cron", "surface",
    "executor", "operator", "main", "keeper",
}
# The entry config block (contract 09, as amended):
# a knob-bearing entry carries its knobs on the entry record
# — the store is the source, edits write back through the one
# writer path, the engine reads the record at fire time. The
# entry form is map-shaped (the YAML subset has no lists of
# maps): knobs and constraints are maps keyed by name, and the
# API projects them to the schema's array form when serving.
# `version` is the store's version stamp: a save presents the
# version it loaded and is refused when the stamp has moved.
CONFIG_FIELDS = {"version", "knobs", "constraints"}
KNOB_FIELDS = {"label", "type", "unit", "value", "min", "max"}
# A knob may also declare `env`: the environment variable the
# engine sets to the knob's value when the entry fires (the
# fire-time seam, contract 09). The mapping is declared here,
# beside the block schema — one optional field per knob, the
# name the fired script actually reads — never a per-job
# table in the engine. The value travels in the knob's own
# unit; the script owns the interpretation of its variable.
KNOB_OPTIONAL_FIELDS = {"env"}
KNOB_TYPES = ("integer", "number")
CONSTRAINT_FIELDS = {"kind", "left", "right", "message"}
# The migration field family (migrated, migrated_at,
# proof_pending, migration_note) does not exist in this
# format (contract 14, amendment 3): an entry stands in the
# registry only by being written through the one writer
# path, so presence is admission and there is no flag for a
# field to carry. An entry carrying one is unknown-field
# invalid, as any other unlisted field is.
CADENCE_FIELDS = {"type", "every", "at", "dow"}
RUN_FIELDS = {"argv", "cwd", "env_names", "shell", "shell_reason"}
REPORT_FIELDS = {"when", "ok_exit_codes", "fail_patterns", "report_patterns", "quiet_patterns"}

# The classified-catalog vocabulary: a catalog
# block classifies an example entry on three axes beyond the
# admission classification; a source block stamps a live entry
# adopted from the catalog with its origin and the parameters
# the adoption used, so drift is a diff (server/entries/catalog.py).
ORIGINS = ("hand", "machine", "per-session")
GENERALITIES = ("generalized", "parameterized", "deployment-specific")
CATALOG_FIELDS = {"origin", "generality", "use_case", "parameters", "setup"}
PARAM_FIELDS = {"field", "required", "default", "description"}
SOURCE_FIELDS = {"catalog", "catalog_version", "parameters"}
# The source block has a second, machine form: where an
# adoption stamp records the catalog an entry was copied
# from, a machine stamp records the writer that rendered the
# entry (the wb-progress family). The two forms never mix on
# one entry. source_class is the scheduler-side backstop for
# the harness's own render refusal: a fixture-classed machine
# entry must never fire, so validation holds it out of the
# live registry entirely (load_dir quarantines the file).
SOURCE_MACHINE_FIELDS = {"writer", "project", "todo", "source_class"}
SOURCE_CLASSES = {"project", "fixture"}
# The setup axis: what an adoption must establish beyond the
# entry itself. state_dirs are created; files are copied from
# a catalog specimen (from_catalog) or verified present;
# stores are verified present or initialized by their declared
# init argv; companions are verified adopted; registrations
# are declared manual steps the adopt verb surfaces; docs are
# Markdown files traveling with the example that describe
# documentation amendments (AGENTS.md edits) the adoption
# requires — the verb records them with the adoption, it
# never performs them.
SETUP_FIELDS = {"state_dirs", "files", "stores", "companions", "registrations", "docs"}
SETUP_FILE_FIELDS = {"target", "from_catalog"}
SETUP_STORE_FIELDS = {"path", "init"}
USE_CASE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
PARAM_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
FIELD_PATH_RE = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)*$")

SECRET_PATTERNS = [
    re.compile(r"(?i)(secret|token|password|passwd|api[_-]?key|credential)\s*[:=]\s*\S+"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b[0-9a-f]{40,}\b"),
    re.compile(r"\b(sk|ghp|gho|xox[bap])-[A-Za-z0-9-]{10,}\b"),
]
ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
EVERY_RE = re.compile(r"^(\d+)([smh])$")
TIME_RE = re.compile(r"^(\d{2}):(\d{2})$")
ANCHOR_RE = re.compile(r"\$\{(REPO|WS|HOME)\}")
ANCHOR_PREFIXES = ("${REPO}/", "${WS}/", "${HOME}/")

# The live overlay: bodies/ holds the live agent bodies —
# per-deployment working state, gitignored by design, so a
# clean checkout carries no bodies/ directory at all. A body
# reference into an absent overlay is a named state
# (overlay-absent, recorded on the Entry and reported by the
# validate/census verbs), not a broken entry; a body missing
# from a present overlay is a defect and fails validation.
# The server's own load passes require_bodies=True and never
# takes the overlay-absent pass: there, a missing body is a
# real defect however the overlay stands.
OVERLAY_DIR = "bodies"

# The jobs overlay: a sibling jobs-overlay/ directory beside
# the tracked jobs/ set, untracked by design, carries the
# deployment's instance jobs — entries serving another
# programme or this deployment instance (the fresh-instance
# test) — while the tracked set carries the system jobs a
# fresh instance validates alone. A checkout without the
# overlay loads the tracked set alone.
JOBS_OVERLAY_DIR = "jobs-overlay"


def derive_anchors(home, workspace_root=None):
    """Path anchors (portability rule: tracked files never carry
    absolute or outside-repo paths). Entries write ${REPO} (this
    repo), ${WS} (the workspace root) and ${HOME} (the directory
    above the workspace root); the server expands them at load,
    so an entry means the same thing wherever the repo is cloned.
    """
    workspace_root = workspace_root or os.path.dirname(home)
    return {
        "REPO": home,
        "WS": workspace_root,
        "HOME": os.path.dirname(workspace_root),
    }


def expand_anchors(value, anchors):
    if not isinstance(value, str):
        return value
    return ANCHOR_RE.sub(lambda m: anchors[m.group(1)], value)


def _check_portable_path(value, where, trail):
    """A raw entry path is portable iff it is a bare name (a
    command resolved via PATH, containing no slash) or begins
    with one of the anchor prefixes. Anything else — an absolute
    path, a home-anchored path, a relative path escaping through
    a bare slash — is rejected at load."""
    if not isinstance(value, str) or "/" not in value:
        return
    if value.startswith(ANCHOR_PREFIXES):
        return
    raise EntryError(
        f"{where}: {trail} {value!r} is not portable: use a bare "
        "command name or an anchored path (${REPO}/, ${WS}/, ${HOME}/)"
    )


class EntryError(Exception):
    """One entry file is invalid; carries the file name."""


# ---------------------------------------------------------------- parser

class _Line:
    __slots__ = ("indent", "text", "no")

    def __init__(self, indent, text, no):
        self.indent, self.text, self.no = indent, text, no


def _strip_comment(text):
    out, quote = [], None
    for i, ch in enumerate(text):
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif ch == "#" and (i == 0 or text[i - 1] in " \t"):
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def _scalar(text, where):
    text = text.strip()
    if text == "" or text in ("null", "~"):
        return None
    if text.startswith("["):
        if not text.endswith("]"):
            raise EntryError(f"{where}: malformed flow list")
        inner = text[1:-1].strip()
        if inner == "":
            return []
        return [_scalar(part, where) for part in inner.split(",")]
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1].replace("''", "'")
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        body = text[1:-1]
        return body.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
    if text in ("true", "false"):
        return text == "true"
    try:
        return int(text)
    except ValueError:
        return text


def _parse_block(lines, pos, indent, where):
    """Parse one block starting at lines[pos] with the given indent.
    Returns (value, next_pos)."""
    if pos >= len(lines):
        return None, pos
    first = lines[pos]
    if first.indent != indent:
        raise EntryError(f"{where}: line {first.no}: unexpected indentation")
    if first.text.startswith("- ") or first.text == "-":
        items = []
        while pos < len(lines) and lines[pos].indent == indent and (
            lines[pos].text.startswith("- ") or lines[pos].text == "-"
        ):
            line = lines[pos]
            rest = line.text[1:].strip()
            if rest == "":
                raise EntryError(f"{where}: line {line.no}: empty list item (scalar lists only)")
            if ":" in rest and not rest.startswith(("'", '"', "[")):
                raise EntryError(f"{where}: line {line.no}: lists of maps are outside the subset")
            items.append(_scalar(rest, where))
            pos += 1
            if pos < len(lines) and lines[pos].indent > indent:
                raise EntryError(f"{where}: line {lines[pos].no}: nested block under a scalar list item")
        return items, pos
    mapping = {}
    while pos < len(lines) and lines[pos].indent == indent and not lines[pos].text.startswith("- "):
        line = lines[pos]
        if ":" not in line.text:
            raise EntryError(f"{where}: line {line.no}: expected 'key: value'")
        key, _, rest = line.text.partition(":")
        key = key.strip()
        if not key or key in mapping:
            raise EntryError(f"{where}: line {line.no}: bad or duplicate key {key!r}")
        rest = rest.strip()
        pos += 1
        if rest:
            mapping[key] = _scalar(rest, where)
        elif pos < len(lines) and lines[pos].indent > indent:
            mapping[key], pos = _parse_block(lines, pos, lines[pos].indent, where)
        else:
            mapping[key] = None
    return mapping, pos


def parse_yaml(text, where="<entry>"):
    lines = []
    for no, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise EntryError(f"{where}: line {no}: tabs are not indentation")
        stripped = _strip_comment(raw)
        if stripped.strip() == "":
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        if indent % 2:
            raise EntryError(f"{where}: line {no}: indentation must be two-space steps")
        lines.append(_Line(indent, stripped.strip(), no))
    if not lines:
        raise EntryError(f"{where}: empty entry")
    value, pos = _parse_block(lines, 0, lines[0].indent, where)
    if pos != len(lines):
        raise EntryError(f"{where}: line {lines[pos].no}: trailing content outside the document")
    if not isinstance(value, dict):
        raise EntryError(f"{where}: an entry is one map, not a list or scalar")
    return value


# ---------------------------------------------------------------- entry

class Entry:
    def __init__(self, job_id, data, path):
        self.id = job_id
        self.data = data
        self.path = path
        # (field, rel) body references into an absent live
        # overlay — the named overlay-absent state validate()
        # records instead of failing a clean checkout. Empty
        # whenever every referenced body file is present.
        self.overlay_absent_bodies = []

    def get(self, key, default=None):
        return self.data.get(key, default)

    @property
    def kind(self):
        return self.data["kind"]

    @property
    def executor(self):
        return self.data.get("executor")

    @property
    def status(self):
        return self.data.get("status", "active")

    @property
    def cadence(self):
        return self.data["cadence"]

    @property
    def timeout_secs(self):
        return self.data["timeout_secs"]

    @property
    def report(self):
        rep = dict(self.data.get("report") or {})
        rep.setdefault("when", "on_failure")
        rep.setdefault("ok_exit_codes", [0])
        rep.setdefault("fail_patterns", [])
        rep.setdefault("report_patterns", [])
        rep.setdefault("quiet_patterns", [])
        return rep

    def timezone_name(self, default_tz):
        return self.data.get("timezone") or default_tz


def expected_wake_per_day(entry):
    """Expected main-thread wake-ups per day from this entry in
    steady state: agent jobs ping every due; report-always
    scripted jobs report every run; on_output jobs report only
    when there is something to say (~0 when quiet); the rest ~0.
    The one implementation — bin/sched census and the read API
    both use it."""
    from .firing import schedule as schedule_mod
    rep = entry.report
    fires = entry.kind == "agent" or rep["when"] == "always"
    if not fires:
        return 0.0
    cad = entry.cadence
    if cad["type"] == "interval":
        step = schedule_mod.parse_every(cad["every"])
        return 86400 / step.total_seconds()
    if cad["type"] == "daily":
        return 1.0
    return len(cad["dow"]) / 7.0


def config_number(value, knob_type):
    """A config block's numeric field as a number, or None when
    the value is not numeric for the knob's type. Integers must
    be integral; numbers accept an int, a float, or a float-
    parseable string (the YAML subset parses `4.5` as a string,
    so a number knob's value may arrive in that form)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if knob_type == "integer" and value.is_integer() \
            else (None if knob_type == "integer" else value)
    if isinstance(value, str) and knob_type == "number":
        try:
            return float(value)
        except ValueError:
            return None
    return None


def config_env(entry):
    """The fire-time environment a config block declares: for
    every knob carrying an `env` name, that variable set to
    the knob's current value (in the knob's own unit, rendered
    as the script reads it — whole numbers without a fraction).
    An entry with no block, or no knob declaring `env`, maps
    to {} — it fires with exactly the environment it fires
    with today. The executor applies this over the inherited
    environment, so a saved knob governs its variable even
    when the server's own environment also carries it."""
    block = entry.get("config")
    if not isinstance(block, dict):
        return {}
    env = {}
    for knob in (block.get("knobs") or {}).values():
        if not isinstance(knob, dict):
            continue
        name = knob.get("env")
        if not name:
            continue
        num = config_number(knob.get("value"), knob.get("type"))
        if num is None:
            continue
        env[name] = str(int(num)) if isinstance(num, float) \
            and num.is_integer() else str(num)
    return env


def _validate_config(data, where):
    cfg = data.get("config")
    if cfg is None:
        return
    if not isinstance(cfg, dict) or set(cfg) - CONFIG_FIELDS:
        raise EntryError(f"{where}: config has unknown or missing fields")
    version = cfg.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise EntryError(f"{where}: config.version is the store's version "
                         "stamp: a positive integer")
    knobs = cfg.get("knobs")
    if not isinstance(knobs, dict) or not knobs:
        raise EntryError(f"{where}: config.knobs is a non-empty map keyed "
                         "by knob name")
    values = {}
    for key, knob in knobs.items():
        if not PARAM_NAME_RE.match(str(key)):
            raise EntryError(f"{where}: bad config knob name {key!r}")
        if not isinstance(knob, dict) \
                or not KNOB_FIELDS <= set(knob) \
                or set(knob) - KNOB_FIELDS - KNOB_OPTIONAL_FIELDS:
            raise EntryError(f"{where}: config knob {key} has unknown or "
                             "missing fields")
        if "env" in knob and not ENV_NAME_RE.match(str(knob["env"])):
            raise EntryError(f"{where}: config knob {key} env holds an "
                             f"environment variable name only, got "
                             f"{knob['env']!r}")
        if not isinstance(knob["label"], str) or not knob["label"]:
            raise EntryError(f"{where}: config knob {key} needs a label")
        if knob["type"] not in KNOB_TYPES:
            raise EntryError(f"{where}: config knob {key} type must be one "
                             f"of {KNOB_TYPES}")
        if not isinstance(knob["unit"], str) or not knob["unit"]:
            raise EntryError(f"{where}: config knob {key} needs a unit")
        nums = {}
        for field in ("value", "min", "max"):
            num = config_number(knob[field], knob["type"])
            if num is None:
                raise EntryError(
                    f"{where}: config knob {key} {field} must be "
                    f"{'a whole number' if knob['type'] == 'integer' else 'a number'}")
            nums[field] = num
        if nums["min"] > nums["max"] or not nums["min"] <= nums["value"] <= nums["max"]:
            raise EntryError(f"{where}: config knob {key} value must sit "
                             "inside its min..max range")
        values[key] = nums["value"]
    constraints = cfg.get("constraints") or {}
    if not isinstance(constraints, dict):
        raise EntryError(f"{where}: config.constraints is a map keyed by name")
    for name, con in constraints.items():
        if not isinstance(con, dict) or set(con) != CONSTRAINT_FIELDS:
            raise EntryError(f"{where}: config constraint {name} has unknown "
                             "or missing fields")
        if con["kind"] != "lt":
            raise EntryError(f"{where}: config constraint {name} kind is lt")
        for side in ("left", "right"):
            if con[side] not in values:
                raise EntryError(f"{where}: config constraint {name} names "
                                 f"unknown knob {con[side]!r}")
        if not isinstance(con["message"], str) or not con["message"]:
            raise EntryError(f"{where}: config constraint {name} needs a message")
        if not values[con["left"]] < values[con["right"]]:
            raise EntryError(f"{where}: config constraint {name} is violated "
                             "by the block's own values")


def _check_secrets(value, where, trail=""):
    if isinstance(value, str):
        for pat in SECRET_PATTERNS:
            if pat.search(value):
                raise EntryError(f"{where}: secret-shaped value at {trail or '<root>'}")
    elif isinstance(value, dict):
        for key, sub in value.items():
            _check_secrets(sub, where, f"{trail}.{key}" if trail else key)
    elif isinstance(value, list):
        for i, sub in enumerate(value):
            _check_secrets(sub, where, f"{trail}[{i}]")


def _overlay_absent(home, rel):
    """True when a body reference points into the live overlay
    (bodies/) and this checkout carries no overlay directory
    at all — the clean-clone shape, where the reference is the
    named overlay-absent state rather than a missing file. A
    reference anywhere else, or any reference while the
    overlay directory stands, is checked strictly."""
    if rel.split("/")[0] != OVERLAY_DIR:
        return False
    return not os.path.isdir(os.path.join(home, OVERLAY_DIR))


def validate(job_id, data, home, where=None, anchors=None, require_bodies=False):
    """Validate one parsed entry; raises EntryError. `home` is the
    repo root, used to resolve body paths. Anchor tokens in
    run.argv and state_paths are checked for portability and then
    expanded in place, so consumers always see real paths.

    Body existence has two contexts. In the live registry a
    missing body is a defect and raises; require_bodies=True
    (the server's load) keeps that unconditional. Otherwise a
    reference into an absent live overlay (a clean checkout,
    where bodies/ is gitignored working state) is recorded on
    the returned Entry as overlay_absent_bodies — a named,
    countable state the report verbs surface — instead of
    failing a checkout that carries no overlay by design."""
    where = where or f"{job_id}.yaml"
    if not isinstance(data, dict):
        raise EntryError(f"{where}: entry is not a map")
    unknown = sorted(set(data) - TOP_FIELDS)
    if unknown:
        raise EntryError(f"{where}: unknown fields: {', '.join(unknown)}")
    if data.get("id") != job_id:
        raise EntryError(f"{where}: id field {data.get('id')!r} does not match the file name")
    for field in ("title", "kind", "cadence", "owner", "timeout_secs", "classification"):
        if data.get(field) in (None, ""):
            raise EntryError(f"{where}: missing required field {field}")
    if data["kind"] not in KINDS:
        raise EntryError(f"{where}: kind must be one of {KINDS}")
    if data.get("status", "active") not in STATUSES:
        raise EntryError(f"{where}: status must be one of {STATUSES}")
    if data.get("status") == "suspended" and not (data.get("suspend_reason") and data.get("suspended_on")):
        raise EntryError(f"{where}: a suspension carries suspend_reason and suspended_on")
    if not isinstance(data["timeout_secs"], int) or data["timeout_secs"] <= 0:
        raise EntryError(f"{where}: timeout_secs is required and must be a positive integer")
    owner = data["owner"]
    if owner != "none" and not (isinstance(owner, str) and owner.startswith("goal:") and len(owner) > 5):
        raise EntryError(f"{where}: owner must be goal:<slug> or none")
    if owner == "none" and not data.get("owner_reason"):
        raise EntryError(f"{where}: owner none requires owner_reason")
    tz = data.get("timezone")
    if tz is not None:
        try:
            ZoneInfo(tz)
        except Exception as exc:
            raise EntryError(f"{where}: unknown timezone {tz!r}") from exc
    cad = data["cadence"]
    if not isinstance(cad, dict) or set(cad) - CADENCE_FIELDS:
        raise EntryError(f"{where}: cadence has unknown or missing fields")
    ctype = cad.get("type")
    if ctype not in CADENCE_TYPES:
        raise EntryError(f"{where}: cadence.type must be one of {CADENCE_TYPES}")
    if ctype == "interval":
        if set(cad) != {"type", "every"} or not EVERY_RE.match(str(cad.get("every", ""))):
            raise EntryError(f"{where}: interval cadence is exactly {{type, every: <Nm|Nh>}}")
    elif ctype == "daily":
        if set(cad) != {"type", "at"} or not TIME_RE.match(str(cad.get("at", ""))):
            raise EntryError(f"{where}: daily cadence is exactly {{type, at: HH:MM}}")
    else:
        dows = cad.get("dow")
        if set(cad) != {"type", "dow", "at"} or not TIME_RE.match(str(cad.get("at", ""))) \
                or not isinstance(dows, list) or not dows or any(d not in DOWS for d in dows):
            raise EntryError(f"{where}: weekly cadence is exactly {{type, dow: [Mon..Sun], at: HH:MM}}")
    if data["kind"] == "scripted":
        run = data.get("run")
        if not isinstance(run, dict) or set(run) - RUN_FIELDS:
            raise EntryError(f"{where}: scripted entries need a run map (argv, cwd, env_names, shell, shell_reason)")
        argv = run.get("argv")
        if run.get("shell"):
            if not run.get("shell_reason"):
                raise EntryError(f"{where}: shell: true requires shell_reason")
            if not (isinstance(argv, str) and argv) and not (isinstance(argv, list) and argv):
                raise EntryError(f"{where}: shell run needs an argv command")
        elif not (isinstance(argv, list) and argv and all(isinstance(a, str) and a for a in argv)):
            raise EntryError(f"{where}: run.argv must be a non-empty list of strings (or shell: true with shell_reason)")
        for name in run.get("env_names") or []:
            if not ENV_NAME_RE.match(str(name)):
                raise EntryError(f"{where}: env_names holds variable names only, got {name!r}")
        if data.get("body"):
            raise EntryError(f"{where}: scripted entries use run, not body")
    else:
        body = data.get("body")
        if not body or not isinstance(body, str) or not body.startswith("bodies/"):
            raise EntryError(f"{where}: agent entries need body: bodies/<id>.md")
        if data.get("run"):
            raise EntryError(f"{where}: agent entries use body, not run")
        executor = data.get("executor")
        if not isinstance(executor, str) or not executor.strip():
            raise EntryError(
                f"{where}: agent entries need executor: the registered "
                "name of the surface that claims and works their pings "
                "(a cron id, a named worker, a seat) — the server mints "
                "pings and never works them, so an agent job with no "
                "designated executor does not arm")
        if executor.strip().casefold() in EXECUTOR_PLACEHOLDERS:
            raise EntryError(
                f"{where}: executor {executor!r} is a placeholder, not "
                "an executing surface — name the surface that claims "
                "and works this job's pings")
    absent_bodies = []
    for field in ("body", "escalate_body"):
        rel = data.get(field)
        if rel:
            if not isinstance(rel, str) or rel.startswith("/") or ".." in rel.split("/"):
                raise EntryError(f"{where}: {field} must be a repo-relative path")
            if not os.path.isfile(os.path.join(home, rel)):
                if not require_bodies and _overlay_absent(home, rel):
                    absent_bodies.append((field, rel))
                else:
                    raise EntryError(f"{where}: {field} file does not exist: {rel}")
    rep = data.get("report") or {}
    if not isinstance(rep, dict) or set(rep) - REPORT_FIELDS:
        raise EntryError(f"{where}: report has unknown fields")
    if rep.get("when", "on_failure") not in REPORT_WHEN:
        raise EntryError(f"{where}: report.when must be one of {REPORT_WHEN}")
    if not all(isinstance(c, int) for c in rep.get("ok_exit_codes", [0])):
        raise EntryError(f"{where}: report.ok_exit_codes is a list of integers")
    if data.get("lifetime", "permanent") not in LIFETIMES:
        raise EntryError(f"{where}: lifetime must be one of {LIFETIMES}")
    cat = data.get("catalog")
    if cat is not None:
        if not isinstance(cat, dict) or set(cat) - CATALOG_FIELDS:
            raise EntryError(f"{where}: catalog has unknown fields")
        if cat.get("origin") not in ORIGINS:
            raise EntryError(f"{where}: catalog.origin must be one of {ORIGINS}")
        if cat.get("generality") not in GENERALITIES:
            raise EntryError(f"{where}: catalog.generality must be one of {GENERALITIES}")
        if not USE_CASE_RE.match(str(cat.get("use_case", ""))):
            raise EntryError(f"{where}: catalog.use_case is a lowercase hyphenated label")
        params = cat.get("parameters") or {}
        if not isinstance(params, dict):
            raise EntryError(f"{where}: catalog.parameters is a map keyed by name")
        for name, spec in params.items():
            if not PARAM_NAME_RE.match(str(name)):
                raise EntryError(f"{where}: bad parameter name {name!r}")
            if not isinstance(spec, dict) or set(spec) - PARAM_FIELDS:
                raise EntryError(f"{where}: parameter {name} has unknown fields")
            if not FIELD_PATH_RE.match(str(spec.get("field", ""))):
                raise EntryError(f"{where}: parameter {name} needs a dotted field path")
            if ("default" in spec) == (spec.get("required") is True):
                raise EntryError(
                    f"{where}: parameter {name} declares exactly one of default / required: true")
        setup = cat.get("setup") or {}
        if not isinstance(setup, dict) or set(setup) - SETUP_FIELDS:
            raise EntryError(f"{where}: catalog.setup has unknown fields")
        for kind in ("state_dirs", "companions", "registrations", "docs"):
            value = setup.get(kind) or []
            if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
                raise EntryError(f"{where}: catalog.setup.{kind} is a list of strings")
        for doc_name in setup.get("docs") or []:
            if not doc_name.endswith(".md") or "/" in doc_name:
                raise EntryError(
                    f"{where}: catalog.setup.docs names Markdown files in the layer")
        files = setup.get("files") or {}
        if not isinstance(files, dict):
            raise EntryError(f"{where}: catalog.setup.files is a map keyed by name")
        for name, spec in files.items():
            if not isinstance(spec, dict) or set(spec) - SETUP_FILE_FIELDS \
                    or not isinstance(spec.get("target"), str) or not spec.get("target"):
                raise EntryError(f"{where}: setup file {name} needs a target path")
        stores = setup.get("stores") or {}
        if not isinstance(stores, dict):
            raise EntryError(f"{where}: catalog.setup.stores is a map keyed by name")
        for name, spec in stores.items():
            if not isinstance(spec, dict) or set(spec) - SETUP_STORE_FIELDS \
                    or not isinstance(spec.get("path"), str) or not spec.get("path"):
                raise EntryError(f"{where}: setup store {name} needs a path")
            init = spec.get("init")
            if init is not None and not (
                    isinstance(init, list) and init
                    and all(isinstance(a, str) and a for a in init)):
                raise EntryError(f"{where}: setup store {name} init is an argv list")
    src = data.get("source")
    if src is not None:
        if not isinstance(src, dict):
            raise EntryError(f"{where}: source is a map")
        if "catalog" in src:
            if set(src) - SOURCE_FIELDS:
                raise EntryError(f"{where}: source has unknown fields")
            if not isinstance(src.get("catalog"), str) or not src.get("catalog"):
                raise EntryError(f"{where}: source.catalog names the catalog entry")
            if not isinstance(src.get("catalog_version"), int) or src.get("catalog_version", 0) <= 0:
                raise EntryError(f"{where}: source.catalog_version is a positive integer")
            sparams = src.get("parameters") or {}
            if not isinstance(sparams, dict) or any(
                    isinstance(v, (dict, list)) for v in sparams.values()):
                raise EntryError(f"{where}: source.parameters is a flat map of scalars")
        elif set(src) <= SOURCE_MACHINE_FIELDS:
            for field in ("writer", "project", "todo"):
                if not isinstance(src.get(field), str) or not src.get(field):
                    raise EntryError(f"{where}: source.{field} names the {field}")
            if src.get("source_class") not in SOURCE_CLASSES:
                raise EntryError(
                    f"{where}: source.source_class is one of {sorted(SOURCE_CLASSES)}")
            cat = data.get("catalog")
            if not isinstance(cat, dict) or cat.get("origin") != "machine":
                raise EntryError(
                    f"{where}: a machine source stamp requires catalog origin: machine")
            if src["source_class"] == "fixture":
                raise EntryError(
                    f"{where}: machine entry declares fixture source class — "
                    "held out of the live registry, must not fire")
        else:
            raise EntryError(f"{where}: source matches neither the adoption "
                             "form nor the machine form")
    _validate_config(data, where)
    if not isinstance(data.get("state_paths", []), list):
        raise EntryError(f"{where}: state_paths is a list of paths")
    anchors = anchors or derive_anchors(home)
    run = data.get("run") or {}
    argv = run.get("argv")
    if isinstance(argv, list):
        for i, item in enumerate(argv):
            _check_portable_path(item, where, f"run.argv[{i}]")
        run["argv"] = [expand_anchors(item, anchors) for item in argv]
    cwd = run.get("cwd")
    if isinstance(cwd, str):
        _check_portable_path(cwd, where, "run.cwd")
        run["cwd"] = expand_anchors(cwd, anchors)
    for i, item in enumerate(data.get("state_paths", [])):
        _check_portable_path(item, where, f"state_paths[{i}]")
    if isinstance(data.get("state_paths"), list):
        data["state_paths"] = [expand_anchors(item, anchors) for item in data["state_paths"]]
    _check_secrets(data, where)
    entry = Entry(job_id, data, os.path.join(home, "jobs", f"{job_id}.yaml"))
    entry.overlay_absent_bodies = absent_bodies
    return entry


def load_dir(jobs_dir, home, anchors=None, require_bodies=False):
    """Load every entry. Returns (entries, errors): entries is a dict
    id -> Entry for the files that parsed and validated; errors is a
    list of strings naming the quarantined files (spec EC-9).
    require_bodies is the live-load context (the server): a missing
    body file is an error there, never the overlay-absent state a
    clean checkout reports. The jobs overlay (the sibling
    jobs-overlay/ directory, when present) loads after the tracked
    set, its entries held to the same validation; an id standing
    in both sets is a named error — the overlay never shadows a
    tracked entry."""
    entries, errors = {}, []

    def _load_one(directory, name):
        job_id = name[: -len(".yaml")]
        path = os.path.join(directory, name)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = parse_yaml(fh.read(), where=name)
            entries[job_id] = validate(job_id, data, home, where=name,
                                       anchors=anchors,
                                       require_bodies=require_bodies)
        except (EntryError, OSError) as exc:
            errors.append(str(exc))

    if not os.path.isdir(jobs_dir):
        return entries, [f"registry dir missing: {jobs_dir}"]
    for name in sorted(os.listdir(jobs_dir)):
        if name.endswith(".yaml"):
            _load_one(jobs_dir, name)
    overlay_dir = os.path.join(
        os.path.dirname(os.path.abspath(jobs_dir)), JOBS_OVERLAY_DIR)
    if os.path.isdir(overlay_dir):
        for name in sorted(os.listdir(overlay_dir)):
            if not name.endswith(".yaml"):
                continue
            job_id = name[: -len(".yaml")]
            if job_id in entries:
                errors.append(
                    f"{name}: job id {job_id} stands in both the tracked "
                    "registry and the jobs overlay — the overlay never "
                    "shadows a tracked entry")
                continue
            _load_one(overlay_dir, name)
    return entries, errors
