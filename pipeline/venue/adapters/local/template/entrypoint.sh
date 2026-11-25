#!/bin/bash
set -e
# Authorized keys are mounted read-only at /run/secrets/authorized_keys.
# Copy (never symlink) so sshd StrictModes ownership checks pass.
if [ -f /run/secrets/authorized_keys ]; then
  AGENT_HOME="$(getent passwd agent | cut -d: -f6)"
  cp /run/secrets/authorized_keys "$AGENT_HOME/.ssh/authorized_keys"
  chmod 600 "$AGENT_HOME/.ssh/authorized_keys"
  chown agent:agent "$AGENT_HOME/.ssh/authorized_keys"
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
