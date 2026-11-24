# Local adapter (manual proving path)

Operator's own machine as a compute venue: Tailscale sidecar + Docker
workspace container, SSH into the container only.

Three layers, kept separate:

- **Tracked docs** — `../../docs/local-compute.md`: the generic
  runbook, architecture, and rules. No host's actual values.
- **Tracked examples** — `template/` in this folder: the generic
  Dockerfile, compose, entrypoint, guard script, and `*.example`
  files with placeholder/example values. Copy-and-run seed material.
- **Untracked instance state** — `instance/` in this folder
  (gitignored, see `.gitignore` here): one specific host's actual
  allocation, actual cron entries, and actual env values, seeded
  from `template/`. Same separation as the venue's
  `config/*.example.json` (tracked) vs `config/*.json` (never
  tracked). Actual crons and instance logic never enter tracked
  files.

- Venue kind name for records, when used: `local`.
