"""The settings seam: the ONLY module that reads the environment.

Every machine assumption resolves here, once, into a frozen
Settings object; defaults let a fresh clone run.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Roots resolve in the package's paths module (the tree's
# paths discipline); they are re-exported here because
# the services were written against this seam. The
# redundant alias marks REPO_ROOT as a deliberate
# re-export — services import it from this module.
from attention.paths import ATTENTION_HOME, PIPELINE_ROOT
from attention.paths import REPO_ROOT as REPO_ROOT

# D3 basis: three digest windows a day. A settings value, not
# a spec constant — one source, here.
DEFAULT_WINDOWS = ("07:30", "12:30", "17:30")


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8797
    unit_name: str = "workhorse"
    environment: str = "local"
    data_path: Path | None = None  # the serving seam refuses None (no default store)
    digest_windows: tuple[str, ...] = DEFAULT_WINDOWS
    breakthrough_cap: int = 2  # D4 basis: 2 reminders per item
    focus_scope: str = "away"  # D8 basis: focus counts as away
    wb_url: str = "http://127.0.0.1:8792"  # the workbench surface
    wb_timeout_s: float = 2.5
    wb_collect_timeout_s: float = 30.0  # the slow loop's sweep budget
    stall_after_hours: float = 6.0  # a non-terminal status older than this is a stall
    dispatch_claim_minutes: float = 15.0
    dispatch_consumer: str = "attention-service"
    bridge_url: str = "http://127.0.0.1:8796"  # the harness connector
    bridge_token_path: Path = ATTENTION_HOME / "var" / "connector" / "bridge-token"
    bridge_timeout_s: float = 10.0
    dispatch_pass_cap: int = 10
    dispatch_max_attempts: int = 6
    panel_url: str = "http://127.0.0.1:8793"  # the lease panel surface
    panel_timeout_s: float = 120.0
    capacity_collect_minutes: float = 5.0
    capacity_stale_minutes: float = 15.0
    digest_poll_s: float = 1.0  # the assembly worker's wake interval
    digest_max_age_s: float = 60.0  # the digest assembly's freshness bound
    staffing_escalate_hours: float = 1.0
    checkpoint_cadence_minutes: float = 15.0
    fulfillment_stall_minutes: float = 120.0
    run_records_dir: Path = PIPELINE_ROOT / "venue" / "results" / "detached"
    armed_dir: Path = ATTENTION_HOME / "var" / "armed"
    # The supervision registry's declaration rows: instance
    # data, held in an untracked file under the state home
    # and read by key (services/measure/registry.py). An
    # absent file is an empty registry, honestly.
    supervision_registry_path: Path = (
        ATTENTION_HOME / "var" / "supervision-registry.json"
    )

    @classmethod
    def from_env(cls) -> Settings:
        data = os.environ.get("ATTENTION_DATA", "")
        environment = os.environ.get("ATTENTION_ENV", "local")
        data_path = Path(data) if data else None
        if (
            environment in ("dev", "test")
            and data_path is not None
            and "prod" in data_path.parts
        ):
            raise ValueError(
                f"{environment} environment refuses a production data path: {data_path}"
            )
        windows = os.environ.get("ATTENTION_WINDOWS", "")
        return cls(
            host=os.environ.get("ATTENTION_HOST", "127.0.0.1"),
            port=int(os.environ.get("ATTENTION_PORT", "8797")),
            unit_name=os.environ.get("ATTENTION_UNIT", "workhorse"),
            environment=environment,
            data_path=data_path,
            digest_windows=(
                tuple(w.strip() for w in windows.split(",") if w.strip())
                if windows
                else DEFAULT_WINDOWS
            ),
            breakthrough_cap=int(os.environ.get("ATTENTION_BREAKTHROUGH_CAP", "2")),
            focus_scope=os.environ.get("ATTENTION_FOCUS_SCOPE", "away"),
            wb_url=os.environ.get("ATTENTION_WB_URL", "http://127.0.0.1:8792"),
            wb_timeout_s=float(os.environ.get("ATTENTION_WB_TIMEOUT_S", "2.5")),
            wb_collect_timeout_s=float(
                os.environ.get("ATTENTION_WB_COLLECT_TIMEOUT_S", "30")
            ),
            stall_after_hours=float(os.environ.get("ATTENTION_STALL_HOURS", "6")),
            dispatch_claim_minutes=float(
                os.environ.get("ATTENTION_DISPATCH_CLAIM_MINUTES", "15")
            ),
            dispatch_consumer=os.environ.get(
                "ATTENTION_DISPATCH_CONSUMER", "attention-service"
            ),
            bridge_url=os.environ.get("ATTENTION_BRIDGE_URL", "http://127.0.0.1:8796"),
            bridge_token_path=Path(
                os.environ.get(
                    "ATTENTION_BRIDGE_TOKEN_PATH",
                    str(ATTENTION_HOME / "var" / "connector" / "bridge-token"),
                )
            ),
            bridge_timeout_s=float(os.environ.get("ATTENTION_BRIDGE_TIMEOUT_S", "10")),
            dispatch_pass_cap=int(os.environ.get("ATTENTION_DISPATCH_PASS_CAP", "10")),
            dispatch_max_attempts=int(
                os.environ.get("ATTENTION_DISPATCH_MAX_ATTEMPTS", "6")
            ),
            panel_url=os.environ.get("ATTENTION_PANEL_URL", "http://127.0.0.1:8793"),
            panel_timeout_s=float(os.environ.get("ATTENTION_PANEL_TIMEOUT_S", "120")),
            capacity_collect_minutes=float(
                os.environ.get("ATTENTION_CAPACITY_COLLECT_MINUTES", "5")
            ),
            capacity_stale_minutes=float(
                os.environ.get("ATTENTION_CAPACITY_STALE_MINUTES", "15")
            ),
            digest_poll_s=float(os.environ.get("ATTENTION_DIGEST_POLL_S", "1")),
            digest_max_age_s=float(os.environ.get("ATTENTION_DIGEST_MAX_AGE_S", "60")),
            staffing_escalate_hours=float(
                os.environ.get("ATTENTION_STAFFING_ESCALATE_HOURS", "1")
            ),
            checkpoint_cadence_minutes=float(
                os.environ.get("ATTENTION_CHECKPOINT_CADENCE_MINUTES", "15")
            ),
            run_records_dir=Path(
                os.environ.get(
                    "ATTENTION_RUN_RECORDS_DIR",
                    str(PIPELINE_ROOT / "venue" / "results" / "detached"),
                )
            ),
            fulfillment_stall_minutes=float(
                os.environ.get("ATTENTION_FULFILLMENT_STALL_MINUTES", "120")
            ),
            armed_dir=Path(
                os.environ.get(
                    "ATTENTION_ARMED_DIR", str(ATTENTION_HOME / "var" / "armed")
                )
            ),
            supervision_registry_path=Path(
                os.environ.get(
                    "ATTENTION_SUPERVISION_REGISTRY",
                    str(ATTENTION_HOME / "var" / "supervision-registry.json"),
                )
            ),
        )
