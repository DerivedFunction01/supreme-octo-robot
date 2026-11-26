#!/bin/bash
set -e
# Argument surface: none — the image's CMD invokes this
# script with no arguments, and it reads no operator
# argv. This is the vendored refuse-any-argument guard
# of the unified argv contract (contract home:
# pipeline/platform/argv.py; bash adapter: argv.sh in
# the same home) — vendored, not sourced, because the
# Dockerfile copies this file OUT of the checkout into
# the image, where no adapter stands beside it. Any
# argument is a usage refusal (exit 2); --help prints
# usage. Sync obligation: if the contract's
# no-argument guard form changes in argv.sh, this
# block changes with it.
if [ $# -gt 0 ]; then
  case "$1" in
    --help|-h)
      echo "usage: entrypoint.sh"
      exit 0
      ;;
    *)
      echo "entrypoint: unexpected argument: $1" >&2
      echo "usage: entrypoint.sh" >&2
      exit 2
      ;;
  esac
fi
# Authorized keys are mounted read-only at /run/secrets/authorized_keys.
# Copy (never symlink) so sshd StrictModes ownership checks pass.
if [ -f /run/secrets/authorized_keys ]; then
  AGENT_HOME="$(getent passwd agent | cut -d: -f6)"
  cp /run/secrets/authorized_keys "$AGENT_HOME/.ssh/authorized_keys"
  chmod 600 "$AGENT_HOME/.ssh/authorized_keys"
  chown agent:agent "$AGENT_HOME/.ssh/authorized_keys"
fi
# GitHub clone auth is provisioned state, restored on every start:
# the instance's key and the pinned host keys are mounted read-only
# at /run/secrets (setup.sh places them in the instance folder),
# and the agent's git config is rewritten to match — a container
# rebuild never strands jobs without clone auth.
if [ -s /run/secrets/id_github ] && [ -f /run/secrets/known_hosts_github ]; then
  AGENT_HOME="$(getent passwd agent | cut -d: -f6)"
  cp /run/secrets/id_github "$AGENT_HOME/.ssh/id_github"
  cp /run/secrets/known_hosts_github "$AGENT_HOME/.ssh/known_hosts_github"
  chmod 600 "$AGENT_HOME/.ssh/id_github"
  chmod 644 "$AGENT_HOME/.ssh/known_hosts_github"
  chown agent:agent "$AGENT_HOME/.ssh/id_github" "$AGENT_HOME/.ssh/known_hosts_github"
  sudo -u agent git config --global url."git@github.com:".insteadOf "https://github.com/"
  sudo -u agent git config --global core.sshCommand "ssh -i $AGENT_HOME/.ssh/id_github -o UserKnownHostsFile=$AGENT_HOME/.ssh/known_hosts_github -o StrictHostKeyChecking=yes"
fi
# The Vercel login is planted state on the same pattern: the
# instance's host-side auth copy is mounted read-only at
# /run/secrets/vercel-auth.json (setup.sh --vercel-auth-file
# places it in the instance folder) and planted into the CLI's
# data dir on every start, so a rebuild restores the login the
# copy carries. The CLI binary itself is image provisioning
# (the Dockerfile's pinned global install), never planted.
if [ -s /run/secrets/vercel-auth.json ]; then
  AGENT_HOME="$(getent passwd agent | cut -d: -f6)"
  mkdir -p "$AGENT_HOME/.local/share/com.vercel.cli"
  cp /run/secrets/vercel-auth.json "$AGENT_HOME/.local/share/com.vercel.cli/auth.json"
  chmod 600 "$AGENT_HOME/.local/share/com.vercel.cli/auth.json"
  chown -R agent:agent "$AGENT_HOME/.local"
fi
# Persist SSH host keys in the ssh-host-keys volume so a container
# recreate does not change the host key and break known_hosts.
mkdir -p /var/run/sshd /workspace /etc/ssh/host-keys-store
if ls /etc/ssh/host-keys-store/ssh_host_*_key >/dev/null 2>&1; then
  cp /etc/ssh/host-keys-store/ssh_host_* /etc/ssh/
else
  ssh-keygen -A
  cp /etc/ssh/ssh_host_* /etc/ssh/host-keys-store/
fi
chmod 600 /etc/ssh/ssh_host_*_key 2>/dev/null || true
chown agent:agent /workspace || true
# Venue clients connect in parallel bursts (the local sshd admits
# concurrent connections, and each dispatch/poll is its own short
# connection through a ~1-2 s proxy CONNECT, so the unauthenticated
# window is long). The stock MaxStartups 10:30:100 drops new
# connections past 10 concurrent startups — clients die in banner /
# kex exchange, intermittently, exactly under multi-lane load.
# Raise the startup window to the venue's real concurrency.
mkdir -p /etc/ssh/sshd_config.d
printf 'MaxStartups 30:50:200\n' > /etc/ssh/sshd_config.d/60-venue-maxstartups.conf
exec /usr/sbin/sshd -D -e
