#!/usr/bin/env bash
# The local venue smoke job: proves the dispatch path end to
# end — the script ran on the venue, under its own resource
# caps, and its output rode back into the run record.
set -e
echo "host: $(hostname)"
echo "user: $(whoami)"
echo "cpus (cgroup): $(cat /sys/fs/cgroup/cpu.max)"
echo "memory max (cgroup): $(cat /sys/fs/cgroup/memory.max)"
echo "workspace: $(df -h /workspace | tail -n 1)"
