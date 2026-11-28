"""Server configuration: one JSON file, one env override layer.

Precedence (spec Step 1): SCHEDULER_* env > config.json > built-in
default. `resolve()` returns (values, sources) so /health can report
the resolved value of every key and which layer set it.
"""
import json
import os

from . import paths as _paths


def _root_list(value):
    """Coerce an extra-write-roots value: a list of paths, or
    one os.pathsep-joined string (the env layer's form). Each
    entry is ~-expanded; the resolved roots themselves are
    realpath'd by the writer at resolve time."""
    if isinstance(value, str):
        parts = [p for p in value.split(os.pathsep) if p]
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        raise ValueError("expected a list of paths or a pathsep-joined string")
    if not all(isinstance(p, str) and p for p in parts):
        raise ValueError("extra write roots must be non-empty path strings")
    return [os.path.expanduser(p) for p in parts]


# key -> (default, env var, coercion)
KEYS = {
    "host": ("127.0.0.1", "SCHEDULER_HOST", str),
    "port": (8796, "SCHEDULER_PORT", int),
    "home": (None, "SCHEDULER_HOME", str),
    "workspace_root": (None, "SCHEDULER_WORKSPACE_ROOT", str),
    # Extra roots the /ops writer may write under, beside the
    # workspace root (contract 15's server-configured
    # allowance). The default — derived in resolve() when no
    # layer sets the key — is exactly the venue funnel's
    # credential directory under the server's home; a caller
    # can never name a root in a request.
    "ops_extra_write_roots": (None, "SCHEDULER_OPS_EXTRA_WRITE_ROOTS", _root_list),
    "tick_secs": (20, "SCHEDULER_TICK_SECS", int),
    "default_timezone": ("UTC", "SCHEDULER_DEFAULT_TIMEZONE", str),
    "outbox_ack_timeout_secs": (3600, "SCHEDULER_OUTBOX_ACK_TIMEOUT_SECS", int),
    "ledger_retention_days": (90, "SCHEDULER_LEDGER_RETENTION_DAYS", int),
    "capture_cap_bytes": (65536, "SCHEDULER_CAPTURE_CAP_BYTES", int),
    "git_ssh_identity_file": (None, "SCHEDULER_GIT_SSH_IDENTITY_FILE", str),
    "git_ssh_known_hosts_file": (None, "SCHEDULER_GIT_SSH_KNOWN_HOSTS_FILE", str),
    "workbench_base_url": ("http://127.0.0.1:8792", "SCHEDULER_WORKBENCH_BASE_URL", str),
    # Stack-dump watchdog (stackdump-contract: v1 — the starter
    # SPEC's canonical text): the internal health check's cadence
    # and lag threshold, the dump repeat discipline, and the dump
    # file's aggregate size cap. Contract defaults are the shipped
    # values.
    "stackdump_cadence_s": (5.0, "SCHEDULER_STACKDUMP_CADENCE_S", float),
    "stackdump_threshold_s": (15.0, "SCHEDULER_STACKDUMP_THRESHOLD_S", float),
    "stackdump_repeat_s": (60.0, "SCHEDULER_STACKDUMP_REPEAT_S", float),
    "stackdump_max_bytes": (16 * 1024 * 1024, "SCHEDULER_STACKDUMP_MAX_BYTES", int),
    # The connector caller registry (hashes + scopes only) lives
    # in the config file's `connector` object; it is read fresh
    # from the file by server/serving/connector.py on every call, so it
    # has no env layer and its resolved value here is a marker.
    "connector": (None, None, lambda v: v),
}


class ConfigError(Exception):
    pass


def default_config_path():
    return _paths.CONFIG_PATH


def example_config_path():
    return _paths.CONFIG_EXAMPLE_PATH


def require_live_config(path):
    """The live config is the server's home contract (contract
    04): it exists, untracked, provisioned from the shipped
    example, and it carries what the code defaults must never
    invent — the connector caller registry's home and the
    machine-local values. A server that starts without one
    would silently run on built-in defaults with an empty
    token registry, so absence is a startup refusal, never a
    default. Returns the path when present."""
    if not os.path.exists(path):
        raise ConfigError(
            f"live config absent at {path}: provision it from "
            f"{example_config_path()} (untracked; it may carry "
            "machine-local values) — the server never starts on "
            "silent defaults")
    return path


def load_file(path):
    if path is None or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot load config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"config {path} is not a JSON object")
    unknown = sorted(set(data) - set(KEYS))
    if unknown:
        raise ConfigError(f"config {path} has unknown keys: {', '.join(unknown)}")
    return data


def resolve(path=None, env=None):
    """Return (values, sources). `home` defaults to the config file's
    own directory (the repo root), so the server runs identically
    from systemd, a shell, or a test."""
    env = os.environ if env is None else env
    path = default_config_path() if path is None else path
    file_values = load_file(path)
    values, sources = {}, {}
    for key, (default, env_name, coerce) in KEYS.items():
        if env_name is not None and env_name in env and env[env_name] != "":
            try:
                values[key] = coerce(env[env_name])
            except (TypeError, ValueError) as exc:
                raise ConfigError(f"env {env_name}={env[env_name]!r} is not a valid {key}") from exc
            sources[key] = "env"
        elif key in file_values and file_values[key] is not None:
            try:
                values[key] = coerce(file_values[key])
            except (TypeError, ValueError) as exc:
                raise ConfigError(f"config key {key}={file_values[key]!r} has the wrong type") from exc
            sources[key] = "config"
        else:
            values[key] = default
            sources[key] = "default"
    if values["home"] is None:
        values["home"] = os.path.dirname(os.path.abspath(path))
        sources["home"] = "default"
    if values["workspace_root"] is None:
        values["workspace_root"] = os.path.dirname(values["home"])
        sources["workspace_root"] = "default"
    if values["ops_extra_write_roots"] is None:
        # The one standing extra root: the venue funnel's
        # credential directory, resolved from the server's
        # home — never a tracked literal, never a glob.
        values["ops_extra_write_roots"] = [
            os.path.join(os.path.expanduser("~"), ".config", "colab-cli")
        ]
        sources["ops_extra_write_roots"] = "default"
    return values, sources


def anchors(values):
    """Path anchors for registry entries (portability rule: tracked
    files never carry absolute or outside-repo paths; entries write
    ${REPO}, ${WS} and ${HOME} and the server expands them here).
    HOME is the directory above the workspace root."""
    return {
        "REPO": values["home"],
        "WS": values["workspace_root"],
        "HOME": os.path.dirname(values["workspace_root"]),
    }
