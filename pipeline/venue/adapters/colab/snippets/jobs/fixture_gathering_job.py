"""Run the fixture gathering of a built clone on the leased VM, from a config.

Follows the venue-run harness contract (implemented once in
job_harness.py): progress goes to <out>/heartbeat.log, completion is
<out>/checkpoint.json with completed_units=1 plus a final heartbeat
line containing "complete". The built clone is resolved from
/content/env-registry.json via the harness's resolve_remote_repo.
Inputs: the config JSON is a declared upload of the job's manifest —
the caller stages the copy it edited locally at
var/fixture-gathering/fixture-gathering-config.json and the runner
lands it in the run's own upload directory, which the defaults below
resolve. A hand-driven run may still copy the config flat to
/content (the pre-per-run-uploads slot); the defaults fall back to
that copy when no run copy is present. The filing catalog parts live
at /content/fixture-gathering/catalog: a directory transferred once
per lease through the transfer channel, never a runner upload, so
its address stays flat. The execution plan is generated on the VM
from the config and that catalog — no plan file is uploaded.
Outputs: gathering-plan.json, fixture-candidates-8ka.json, gathering.log.
"""

from __future__ import annotations

import os
import subprocess
import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import job_harness


def _uploads_dir() -> Path:
    """The run's own upload directory (runner per-run uploads):
    shell_job exports it as SHELL_JOB_UPLOADS, and the runner lands
    this script in that same directory, so the script's own
    directory names it on a plain runner launch."""
    env = os.environ.get("SHELL_JOB_UPLOADS")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent


UPLOADS_DIR = _uploads_dir()
FLAT_ROOT = Path("/content")
DEFAULT_CONFIG = UPLOADS_DIR / "fixture-gathering-config.json"
DEFAULT_CATALOG = UPLOADS_DIR / "fixture-gathering" / "catalog"


def main() -> int:
    parser = job_harness.job_parser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--catalog-dir", default=str(DEFAULT_CATALOG))
    parser.add_argument("--repo", default=os.environ.get("VENUE_REPO_ID", os.environ.get("COLAB_REPO_ID")),  # step6-retire: COLAB_ dual-read fallback
                        help="registry repo id (default: $VENUE_REPO_ID, else the sole built clone)")
    args = parser.parse_args()
    record = job_harness.resolve_remote_repo(args.repo)
    REPO = Path("/content") / record["dest"]
    venv_py = Path(record["venv_python"])
    package = record.get("package")
    if not package:
        raise SystemExit("fixture_gathering_job: the built clone's registry record carries no package name (re-run the env build with a registry entry that declares one)")
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    beat = partial(job_harness.beat, out)

    def finish(rc: int) -> int:
        job_harness.write_checkpoint(out, rc)
        beat("gathering complete")
        return 0 if rc == 0 else 1

    config = Path(args.config)
    catalog = Path(args.catalog_dir)
    # Flat-slot fallback: a hand-driven run whose inputs were copied
    # to /content the pre-per-run way still finds them when the
    # resolved run-directory defaults name nothing.
    if config == DEFAULT_CONFIG and not config.is_file():
        flat_config = FLAT_ROOT / "fixture-gathering-config.json"
        if flat_config.is_file():
            config = flat_config
    if catalog == DEFAULT_CATALOG and not catalog.is_dir():
        flat_catalog = FLAT_ROOT / "fixture-gathering" / "catalog"
        if flat_catalog.is_dir():
            catalog = flat_catalog
    beat(f"starting fixture gathering from config {config}")
    if not config.is_file():
        beat(f"config file missing: {config}")
        return finish(2)
    if not catalog.is_dir() or not any(catalog.rglob("*.parquet")):
        beat(f"catalog parts missing under {catalog}")
        return finish(2)
    if not os.environ.get("SEC_USER_AGENT"):
        beat("SEC_USER_AGENT is not set in the job environment")
        return finish(2)
    env = dict(os.environ)
    env["RUNTIME_TEMP_DIRECTORY"] = str(REPO / ".artifacts" / "transient")
    env["PYTHONPATH"] = str(REPO)
    log_path = out / "gathering.log"
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.run(
            [
                str(venv_py),
                "-m",
                f"{package}.tools.fixture_candidates",
                "gather",
                "--config",
                str(config),
                "--work-dir",
                str(out / "work"),
                "--out-dir",
                str(out),
                "--catalog-dir",
                str(catalog),
            ],
            cwd=REPO,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    beat(f"gathering exited rc={proc.returncode}")
    return finish(proc.returncode)


if __name__ == "__main__":
    sys.exit(main())
