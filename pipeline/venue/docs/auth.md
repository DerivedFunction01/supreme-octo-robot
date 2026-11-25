# Colab authentication — the credential, the guards, and re-authorization

Findings first: the stored credential is guarded at
every seam — no automated path may invoke the CLI's
interactive login, and any auth death surfaces as an
explicit `auth_required` state instead of junk data.
The defenses below make the loss class — an automated
call destroying the token by falling into the
interactive flow — structurally impossible.

## The credential

- Canonical file: `~/.config/colab-cli/token.json` (mode 600), mirrored
  to `state/transient/colab-cli/token.json` under the transient
  registry (`validate: colab-token`).
- Strategy: `colab --auth oauth2` — Google's InstalledAppFlow
  (copy-paste code variant, redirect hosted at
  sdk.cloud.google.com). The client is Google's public Cloud SDK
  installed-app client (`764086051850-…apps.googleusercontent.com`),
  not a project owned by the operator, so no testing-mode refresh-cap
  applies; the re-auth cadence is measured from the live grant,
  not assumed.
- Validity check used everywhere: the file parses as JSON and carries
  a `refresh_token` string of length ≥ 20. Contents are never printed
  or logged.
- The current grant is an oauth2 InstalledAppFlow grant on
  the public Cloud SDK client, recovered by direct code
  exchange. Standing rule: an authorization code never
  transits an agent's re-typing unverified — verify the
  transcribed code against the message record before
  submitting it, or move it as a file.

## The guards

- `bin/colab-run`'s `colab()` — the single funnel for automated CLI
  calls: refuses to invoke the CLI when the stored token is
  missing/invalid; snapshots the token before each call and restores
  it (atomically) if the call leaves it invalid, including on
  timeout; any output carrying the login prompt becomes an
  auth-required result (rc 3, empty stdout) and drops a marker at
  `var/auth-required.json`, cleared by the next healthy call. Inert
  under `COLAB_BIN` (test fakes are not credential flows).
- The same funnel snapshots the session binding (`sessions.json`):
  the CLI rewrites it non-atomically on
  ordinary calls, and a write denied after the truncate left it at
  0 bytes — every recorded session read absent and the fleet
  blinded while its lease records stayed correct. A call that
  leaves the binding missing or unparseable gets the snapshot
  restored atomically; a binding that still parses (even `{}`) is
  the CLI's own view and is never overridden wholesale. Entry
  level: a call that prunes an individual entry
  from a parseable binding gets it restored verbatim from the
  snapshot — merged into the CLI's current map — when the
  session's lease record names a deadline in the future; the
  CLI's rewrites drop entries under load while their assignments
  live on, and the record is the authority on what should exist.
  An entry with no live record stays pruned. The mirror's
  never-capture-empty guard counts an unparseable canonical as
  empty, so a torn binding can no longer overwrite its last good
  mirror copy either.
- `sync/lease/sessions/sessions.py`: `session_state` treats a prompt-carrying list as
  unknown, never absent; `acquire` branches on the tri-state and
  never stops/deletes/recreates on unknown (`acquire-unknown`);
  `budget_check` maps the guard's signal to reason `auth-required`;
  `state()` serves `auth_required` from the marker for the panel.
- Mirror (`ops/mirror_transient.py`): the token item is validated —
  an invalid canonical heals from a valid mirror on capture; an
  invalid copy never overwrites a valid one in either direction,
  regardless of mtimes.
- Atomic token writes (owner ruling): every save, mirror, restore,
  and the renewal kit's in-VM placement writes a `.tmp` sibling and
  renames it over the live file; the token is never written in place
  under its live name.

## Re-authorization procedure

1. Start `colab --auth oauth2 usage` and give the owner the URL.
2. The owner approves and pastes the code. Verify the code
   byte-for-byte before submitting it (see the standing rule above).
3. Confirm the token file is valid (keys + refresh_token length
   only) and run a live `usage`/`sessions` check; the new
   grant then stands as the credential of record.

<!-- Portability exception (gate component directive):
portability-exception: ~/.config/colab-cli/token.json — the colab CLI's own per-user token file, the canonical location this document governs
-->
