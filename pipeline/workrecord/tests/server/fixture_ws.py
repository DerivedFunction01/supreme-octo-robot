"""One fixture workspace for the server-half tests and
proofs (S8): two manifest projects and one plain repo,
built entirely through the pipeline's own writers (the
registry, the bundle writer, the dispatch message
store) so both the pinned server and this package read
the same stores the same way.

Layout under the given base:

    ws/alpha/       git repo + manifest project: registry
                    entries (one verified mockup, one
                    reviewed needs-changes), a plan bundle
                    with steps and todos (open, blocked,
                    an armed doing todo with checkpoints),
                    a finished bundle with done todos
    ws/beta/        manifest only — no registry, no plans
    ws/delta-repo/  a plain git repo (no manifest): a
                    committed CSV dataset, a committed
                    text file since modified, an
                    untracked file
    state/          the message store, seeded through
                    dispatch.messages (a sent text
                    annotation on alpha's plan, a draft,
                    a done message, a plain owner note)
    armed/, jobs/   the doing todo's two projections,
                    landed by the harness's own writers
                    through the contract 03 env seams

Git commits use fixed author/committer dates so commit
hashes are stable across builds.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# The pipeline path seam (the message store lives in the
# dispatch substrate): tests/server -> workrecord root ->
# pipeline root.
_PIPELINE_ROOT = Path(__file__).resolve().parents[3]
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

from lib.writes import bundles as bundle_mod
from lib import registry as reg

GIT_ENV = {
    "GIT_AUTHOR_DATE": "2026-10-25T12:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-10-25T12:00:00+00:00",
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
}

MOCK = ('<style>:root{--ink:#111}</style>'
        '<h1 style="color:var(--ink)">A</h1>\n')

PLAN_TEXT = """# Fixture plan for the feeds

Status: in progress
Executor: fixture-lane

## Objective

Exercise every feed the workbench app consumes, from
stores both servers read identically.

## Steps

### Step 1 — Build the fixture stores

The registry, the bundles, and the message store are
seeded through their own writers.

files: tests/server/fixture_ws.py
verify: .venv/bin/python -m unittest tests.server
done when: both servers serve identical payloads

### Step 2 — Diff the payloads

Route by route, the pipeline's payloads are diffed
against the pinned server's over these same stores.

files: server/assemble.py
verify: the S8 diff proof
done when: the diff is empty or every delta is named
"""

DOING_BODY = (
    "progress-checkpoint: 2026-10-25T11:30:00+00:00"
    " — fixture checkpoint one\n"
    "progress-checkpoint: 2026-10-25T11:45:00+00:00"
    " — fixture checkpoint two\n"
    "\nNotes ride under the checkpoints.\n")


def _git(root: Path, *args: str) -> None:
    env = {**os.environ, **GIT_ENV}
    subprocess.run(["git", "-C", str(root), *args],
                   check=True, env=env,
                   capture_output=True, text=True)


def _commit_all(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def _manifest(root: Path, name: str) -> None:
    (root / "workbench.yaml").write_text(
        f"name: {name}\n"
        "registry: workbench/registry.db\n"
        "plans: .plans\n"
        "mockups: workbench/entries\n"
        "archive: workbench/archive\n"
        "catalog_origin: machine\n"
        "catalog_generality: deployment-specific\n"
        "catalog_use_case: work-tracking\n",
        encoding="utf-8")


def build_fixture_workspace(base: Path) -> dict:
    base = Path(base)
    ws = base / "ws"
    state = base / "state"
    armed_dir = base / "armed"
    jobs_dir = base / "jobs"
    for d in (ws, state, armed_dir, jobs_dir):
        d.mkdir(parents=True, exist_ok=True)
    # The harness writers land their projections through
    # the contract 03 sibling seams; point both at the
    # fixture so nothing touches the pipeline's live
    # registry or armed directory.
    saved_env = {k: os.environ.get(k) for k in
                 ("WB_ATTENTION_ARMED_DIR",
                  "WB_SCHEDULER_JOBS_DIR")}
    os.environ["WB_ATTENTION_ARMED_DIR"] = str(armed_dir)
    os.environ["WB_SCHEDULER_JOBS_DIR"] = str(jobs_dir)
    try:
        return _build(base, ws, state, armed_dir, jobs_dir)
    finally:
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _build(base: Path, ws: Path, state: Path,
           armed_dir: Path, jobs_dir: Path) -> dict:

    # ------------------------------------------------ alpha
    alpha = ws / "alpha"
    (alpha / "workbench").mkdir(parents=True)
    (alpha / ".plans").mkdir()
    _manifest(alpha, "Alpha")
    db = alpha / "workbench" / "registry.db"
    reg.init_registry(db)
    layout = (alpha / "workbench" / "entries",
              alpha / "workbench" / "archive")
    entry = reg.add_entry(db, layout, "tile-a",
                          title="Tile A")
    (Path(entry["entry_dir"]) / "mock.html").write_text(
        MOCK, encoding="utf-8")
    reg.verify_entry(db, "tile-a", accept_drift=True)
    entry_b = reg.add_entry(db, layout, "tile-b",
                            title="Tile B")
    (Path(entry_b["entry_dir"]) / "mock.html").write_text(
        MOCK, encoding="utf-8")
    reg.verify_entry(db, "tile-b", accept_drift=True)
    reg.review_entry(db, "tile-b", "needs-changes",
                     actor="owner", comment="Fixture note")
    reg.add_entry(db, layout, "spec-doc", title="Spec Doc",
                  kind="storyboard")
    reg.set_status(db, "spec-doc", "canonical",
                   actor="owner",
                   ruling="Fixture ruling (S8)")

    plans = alpha / ".plans"
    bundle_mod.create_bundle(plans, "fixture-work",
                             today="2026-10-25")
    plan_path = plans / "2026-10-25-fixture-work" / "plan.md"
    plan_path.write_text(PLAN_TEXT, encoding="utf-8")
    stamp = {"created": "2026-10-25", "updated": "2026-10-25"}
    t_open = bundle_mod.create_todo(
        plans, "fixture-work", "Open thing", **stamp)
    # The doing todo: cadence + arming stamp + checkpoints
    # in the body. The writer syncs both projections in
    # the same call — the armed row lands in the fixture's
    # armed dir through the env seam set by the caller.
    t_doing = bundle_mod.create_todo(
        plans, "fixture-work", "Doing thing",
        status="doing", progress="30m",
        armed_at="2026-10-25T11:00:00+00:00",
        body=DOING_BODY, **stamp)
    bundle_mod.create_todo(
        plans, "fixture-work", "Blocked thing",
        status="blocked", **stamp)
    done_bundle = bundle_mod.create_bundle(
        plans, "old-work", today="2026-10-20")
    for i in range(3):
        bundle_mod.create_todo(
            plans, "old-work", f"Done thing {i}",
            status="done", body="history", **stamp)
    # Archive the done bundle: finished/ is the archive.
    finished = plans / "finished"
    finished.mkdir(exist_ok=True)
    Path(done_bundle["path"]).rename(
        finished / Path(done_bundle["path"]).name)

    _git(alpha, "init", "-q", "-b", "main")
    _commit_all(alpha, "alpha fixture root")
    # A working-tree change for the diff feed.
    (alpha / "workbench.yaml").write_text(
        (alpha / "workbench.yaml").read_text(
            encoding="utf-8") + "# fixture drift\n",
        encoding="utf-8")

    # ------------------------------------------------- beta
    beta = ws / "beta"
    beta.mkdir()
    _manifest(beta, "Beta")

    # -------------------------------------------- delta-repo
    delta = ws / "delta-repo"
    (delta / "data").mkdir(parents=True)
    (delta / "README.md").write_text(
        "# Delta fixture repo\n\nA plain repo the census "
        "finds.\n", encoding="utf-8")
    (delta / "data" / "filings.csv").write_text(
        "form,cik,filed\n10-K,12345,2026-10-01\n"
        "10-Q,12345,2026-10-02\n", encoding="utf-8")
    _git(delta, "init", "-q", "-b", "main")
    _commit_all(delta, "delta fixture root")
    (delta / "README.md").write_text(
        "# Delta fixture repo\n\nA plain repo the census "
        "finds.\n\nModified after the commit.\n",
        encoding="utf-8")
    (delta / "notes.txt").write_text(
        "untracked fixture notes\n", encoding="utf-8")

    # ---------------------------------------------- messages
    from dispatch import messages as msg_mod
    msg_db = state / "messages.db"
    annotation = msg_mod.create_message(
        msg_db, author="Muse",
        body="The step heading moved — re-check the "
             "anchor.",
        project_slug="alpha", anchor_type="text",
        anchor_ref="2026-10-25-fixture-work/plan.md",
        selection={
            "kind": "text", "component_id": "step-1",
            "quote": "### Step 1 — Build the fixture "
                     "stores",
            "prefix": "", "suffix": ""},
        send=True)
    msg_mod.create_message(
        msg_db, author="owner", body="Draft thought.",
        project_slug="alpha", anchor_type="none",
        send=False)
    done = msg_mod.create_message(
        msg_db, author="Muse", body="Handled already.",
        project_slug="alpha", anchor_type="none",
        send=True)
    # The lifecycle is draft -> sent -> acknowledged ->
    # done: the pickup fetch is what acknowledges.
    msg_mod.fetch_unacked(msg_db, "alpha")
    msg_mod.mark_done(msg_db, done["id"])
    msg_mod.create_message(
        msg_db, author="owner", body="Plain owner note.",
        project_slug=None, anchor_type="none", send=True)

    return {
        "base": base, "ws": ws, "state": state,
        "armed_dir": armed_dir, "jobs_dir": jobs_dir,
        "alpha": alpha,
        "beta": beta, "delta": delta,
        "messages_db": msg_db,
        "doing_todo": t_doing["id"],
        "open_todo": t_open["id"],
        "annotation_id": annotation["id"],
        "plan_ref": "2026-10-25-fixture-work/plan.md",
    }


def fixture_config(base: Path, state_dir: Path) -> Path:
    """The viewer config both servers load for the
    fixture: the workspace and roots pinned, the state
    dir per-side (the repos feed keeps its registry +
    history in state, and the message store lives there
    too — each side gets its own copy of both)."""
    import shutil
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    seeded = Path(base) / "state" / "messages.db"
    if seeded.is_file():
        shutil.copyfile(seeded, state_dir / "messages.db")
    cfg = {
        "workspace_root": str(base / "ws"),
        "sweep_roots": [str(base / "ws")],
        "state_dir": str(state_dir),
        "file_editing_enabled": True,
        "sweep_ttl_s": 1,
    }
    path = state_dir / "config.json"
    path.write_text(json.dumps(cfg, indent=2),
                    encoding="utf-8")
    return path
