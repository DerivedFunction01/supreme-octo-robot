# Local adapter — the local venue

Operator's own machine as a compute venue: Tailscale sidecar + Docker
workspace container, SSH into the container only. Jobs run through
the runner (`bin/venue-run`) against the lease config's local
targets; `local_compute_fwd.py` here is the tunnel forwarder the
lease's transport lifecycle launches (its pin file rides as
argv[3], its listen port as argv[4], default 2222).

Layers, kept separate:

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
- **Job manifests** — `jobs/` in this folder: the local
  venue's job manifests (`job.json` + `run.sh`) that
  `bin/venue-run` ships to the container. A manifest may
  also declare `uploads`: files relative to the venue root
  that ship beside the script into the run dir under their
  basenames before launch (the local form of the Colab
  job's uploads). The standing consumer is the code drop —
  `jobs/mfa-drop` (per local target): the relay stages the
  code at `var/mfa-code.txt`, fires the job, and the script
  delivers it atomically into the venue checkout's
  `var/state/code-files/mol.txt` and shreds the staged
  copy, the Colab `mfa-drop` job's semantics in the local
  form; the checkout path is the head variable of each
  job's `run.sh`.

- Venue kind name for records, when used: `local`.
