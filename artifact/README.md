# Workhorse Superapp — full-stack rebuild source

The TypeScript rebuild of the workhorse superapp (contract-09
rebuild, steps 1–2): one Space, one server, four app surfaces —
Workbench, Scheduler, Attention, Runner — behind one shell. This
tree is the repo-side source the publish pipeline (step 5) syncs
to the mirror and publishes; it is not itself the published
artifact.

## Layout

- `space.json` — the space's identity (runtime `typescript`,
  platformVersion 25).
- `server/src/privileged.ts` — the privileged bridge module:
  five loopback contracts (wbApi, wbRaw, schedulerApi,
  attentionApi, runnerApi) in the workbench dialect (validated
  zod schemas, `network.loopback`, a raw `node:net` socket per
  call), plus the `hostEnv` contract that reads the host
  process's env host-side. The socket core is the workbench
  original's, carried verbatim.
- `server/src/env.ts` — the env seam: actions read the host env
  ONLY through the hostEnv contract (the SDK's action context
  has no env member and action code may not read env).
- `server/src/bridge-core.ts` — the one bridge implementation
  (status-0 semantics: timeout ≠ unreachable ≠ server error;
  one retry for reads, never on a timeout or a write).
- `server/src/<app>/{config,bridge,actions}.ts` — per app: the
  config seam (the only module naming that backend's host/port),
  the bridge binding, and the action set — one thin proxy
  action per backend route, envelope `{status, payload, error}`.
- `server/src/actions.ts` — the aggregator: the space's single
  `Actions` registry plus the per-app groups.
- `server/.generated/privileged.contract.ts` — the builder's
  contract extraction from `privileged.ts` (generated; do not
  edit).
- `client/src/api.ts` — the shell's typed action client (the
  space's ONLY action client — see the relay below).
- `client/src/relay.ts` — the postMessage relay protocol and
  the frame-side transport (`callAppAction`) the app clients
  are written against.
- `client/src/App.tsx` — the shell: launcher, four
  always-mounted iframes, the relay listener, the composition
  messages, appearance sync.
- `client/src/frames.ts` + `client/<app>.html` — the frame
  pages (step-2 stubs proving the relay path; the apps' own
  clients are step 3).
- `client/build.mjs` — stages the entry document, the ONE
  shared bundle, and the four frame pages as
  `dist/assets/<app>.html`.

## Transport: the shell relay is primary

A frame never calls the action channel directly — the SDK
action client constructed inside an iframe does not settle
(step-1 spike). Frames post
`{type:"workhorse:action-request", id, app, action, args}` to
the shell; the shell validates the action against the app's
registered set, executes it through its single client, and
posts `{type:"workhorse:action-response", id, result}` back.
The composition messages keep the shell convention's shapes
(`"workhorse:apps"`, `workhorse:open`, `workhorse:attention-*`).

## Config seams (env names → loopback defaults)

| App | Env names | Default |
| --- | --- | --- |
| Workbench | `WB_VIEWER_HOST` / `WB_VIEWER_PORT` | 127.0.0.1:8792 |
| Scheduler | `SCHEDULER_API_HOST` / `SCHEDULER_API_PORT` | 127.0.0.1:8796 |
| Attention | `ATTENTION_HOST` / `ATTENTION_PORT` | 127.0.0.1:8797 |
| Runner | `COLAB_LEASE_UI_HOST` / `COLAB_LEASE_UI_PORT` | 127.0.0.1:8793 |

## Build

    bun install
    bun run typecheck   # tsc --noEmit, client + server projects
    bun run build       # server bundle + client staging

The SDK is consumed as the host's packaged tarball (see
`package.json`) — the form the space builder accepts; the
design's vendoring note was amended to this form at step 2.
