#!/usr/bin/env bash
# Plant the account GitHub SSH key on this session (Route B kit, ops/github-sync.md):
# installs the key + pinned known-hosts under $HOME/.ssh and rewrites github.com HTTPS
# clone URLs to SSH via git config, so the existing clone paths (env_build unit 1,
# colab-check base_clone) authenticate unmodified. The key lives only on this
# session and dies with it; removal is an explicit shred from the operator side.
#
# Successor restoration (2026-11-15): the original runner carried this
# script as untracked var material invoked by a tracked job; the move
# to pipeline/venue lost the job, and fresh rotations came up
# credential-less. The script is tracked here now (byte-faithful to
# the original apart from this header and the probe target), invoked
# by adapters/colab/jobs/plant-github-key/job.json. The probe repo —
# the private repo the ls-remote leg proves readable — is named by
# the untracked kit (var/kit-github/probe_repo, uploaded into the
# run's directory as probe_repo), never by tracked code; with no probe named,
# the ssh greeting alone verifies the plant.
#
# The two halves have different homes (plant cure, 2026-11-24): the key is a
# secret and rides the untracked kit, but the known-hosts half is GitHub's
# published host keys — public, pinned, and tracked beside this script as
# known_hosts_github, which the job uploads from there. A plant assembled
# from the kit alone once lost exactly that half on rotated generations
# (config and key present, hosts file absent, every branch clone dead on
# host-key verification); the tracked artifact is the half's single source.
set -uo pipefail
OUT="${SHELL_JOB_OUT:-/content/plant-github-key-out}"
case "$OUT" in /*) ;; *) OUT="/content/$OUT" ;; esac
mkdir -p "$OUT"
LOG="$OUT/plant.log"
: > "$LOG"
fail() { echo "PLANT FAILED: $1" >> "$LOG"; cat "$LOG"; exit 1; }

# Uploads land in the run's own directory (runner Step 5);
# shell_job exports it as SHELL_JOB_UPLOADS. The /content
# fallback is the pre-Step-5 slot, for a hand-driven run.
UP="${SHELL_JOB_UPLOADS:-/content}"
[ -f "$UP/id_ed25519" ] || fail "key upload missing at $UP/id_ed25519"
[ -f "$UP/known_hosts_github" ] || fail "known-hosts upload missing"

mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
cp "$UP/id_ed25519" "$HOME/.ssh/id_github" && chmod 600 "$HOME/.ssh/id_github"
cp "$UP/known_hosts_github" "$HOME/.ssh/known_hosts_github" && chmod 644 "$HOME/.ssh/known_hosts_github"
PROBE_REPO=""
if [ -f "$UP/probe_repo" ]; then
  PROBE_REPO="$(head -n 1 "$UP/probe_repo" | tr -d '[:space:]')"
fi
rm -f "$UP/id_ed25519" "$UP/known_hosts_github" "$UP/probe_repo"

git config --global url."git@github.com:".insteadOf "https://github.com/"
git config --global core.sshCommand "ssh -i $HOME/.ssh/id_github -o UserKnownHostsFile=$HOME/.ssh/known_hosts_github -o StrictHostKeyChecking=yes"

GREETING="$(ssh -i "$HOME/.ssh/id_github" -o UserKnownHostsFile="$HOME/.ssh/known_hosts_github" -o StrictHostKeyChecking=yes -T git@github.com 2>&1 </dev/null || true)"
echo "ssh greeting: $GREETING" >> "$LOG"
echo "$GREETING" | grep -q "successfully authenticated" || fail "ssh auth to github did not greet"

if [ -n "$PROBE_REPO" ]; then
  HEAD_LINE="$(git ls-remote "https://github.com/${PROBE_REPO}.git" HEAD 2>&1 </dev/null || true)"
  echo "ls-remote: $HEAD_LINE" >> "$LOG"
  echo "$HEAD_LINE" | grep -Eq "^[0-9a-f]{40}[[:space:]]+HEAD$" || fail "private repo not readable over the planted key"
fi

echo "PLANT OK" >> "$LOG"
cat "$LOG"
exit 0
