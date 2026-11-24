# S1 overlay inventory — owner-attention (existential capture)

Pin `7f13ae797ca068a258b53054dc34a4e0df9c7fa2`. Captured
first, before the other repos, at **2026-11-13T01:46:21-0500
EST**. Attention is live: everything below is a snapshot at
that instant, and the live store has moved since. Held
copies under `holding/owner-attention/`.

## The store — captured verbatim

`var/data/state.json` — one read, one copy:
**393,986 bytes, SHA-256
`01963cf412a8ba72728b6b6f88bd211288d91889c80224a5fb7b906f54db8ba4`**.
Every registry attention owns lives only in this file; it
migrates as data (contract §4.1/§9 seed-and-export), never
as code. Counts taken from the captured copy:

| Registry | At review | At capture | Delta |
|---|---|---|---|
| handlers | 10 | 10 | — |
| programmes | 3 | 3 | — |
| sends | 39 | 47 | +8 — live dispatch traffic: 9 sends timestamped at/after 2026-11-12T20:00Z, 5 of them after 2026-11-13T00:00Z, all outcomes `recorded` |
| items (the queue) | 52 | 53 | +1 — newest `waiting_since` 2026-11-12T20:55Z, after the review's count |
| rules | (in vocab) | 8 | vocabulary contents migrate as data |
| templates | (in vocab) | 18 | with versions, as records |
| status_codes / fields / wait_classes / item_kinds / action_rules | (in vocab) | 8 / 12 / 16 / 11 / 7 | same |
| waits | — | 0 | queue side-table, empty at capture |
| presence | `away`, expectation set | mode `away`, expectation set, expiry carried in the record | preserved verbatim in the held copy |
| armed_rows (in-store projection) | — | 2 | matches the 2 files under `var/armed` |
| owner_actions / dispatch_failures | — | 26 / 442 | ledger-side state, carried inside the store |

## Load validation (done-evidence)

The held copy was copied once more into a scratch dir
(removed after, verified gone) and loaded through the
pinned code's own path — `backend/infra/store.py`'s
`JsonFileStore.load_state()` — read-only, no save:
**loaded with no exception; every count above identical
raw vs loaded; presence mode `away` preserved; all
top-level keys survive the load** (the loader's
empty-state merge + registry backfill overwrote nothing).

## Also captured as data

`var/armed/` — the workbench's machine-written rows,
verbatim (hashes match source exactly; the programme
names in the file names are genericized here —
programme-a / programme-b — and the held copy carries
them as written):

| File | Bytes | SHA-256 |
|---|---|---|
| var/armed/wb-armed-programme-a-t-01k8r0000000000000000000b1.json | 554 | 7b3bcb3286abb7afac7adfa6e207f2e4ca7503da7b8ffc60bf11dd12f4a0bb85 |
| var/armed/wb-armed-programme-b-t-01k8r0000000000000000000b2.json | 595 | 6d1239aa0237584d132bde3c892a1ec74b54a252c6f2305210a7ea932f5f74fc |

## Credential — reference only

`var/connector/bridge-token` — the bridge caller credential
for the scheduler harness connector (contract 01 carries
its nature: hash-only on the scheduler side, raw token only
in this file). Exists at capture, 43 bytes, mode 600.
**Inventoried by reference only: the value was never
copied, read into any file, printed, or hashed.**

## Paths out of the repo — inventoried for re-basing

From the captured store's programme rows and the pinned
settings (`backend/foundation/settings.py`; no environment
override was in evidence — defaults are the record):

- `run_records_dir` = `<workspace>/colab-runner/results/detached`
  (settings default; env seam `ATTENTION_RUN_RECORDS_DIR`).
- Programme 1: `worktree_roots`
  `['<workspace>/programme-a-*-wt']`,
  `record_locations` `[]`, `contract_path`
  `<workspace>/programme-a/.plans/…/contract.md` (the
  specific plan directory is elided here; the held copy
  carries the path verbatim).
- Programme 2: `worktree_roots`
  `['<workspace>/programme-a-*-wt']`,
  `record_locations` `[]`, `contract_path` none.
- Programme 3: `worktree_roots`
  `['<workspace>/programme-b-wt-*']`,
  `record_locations` `[]`, `contract_path`
  `<workspace>/programme-b/.plans/…/contract.md` (elided
  the same way).
- `armed_dir` = own `var/armed` (above); `bridge_token_path`
  = own `var/connector/bridge-token` (reference only, above).

These paths are re-based here to the `<workspace>` form;
in the held copy they are absolute, exactly as written —
S7/S10 re-base them rather than discovering the breakage
after the move.

## Not captured

| Path | Census | Class |
|---|---|---|
| var/xfer/ | 639 files, 49,100,948 B | debris — probe scripts, tarballs, screenshots from venue-side test loops |
| var/storyboard-build/ | 12 files, 552,419 B | debris — storyboard build state (`gen.py`, `spec.json`, frames) |
| var/venv/ | 1,332 files, 192,650,591 B | debris — the repo venv, rebuildable via its init path |
| var/data/serve.log | 0 B at capture | runtime log, not carried |
| var/state/owner-attention.log | 179,237 B | runtime log, not carried (a `var/state` population §3 does not name; recorded here so it is accounted for) |
