# S1 overlay inventory — workbench-viewer

Pin `b0b9cc58b2cf6f0231173e659b2f9d38d12bec8c`. Nothing is
held for this repo: its overlay classes are inventoried in
place (registry data never migrates — AGENTS.md preserve
rule), live config with tracked specimens, or runtime state.

## Manifest census — the sweep's view at capture

The pinned harness's own sweep (`lib/sweep.py`, run from
this repo against the workspace root, read-only) returned
**11 canonical projects, 241 manifest roots, 0 errors**.
Every root + manifest SHA-256 is in
[workbench-manifest-census.json](workbench-manifest-census.json).
Ten slugs hold exactly one root; `programme-b` folds 231
roots (its worktrees and exports) into one canonical
project — the fold grew during the capture hour as new
worktrees were created, which is why this count is a
snapshot, not a constant.

## Per-project registry stores — inventoried in place

Each project's DB was opened read-only in place from the
mega-repo side (SQLite `mode=ro`); all 11 read cleanly —
that is the §3 verification that the tooling reads them
where they live. All carry the unified schema
(`user_version` 2; tables `entries`, `history`, `todos`,
`todo_events`). Registry DBs and exports stay in their
owning repos; nothing was copied.

| Project (root) | Registry DB — bytes / SHA-256 / rows (entries, history, todos, todo_events) | registry.json — bytes / SHA-256 |
|---|---|---|
| colab-runner | 32,768 / `bbddc202cc4ccf504e43058ac423d1a9912198d51771ee535858dda00a361a4d` / 1, 3, 0, 0 | 3,772 / `e277f5c3ecfd8cc877243c17a9178a8e75a432a308af020dcfe9b65737283881` |
| programme-a | 32,768 / `a9c6b5410389302f102ef88eb1f960b033fee9dc40f9f018bc31db1a019de088` / 0, 0, 0, 0 | 373 / `44c96e4261721a8df3c45588cd5e002eb849c0da6a0eb1b7352293916682add2` |
| job-search | 32,768 / `eb2dab3ec86533930caedb02af95e2185e8e416f7054833c5ada33649d524fa8` / 0, 0, 0, 0 | 375 / `33d2b845affe0263bd5f8d29445b477462ec96ff2f5357374708b77c2556c66c` |
| owner-attention | 49,152 / `d4f681d733348d46a9ee5096ca31485595853bf28ab9663a39a7cfe6c88ecd6b` / 4, 19, 0, 0 | 17,824 / `28581780aa6e1860995ea9665a2a67de7f89b2021ea4e6c12052d4b896bcbc71` |
| scheduler | 32,768 / `eb2dab3ec86533930caedb02af95e2185e8e416f7054833c5ada33649d524fa8` / 0, 0, 0, 0 | 373 / `6fc6b71c39341709c5997529354bd8fed52784ce911ce02d3c093f213100786d` |
| spec-driven-starter | 32,768 / `eb2dab3ec86533930caedb02af95e2185e8e416f7054833c5ada33649d524fa8` / 0, 0, 0, 0 | 393 / `d52689662f95434db5686f7309594852808e1d9a1f8e5014253541c446066c06` |
| staging | 32,768 / `896f6aa6dcd634f991b82035082aa92720a93f75f668026713fefdfcff30121d` / 2, 4, 0, 0 | 4,202 / `5adff31696022311897790e8e16d2d8816e6be0e2084d712c12418b94535a7f3` |
| programme-b | 61,440 / `668557a86646d92c9c6472c93bb718bbe35c9fc6b1ac3c3877e212663c133623` / 10, 60, 0, 0 | 48,104 / `9e36a3c14769b3c799cc4c9eba5e878205940aad2983452220c2bfd1f42f37d6` |
| tax-receipts | 32,768 / `eb2dab3ec86533930caedb02af95e2185e8e416f7054833c5ada33649d524fa8` / 0, 0, 0, 0 | 379 / `21b9f45c5f237416b12fef106780eb3cf6785def1c0ef3d587997990dfea17f1` |
| paywatch-v2 | 90,112 / `f28fe3d5e43253831f6e5f633b4df31c6c7b5e27882402696117072aeb7dd9b2` / 42, 140, 0, 0 | 117,332 / `219c5c152f166dfcdcce9aaef453e5057f1c7a0d412db1a55861c36ab7f4709d` |
| workbench-viewer (own) | 32,768 / `bb1117e4ddd4e255f8873f81860d045e05ffb683d1dfdd556e03dbfb25feae5f` / 1, 6, 4, 10 | 10,175 / `f58689aae367993005e04b5feaa9480ada351d49dc8e1e829b37566d79218a17` |

Manifest SHA-256 per canonical root: colab-runner
`3706f450…`, programme-a `cff39da4…`, job-search `df3e4c19…`,
owner-attention `b9f5d6f9…`, scheduler `b177d59f…`,
spec-driven-starter `1285f4ff…`, staging `d7ab7419…`,
programme-b `f87308e9…`, tax-receipts `226166b2…`,
paywatch-v2 `a6ce2411…`, workbench-viewer
`7b2825b6…` (full values in the census JSON). The identical
DB hashes across the empty projects are the same empty
unified-schema DB — expected, not a copy error. WAL
sidecars (`registry.db-wal`/`-shm`) exist beside live DBs
and are runtime state, not carried.

## This repo's own overlay

- **`config.json`** (50 B, SHA-256
  `e09c6dfff772da5b559fb2225c965ae0f7faab4faeb72e6817f48e4360175f64`)
  — live config; keys are only `file_editing_enabled` and
  `port`. Tracked specimen `config.example.json` exists.
  Inventoried, not held (the specimen + defaults carry the
  contract; the live file is two scalars).
- **`viewer.env`** (330 B, SHA-256
  `8fd0c963c3ac15970191f41eba4504d7eb2fe6a42dfe8c624f3155d70d86b04b`)
  — live config; the only variable name present is `HOME`.
  Tracked specimen `viewer.env.example` exists. Inventoried
  by name + hash, not held, values not read into this
  inventory.
- **`state/`** — runtime state, not carried: 22 files,
  74,318,133 B — `health.json`, `link.json`, `repair.json`,
  `server.lock`, `messages.db` (598,016 B, the second
  store), `repos-registry.json` (343,949 B, the server-local
  registry cache), `doctor-findings.json`, `edit-log.jsonl`,
  `repos-history.jsonl` (7,461,544 B), logs
  (`doctor.log` 60,522,437 B, `server.log`, `stackdumps.log`),
  `denylist.txt` (the portability denylist — live config by
  nature, runtime by location; named here so it is not
  lost), two zero-byte probe temp files (debris), and
  `edit-backups/` (7 `.bak` files) — **two of those backups
  are secret-bearing by name (`secrets.env.bak`,
  `probe-secret.env.bak`): inventoried by reference only,
  never copied, never read.**
- **Templates ride the tree** (tracked, verified via
  `git ls-files`): 9 files under `templates/manifest/`,
  `templates/staging/`, `templates/choice-kit/` — not
  overlay, no capture action.
- The two registries this repo *writes into siblings* (the
  scheduler `wb-progress-*` entries and attention's armed
  rows) are captured in those repos' inventories.
