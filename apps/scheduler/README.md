# apps/scheduler

The scheduler app: the viewer client and its host bridge
binding over the pipeline's `/api/v1` shapes.

- **Lands in:** step S8 (scheduler pin `cf910ce`), stage
  deploy D2. Backend half: the served-shape adapters that
  keep every §2 payload identical; frontend half: overview,
  jobs list/detail, and pings surfaces on the extracted kit
  and the one shell.
- **Governed by:** contract 09 (app shell + bridge
  adapter); payloads stay this app's own. The viewer is a
  consumer — derivations, labels, and status semantics are
  pipeline-served (contract 06).
- **Retains as its own:** job entries authored by operators
  (content; the pipeline owns the registry they land in)
  and the viewer surfaces.
- Bridge-down stays distinct from server-down; the viewer
  stays read-only (ack, suspend, admit live in the CLIs).
