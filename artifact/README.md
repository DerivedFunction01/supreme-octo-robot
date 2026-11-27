# Workhorse Superapp — full-stack source

The TypeScript source of the workhorse superapp: one Space, one
server, and one integrated client in which Workbench, Scheduler,
Attention, and Runner are views — not separate apps. This tree is
the repo-side source the publish pipeline syncs and publishes; it
is not itself the published artifact. The client's composition
contract is `client/INTEGRATION.md`.

## Layout

- `space.json` — the space's identity (runtime `typescript`,
  platformVersion 28).
- `server/src/privileged.ts` — the privileged bridge module:
  five loopback contracts (wbApi, wbRaw, schedulerApi,
  attentionApi, runnerApi) in the workbench dialect (validated
  zod schemas, `network.loopback`, a raw `node:net` socket per
  call), plus the `hostEnv` contract that reads the host
  process's env host-side.
- `server/src/env.ts` — the env seam: actions read the host env
  only through the hostEnv contract (the SDK's action context
  has no env member and action code may not read env).
- `server/src/bridge-core.ts` — the one bridge implementation
  (status-0 semantics: timeout ≠ unreachable ≠ server error;
  one retry for reads, never on a timeout or a write).
- `server/src/<app>/` — per app: `config.ts` (the only module
  naming that backend's host/port), `bridge.ts`, and
  `actions.ts` — one thin proxy action per backend route,
  envelope `{status, payload, error}`. The workbench set splits
  its actions across `actions-core.ts`, `actions-code.ts`,
  `actions-entries.ts`, and `actions-messages.ts`, aggregated
  by its `actions.ts`, and also carries `page.ts` and
  `schemas.ts`.
- `server/src/actions.ts` — the aggregator: the space's single
  `Actions` registry plus the per-app groups
  (`workbenchActions`, `schedulerActions`, `attentionActions`,
  `runnerActions`).
- `server/.generated/privileged.contract.ts` — the builder's
  contract extraction from `privileged.ts` (generated; do not
  edit).
- `client/index.html` → `client/src/main.tsx` →
  `client/src/App.tsx` — the one client's entry and shell:
  launcher, unified Settings, and the four app views behind one
  hash router. There are no iframes, no postMessage relay, and
  no per-app documents or bundles; the one exception is the
  sandboxed `srcDoc` iframe inside the workbench entry-preview
  page (see `client/INTEGRATION.md` §11.7).
- `client/src/lib/actions.ts` — the client's single typed
  action layer, typed over the merged server registry; views
  import transport from nowhere else.
- `client/src/lib/` — also the hash router (`router.ts`), the
  appearance state (`appearance.ts`), and the view-mount
  contract (`view-contract.ts`).
- `client/src/shell/` — the shell views and chrome pieces:
  `Launcher.tsx`, `Settings.tsx`, `PresenceControl.tsx`,
  `apps.tsx` (app identity, tiles, glyphs).
- `client/src/views/<app>/` — the four app views, each with a
  statically imported `meta.ts` (nav, active key, search
  declaration, crumb) and its component tree mounted through
  the shell's mount seam.
- `client/build.mjs` — the SDK's canonical single-bundle build
  with a shape guard: staging holds exactly one document
  (`dist/index.html`) and exactly one JS bundle.
- `client/parity-check.mjs` — the staged-build parity check,
  run as the last leg of `verify:client`.

## Config seams (env names → loopback defaults)

| App | Env names | Default |
| --- | --- | --- |
| Workbench | `WB_VIEWER_HOST` / `WB_VIEWER_PORT` | 127.0.0.1:8792 |
| Scheduler | `SCHEDULER_API_HOST` / `SCHEDULER_API_PORT` | 127.0.0.1:8796 |
| Attention | `ATTENTION_HOST` / `ATTENTION_PORT` | 127.0.0.1:8797 |
| Runner | `VENUE_LEASE_UI_HOST` / `VENUE_LEASE_UI_PORT` | 127.0.0.1:8793 |

## Build

    bun install
    bun run typecheck    # tsc --noEmit, client + server projects
    bun run build        # server bundle + client staging
    bun run verify:client  # frozen install, typecheck, client build, parity check

The SDK is consumed as the host's packaged tarball (see
`package.json`). The kit is consumed from its repo home as the
declared dependency `"@workhorse/kit": "file:../kit"` — never
copied into the client.
