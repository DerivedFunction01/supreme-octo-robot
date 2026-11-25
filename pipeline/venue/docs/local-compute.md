# Local compute venue — operator's own machine (WSL2 + Docker)

Findings first: a local machine joins as a venue through Tailscale + SSH
into a Docker container only. The container is the isolation boundary:
disk, temp files, CPU and memory are capped there, and the host
filesystem outside one mounted workspace folder is not visible.

Template: `../adapters/local/template/` — copy the whole folder to the
host (e.g. `$HOME/agent-workspace/` in WSL), fill it in, `docker compose up -d`.

## Architecture

- Two services, one network namespace: `tailscale` (sidecar, owns the
  venue's tailnet identity — its name, set at setup) and `ubuntu`
  (workspace, `network_mode: service:tailscale`).
- SSH terminates in the `ubuntu` service. Do not use Tailscale SSH
  (`TS_EXTRA_ARGS=--ssh`): it terminates in the sidecar container,
  which has no workspace, tools, or mounted code.
- The connecting agent VM is tailnet client-only: outbound TCP only,
  through its runtime proxy (port 3130). No inbound, no ping/UDP test
  exists — an SSH banner read through the proxy is the reachability test.
- First tunnel request to an exact tailnet IP/name needs the operator's
  approval; it then covers other TCP ports on that same address. Keep
  using one address form.

## Venue character (for runner registration)

- Venue kind: `local`. A node's identity (hostname, tailnet
  address, host machine) is instance state, recorded in the
  untracked `adapters/local/instance/` folder; the template's
  example node name is `agent-ubuntu`.
- **No budget.** A local machine prices nothing: no rate, no daily
  or monthly cap, no spend segments. Registration must carry the
  venue with null/zero pricing — a fabricated rate or cap is a
  defect, and budget checks must never gate its use.
- **Availability is the host's power state.** The venue exists when
  the computer is on and its containers are up; a shutdown host is
  simply unavailable — a probe failure, never an error, a spend
  event, or a lease breach. Liveness probe: tailnet peer present +
  SSH banner from the workspace container.
- **Concurrent SSH.** SSH terminates in the workspace container's
  OpenSSH sshd, which admits concurrent connections (measured:
  4 parallel connections with 5 s sleeps finished in 12 s wall,
  all exit 0) — the one-connection-at-a-time property belongs to
  Colab runtimes and their bridge channel, not to this venue.
  Each connection pays roughly 1–2 s of CONNECT setup through the
  proxy. `bin/local-run` still launches jobs detached (nohup +
  exit file) and polls their records: drop-safety by dispatcher
  design, so a lost client connection never kills a job — never
  a channel constraint.
- Registration is a test of the venue layer's genericity: it should
  register through configuration and records, with no massive code
  change. Any surface that cannot name `local` beside `colab` is
  the gap list, priced per file.

## Standing maintenance rule

This template is a living source of record, not a one-time setup.

- A job on this venue that hits a missing dependency, a wrong flag, or
  a stale instruction is fixed in the template and in this doc in the
  same change — the `Dockerfile`, the compose file, or the step that
  was wrong. Installing a package or patching a config inside the
  running container only is a defect: the fix dies on recreate and
  the next setup re-hits it.
- A container-local hotfix may unblock a running job, but it is not
  done until the template carries it and the image rebuilds clean
  from the template (`docker compose build --no-cache ubuntu` for a
  dependency change).
- Same rule for Tailscale: an auth, approval, DNS, or ACL step that
  had to be discovered live is written into the Tailscale section
  below in the same change, in the place the next setup will look.

## Tailscale setup, in full

The tailnet side is configured once in the admin console
(https://login.tailscale.com/admin), by the operator — the agent VM
is a client-only member and cannot administer, approve, or accept
invites for the tailnet.

1. **Auth key** — Settings > Keys > Generate auth key:
   - Reusable: on (the compose restarts against the same key).
   - Ephemeral: off (this is a persistent machine, not a CI runner;
     an ephemeral node deletes itself when it goes offline).
   - Expiry: take the maximum offered. Auth keys expire (90 days max);
     a key only gates the *first* join — a joined node keeps working
     after its key expires, and rotation is: generate new key, update
     `.env`, `docker compose up -d tailscale`.
   - Pre-approved: on if offered (skips step 3). Never share the key:
     not in chat, not in a commit, not in a log. A key that has
     appeared anywhere is revoked here and replaced.
2. **MagicDNS** — DNS page: enable MagicDNS so the node is reachable
   by its node name, not only by its `100.x` address. Either form
   works; the agent side must keep using one form consistently,
   because its tunnel approval is per exact address.
3. **Device approval** — Settings > General > Device approval: if on,
   a new node joins in a pending state and appears under Machines
   with an approval action. A node that built and started but never
   appears in the connecting peer's `tailscale status` is pending
   here until approved — check this before debugging Docker.
4. **Key expiry for the node** — Machines > the node > Disable
   key expiry. Server-like nodes get expiry disabled, or the node
   will silently drop off the tailnet at its key-expiry date and need
   a console re-enable.
5. **Hostname** — the node's name is chosen at setup (`--name`,
   e.g. the machine's branding) and carried in the instance `.env`
   as `TS_HOSTNAME`, which the compose reads. Name every machine:
   an unnamed install takes the template default `agent-ubuntu`,
   and the tailnet counter-suffixes a duplicate (`agent-ubuntu-1`)
   instead of refusing it. A rename in the console (Machines > ...
   > Edit machine name) changes the MagicDNS name and must be
   mirrored in `.env` (then `docker compose up -d tailscale`), or
   the two drift.
6. **What is not used** — no exit node, no subnet routes, no
   Tailscale SSH (see Architecture), no funnel/serve. An ACL or tag
   (`tag:compute`) is optional hardening; adding a tag requires the
   tag to exist in the tailnet ACL's `tagOwners` first, or the
   sidecar's login fails — do not add `TS_EXTRA_ARGS=--advertise-tags`
   before the ACL carries it.
7. **Invite links** — an `/admin/invite/...` link shares a device or
   invites a user, and is accepted in a browser by a tailnet admin.
   It is not an auth key, does not join the container, and cannot be
   consumed by the agent VM or by `docker compose`.
8. **Sidecar mechanics** — `TS_USERSPACE=false` + `/dev/net/tun` +
   `net_admin` is kernel-mode networking, which the shared-network
   workspace container requires. If the sidecar log shows a TUN
   failure, the host is missing `/dev/net/tun` in WSL (Docker Desktop
   provides it; a bare docker-ce install in WSL may need the host
   rebooted after a WSL update) — userspace mode is not a fallback
   here, because the workspace service would lose inbound SSH.

## One-command setup (the normal path)

Clone the repo, run one command, answer two prompts. No file is
edited by hand and no heredoc is pasted — the script does every
step in the manual list below, in order:

```bash
git clone <this repo> && cd supreme-octo-robot
pipeline/venue/adapters/local/setup.sh
```

Plan of what the script does:

1. Prompts (or takes flags / env) for the Tailscale auth key and
   the connecting agent's SSH public key; limits are flags with
   defaults: `--cpus`, `--mem`, `--workspace-gb`, `--total-gb`,
   `--target` (default `$HOME/agent-workspace`), `--name` (the
   tailnet node name; default `agent-ubuntu` — name each machine).
   Fully non-interactive form, with example values:
   `setup.sh --authkey ... --authorized-key '...' --name hp-envy
   --cpus 4 --mem 8g --workspace-gb 96 --total-gb 128 --yes`.
2. Copies `template/` into the target and writes the instance
   `.env` (key + limits + derived guard thresholds) at mode 600
   and `authorized_keys`. A re-run preserves an existing `.env`
   key — rotation is an explicit `--authkey`, never a side effect.
   The GitHub clone key rides the same way: `--github-key-file`
   copies it into the instance as `id_github` (mode 600, preserved
   on re-runs), the template carries the pinned `known_hosts_github`,
   and the entrypoint plants both into the agent's `.ssh` and git
   config on every container start.
3. Creates the workspace image at the requested size, mounts it,
   and adds the `/etc/fstab` remount line if absent.
4. Installs the disk-guard cron idempotently.
5. `docker compose up -d --build`, then prints the tailnet peer
   list and the toolchain/caps smoke. A peer list that shows only
   the node itself means the key came from the wrong tailnet (see
   Tailscale setup) — the script surfaces it, the operator fixes
   the key and re-runs.

The generate half is testable without Docker: `--skip-docker
--skip-mount` writes every file and stops. Verified that way
against the tracked template (files complete, `.env` 600, compose
parses).

## Operate — start, stop, status

Every command runs on the host, in WSL, from the instance folder
(the `--target` chosen at setup; default `$HOME/agent-workspace`):

```bash
cd "$HOME/agent-workspace"
docker compose up -d            # start both services
docker compose up -d --build    # start, rebuilding after a template change
docker compose ps               # status: both containers
docker exec agent-tailscale tailscale status   # tailnet status: own 100.x, peers
docker compose restart          # restart both services in place
docker compose stop             # stop both (state kept; the node goes offline)
docker compose down             # stop and remove the containers and network
```

- `down` keeps the `tailscale-state` volume and `./workspace`, so
  the next `up -d` rejoins with the same node identity and name.
- Stop only the tailnet side with `docker compose stop tailscale`:
  the node leaves the tailnet while the workspace container keeps
  running (unreachable, but its state is untouched).
- Reset all scratch: `docker compose down && docker compose up -d`
  (what survives is listed under Containment).

### Rebuilds — what is restored, what is lost

A rebuild (setup re-run, image rebuild, container recreate) is
invisible to jobs by construction:

- **Restored by provisioning:** the toolchain — node and the
  pinned Vercel CLI among it — and the Chromium OS libraries
  (the image), the SSH authorized keys and the GitHub clone
  plant — key, pinned host keys, git config (the entrypoint,
  from the instance folder, on every start), the SSH host keys
  (their volume), the tailnet identity (the tailscale-state
  volume), and the workspace (its disk image).
- **The Vercel login, stated exactly:** the CLI is provisioning
  (above); the login is not guaranteed by provisioning alone
  while a rebuild wipes the container home. The guarantee is
  one of two forms: a host-side auth copy in the instance
  folder (`setup.sh --vercel-auth-file`, on the
  `--github-key-file` pattern) that the entrypoint re-plants
  at every container start — the login restored is the one
  the copy carries, so a copy taken before a token rotation
  restores a stale login — or a fresh device login per
  rebuild. There is no third form: an auth file that exists
  only inside the container is lost with the home.
- **Lost, by accepted disposition:** the rest of the container
  filesystem — including the agent home's `runs` directory with
  any run outputs not yet collected, and anything installed by
  hand inside the container.
  Host-side run records survive a rebuild; work whose outputs
  were not collected is re-fired by its owning lane from those
  records. Run outputs are regenerable, so they are not carried
  across rebuilds — a job that must survive a rebuild writes to
  `/workspace`.

## Setup (host, in WSL) — manual fallback, what the script does

1. Revoke any auth key that has appeared in chat, logs, or a commit.
   Generate a fresh one: Tailscale admin > Settings > Keys —
   reusable, non-ephemeral, pre-approved if offered.
2. `cp .env.example .env`, put the key in `.env`, `chmod 600 .env`.
   `.env` is gitignored; never paste the key anywhere.
3. `cp authorized_keys.example authorized_keys`, add the connecting
   agent's SSH public key (one `ssh-ed25519 ...` line).
4. `mkdir -p workspace` — this folder, and only this folder, is mounted
   at `/workspace` in the container.
5. `docker compose up -d --build`
6. Verify from the host:
   `docker logs agent-tailscale` (look for a successful login),
   `docker exec agent-tailscale tailscale status` (own `100.x` address),
   `docker logs agent-workspace` (sshd listening).
   If the node does not appear in the tailnet, check Admin > Machines
   for a pending device approval — that is the usual cause.
7. Verify from the agent side: SSH through the proxy to
   `agent@<node tailnet IP>` and read back
   `hostname && df -h /tmp /workspace && nproc && free -h`.
8. Smoke the toolchain in the container — every line must print a
   version, and a miss here is a template defect under the standing
   maintenance rule, fixed in the `Dockerfile`, not in the container:
   `docker exec agent-workspace bash -lc 'python3 --version; node --version; vercel --version; uv --version; git --version; rg --version | head -1; fd --version; sqlite3 --version; sshd -h 2>&1 | head -1 || true'`

## Containment — disk budget (per-instance total)

Each instance gets a total disk budget, set at setup
(`--total-gb`, carried in the instance `.env`): a workspace hard
cap plus a guarded Docker share adding up to that total. An
uncapped bind mount and overlay are the creep path — without the
image below, the workspace presents the WSL distro's full disk
and the container overlay the host's.

- **Workspace: hard cap.** `workspace/` is a fixed-size ext4 disk
  image (`workspace.img`, sparse `truncate -s <size>G` +
  `mkfs.ext4`, loop-mounted at `workspace/`; an `/etc/fstab` line
  remounts it on WSL start), sized by `--workspace-gb`. The
  container's bind mount then presents exactly that size; writes
  fail `ENOSPC` inside the venue, never on the host. Convert while
  the workspace is empty — conversion replaces the directory's
  contents.
- **Docker storage: the remaining share, guarded — no hard cap
  exists on Windows.** Images, container writable layers, and
  named volumes live in Docker Desktop's WSL disk image
  (`%UserProfile%\AppData\Local\Docker\wsl`). On the WSL 2 backend
  there is no disk-image size setting (that slider is macOS-only);
  resource limits on Windows are managed by Windows itself, via
  `%UserProfile%\.wslconfig` (`[wsl2] memory= / processors= / swap=`),
  which caps the whole WSL 2 VM — every distro and Docker together —
  so it is a coarser lever than the per-container cgroup caps.
  Docker storage is therefore held to its share (total minus
  workspace) by the guard below plus prune discipline
  (`docker system df` / `docker system prune`), not by a hard cap.
- **Guard:** `disk-guard.sh` in the template, on a 15-minute WSL
  cron — warns at total−8 GB, stops the workspace container at the
  total (thresholds read from the instance `.env`). On Windows
  this is the primary enforcement for the Docker share, not a
  backstop. Docker Desktop's Resource Saver (Settings > Resources)
  additionally idles Docker's own CPU/RAM when no container is
  running; it does not bound disk.
- `/tmp` in the workspace container is a 2G tmpfs (inside the Docker
  cap): temp files cannot fill the host disk and vanish on removal.
- Container logs capped (10m x 3, both services).
- CPU/memory/pids are capped via `deploy.resources.limits` in
  compose (`COMPUTE_MEM` / `COMPUTE_CPUS` in `.env`). A specific
  host's allocation is instance state, recorded in the untracked
  `adapters/local/instance/` folder — the tracked template carries
  example values only. The legacy `mem_limit`/`cpus` keys are ignored by Compose
  v2 — verified live, an uncapped container saw all host CPUs and RAM.
- Reset all scratch: `docker compose down && docker compose up -d`.
  Host state that survives is only `./workspace` (the image) and the
  `tailscale-state` volume.

## Troubleshooting

- Node absent from `tailscale status` on the agent VM: pending approval
  in the admin console, a revoked/expired auth key, or the sidecar
  failing on `/dev/net/tun` — read `docker logs agent-tailscale` first.
- Windows host SSH answering on the host's own tailnet IP (port 22) is
  the Windows OpenSSH server, not the container. It proves the host is
  on the tailnet; it does not prove the container is reachable.
- A shared-device invite link is accepted in the admin console by the
  tailnet owner; an agent cannot accept it from its client-only VM.

## Status

The proving path is complete: a host set up by the one-command
setup is reachable by SSH from the agent side, with workspace
write, the full toolchain, and its caps verified from inside the
container. A specific host's live status and allocation are
instance state, in the untracked `adapters/local/instance/`
folder.

As a session, a local venue's character is the inverse of a
Colab session:

- **Lifetime: near-unlimited.** No lease, no deadline, no reap. It
  is up whenever the host computer is on, and down when it is shut
  down — availability is the power state, nothing else.
- **Storage: static.** The workspace is a persistent disk image
  on the host, sized at setup, not session scratch: files survive
  container recreates, reboots, and any future adapter's sessions.
- **Budget: none.** Unmetered, zero-priced (see Venue character).

Runner registration is the Tier 1 small change priced in the
audit record; running jobs through the runner (Tier 2, an SSH
adapter) is a separate commission, not part of this proving path.
