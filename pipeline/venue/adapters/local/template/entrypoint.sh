#!/bin/bash
set -e
# Authorized keys are mounted read-only at /run/secrets/authorized_keys.
# Copy (never symlink) so sshd StrictModes ownership checks pass.
if [ -f /run/secrets/authorized_keys ]; then
  cp /run/secrets/authorized_keys /home/agent/.ssh/authorized_keys
  chmod 600 /home/agent/.ssh/authorized_keys
  chown agent:agent /home/agent/.ssh/authorized_keys
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
exec /usr/sbin/sshd -D -e
