# apps/scheduler

The scheduler app: the viewer client and its host bridge
binding over the pipeline's `/api/v1` shapes
(`pipeline/scheduling/server/serving/`). Its frontend is
`frontend/` (package `scheduler-frontend` in the gate's
`pipeline/gate/frontends.json`).

- **Governed by:** contract 09 (app shell + bridge
  adapter); payloads stay this app's own. The viewer is a
  consumer — derivations, labels, and status semantics are
  pipeline-served (contract 06).
- **Surfaces:** overview, jobs list/detail, pings, and
  ledger, on the kit and the one shell.
- **Retains as its own:** job entries authored by operators
  (content; the pipeline owns the registry they land in)
  and the viewer surfaces.
- Bridge-down stays distinct from server-down; on live data
  the shell stays read-only (ack, suspend, and admit live
  in the CLIs; the one `/api/v1` write is the job-config
  POST the pipeline serves).
