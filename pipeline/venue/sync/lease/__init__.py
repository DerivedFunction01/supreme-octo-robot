#!/usr/bin/env python3
"""The Colab lease: a session held by a caller at a shape, treated as a VM.

All session-lifecycle logic for the lease model lives here (plans:
the 2026-10-29 colab-lease-model plan for the model, the
2026-11-05 profile-retirement plan for the current shape of it).
The module is written against an injected `colab` callable with
bin/colab-run's signature — `colab(*args, timeout=...) ->
CompletedProcess` — so the fake CLI tests it with no network.
bin/colab-lease is the thin CLI; bin/colab-run and bin/colab-check
call acquire/finish_job; the reaper hook calls reap and, when
enabled in config, auto_acquire.

A lease is {session, caller, shape, window}: the session's name is
generated at creation (sync/naming.py) and never reused, the caller
is the governed attribution claim, and the shape is a catalog shape
descriptor from the CLI-parsed catalog. State: one record per
lease, var/lease-<session>.json (override the var dir with
$COLAB_RUNNER_VAR, used by tests). There is no legacy model: a
record, grant, or journal segment is read exactly as written, in
the current shape/caller vocabulary, and anything written in the
retired profile vocabulary is simply not interpreted. A two-tier
grant lives in var/grant.json. The budget
guard's spend is attributed: completed session segments are
journaled to var/lease-spend-journal.jsonl and live records
contribute their running segment, so spend counts only this repo's
own leases. Config: config/lease.json. Nothing here prints file
contents from the transient registry; the sessions binding is read
for its endpoint on the release fallback path, and for its tunnel
host when a session is born (acquire / renewal swap / adoption).
"""

from .core import foundation, catalog, callers, records, spend, accounts
from .sync import syncclaims, bridge
from .access import gate, access, grants
from .sessions import sessions, keepalive, renewal, health, identity, provisioning
from .state import listeners, orphans, reconcile, state
from .lifecycle import lifecycle, standing, reap, auto
from .core.foundation import var_dir, load_json, load_config, ACTOR_ENV_CLAIM, PANEL_ACTOR, GATE_DEFAULT_AGENT_CLASSES, GATE_DEFAULT_BYPASS_ACTORS, GATE_DEFAULT_INFRA_ACTOR, parse_dt, parse_balance, spend_journal_path, reaper_events_path, append_reaper_event, ABSENT_CONFIRM_S, absent_since, stamp_absent, clear_absent_stamp
from .core.catalog import shape_id_for, CLI_CATALOG_TTL_S, SHAPE_TIMEOUT_S, parse_cli_shapes, _catalog_cache_path, _cli_shapes, _shape_entries, shape_rates_path, load_shape_rates, shape_rate, catalog_shapes, default_shape, standing_caller, standing_shape, _session_shape_args
from .core.callers import CALLER_ENV, MACHINERY_CALLERS, _CALLER_PART, callers_path, caller_registry, active_caller_registry, is_active_caller, validate_caller, resolve_caller, caller_claim_error, caller_claims_path, append_caller_claim, load_caller_claims
from .sync.syncclaims import sync_claim_policy, active_callers, read_sync_claim, sync_rights, claim_sync, release_sync_claim
from .access.gate import shape_class, session_gate_policy, gate_journal_path, append_gate_journal, check_session_admission, enforce_session_admission, _actor_privileged, renewal_admission
from .sessions.sessions import _taken_session_names, generate_session_name, _SESSION_READ_ATTEMPTS, _SESSION_READ_BACKOFF_S, _REAP_READ_ATTEMPTS, _REAP_READ_TIMEOUT_S, session_state, session_alive, local_sessions_path, session_host, created_shape_mismatch, UNASSIGN_FALLBACK_SCRIPT, stop_session_safe, stop_endpoint_safe, session_endpoint, _endpoint_shape, live_sessions, ASSIGNMENTS_SCRIPT, BIND_SCRIPT, endpoints_match, assignments_list, bind_name_to_endpoint, prior_names_for_endpoint
from .core.records import _naming_spec, naming, _liveness_spec, liveness_entry, session_record_path, _valid_record, _record_files, all_records, load_record, save_record, delete_record, retire_superseded, run_backing, detached_backing, detached_activity, job_entry, live_jobs
from .core.spend import append_spend_segment, _journal_segments, _overlap_cu, attributed_spend, budget_check, _committed_projection
from .access.access import unattributed_path, load_unattributed, save_unattributed, clear_unattributed, access_list, release_session, release_endpoint, detect_unattributed
from .sessions.keepalive import HEARTBEAT_READ_TIMEOUT_S, heartbeat_age, prime_session_host, KEEPALIVE_UPLOAD_TIMEOUT_S, KEEPALIVE_LAUNCH_TIMEOUT_S, ensure_keepalive, keepalive_fresh, kernel_pulse, _capture_session_host
from .access.grants import grant_ledger_path, append_grant_ledger, load_grant_ledger, _note_envelope_lease_started, _note_envelope_lease_released, grant_path, load_grant, grant_active, grant_scope, grant_shapes, grant_caps, active_grant, shape_in_grant, write_grant, clear_grant, standing_record, _served_caps
from .state.orphans import _jsonl_events, _orphan_contribution, _dt_or_none, orphan_evidence, derive_orphan, nameless_census_path, recorded_endpoints, nameless_census, load_nameless_census, clear_nameless, detect_nameless
from .sessions.renewal import SESSION_CAP_HOURS, RENEWAL_MARGIN, KIT_UPLOAD_TIMEOUT_S, KIT_LAUNCH_TIMEOUT_S, HANDOVER_READ_TIMEOUT_S, RENEWAL_KIT_REMOTE, _shape_spec_for, install_renewal_kit, _swap_session, _adopt_handover, _renew_fresh_session, _attempt_renewal, _ensure_remote_dirs
from .lifecycle.lifecycle import acquire, extend, extend_grant, adopt_orphan, shorten, _job_record, touch_job, finish_job, release, ungrant
from .lifecycle.adoption import adopt_nameless
from .sessions.health import launch_health_path, append_launch_outcome, launch_health
from .sessions.identity import identity_stamp_path, probe_identity, ensure_identity, check_identity
from .state.reconcile import reconcile_journal_path, journal_disagreement
from .sync.bridge import BRIDGE_KIT_REMOTE, BRIDGE_REMOTE, BRIDGE_PROTOCOL, BRIDGE_READ_TIMEOUT_S, BRIDGE_INSTALL_COOLDOWN_S, BRIDGE_HEARTBEAT_STALE_S, bridge_limits, bridge_command, _bridge_arm_path, _bridge_arm, _bridge_arm_stamp, bridge_status_read, install_bridge_kit, _bridge_fold_stop, _bridge_ferry, bridge_duty
from .state.state import _extend_guard_spec, extend_guard, status, specs, budget_snapshot, accounts_state, budgets_state, _UNSET, set_budget_caps, auth_required, _envelope_block, _bridge_block, state_records, state_specs, state_budget, state_grant, state_meta, state_extend_guard, state_listeners, state_orphans, state
from .lifecycle.standing import standing_duty
from .lifecycle.reap import _reap_record, _REAP_PRIORITY, _reap_lock, reap, _reap_pass, GateScope, parse_gate_scope
from .lifecycle.auto import request_path, write_request, load_request, clear_request, auto_enabled, auto_acquire
