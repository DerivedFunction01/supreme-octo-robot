#!/usr/bin/env bash
# The local venue union gate: form the union of two or more
# gate-ready constituent tips in a fresh clone, prove every
# constituent is contained in the resulting tree, and run
# the scoped check once over the union. The constituents
# and the check paths arrive as the dispatcher's generated
# constituents.json, staged beside this script.
set -u
RUN_DIR=$(cd "$(dirname "$0")" && pwd)
RUN_ID=$(basename "$RUN_DIR")
cd "$RUN_DIR" || exit 2

if [ ! -f constituents.json ]; then
  echo "union-gate: constituents.json was not staged in the run dir" >&2
  exit 2
fi

# Validate the staged payload and flatten it into shell
# arrays, in the order the dispatch was given.
python3 - constituents.json > constituents.sh <<'PY'
import json
import shlex
import sys

try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    constituents = data["constituents"]
    check_paths = data["check_paths"]
    if len(constituents) < 2:
        raise ValueError("at least two constituents are required")
    if not check_paths or not all(isinstance(p, str) and p for p in check_paths):
        raise ValueError("at least one check path is required")
    branches = []
    shas = []
    for item in constituents:
        branch = item["branch"]
        sha = item["sha"]
        if not isinstance(branch, str) or not branch:
            raise ValueError("each constituent must name a branch")
        if (
            not isinstance(sha, str)
            or len(sha) != 40
            or any(ch not in "0123456789abcdefABCDEF" for ch in sha)
        ):
            raise ValueError("each constituent must carry a full 40-hex SHA")
        branches.append(branch)
        shas.append(sha)
except Exception as exc:
    print(f"union-gate: invalid constituents.json: {exc}", file=sys.stderr)
    raise SystemExit(2)
print("BRANCHES=(" + " ".join(shlex.quote(v) for v in branches) + ")")
print("SHAS=(" + " ".join(shlex.quote(v) for v in shas) + ")")
print("CHECK_PATHS=(" + " ".join(shlex.quote(v) for v in check_paths) + ")")
PY
[ $? -eq 0 ] || exit 2
# shellcheck disable=SC1091
. ./constituents.sh

# The clone rides the container's planted git config
# (the plant script's insteadOf + core.sshCommand), the
# form every in-container clone of this repo takes.
git clone -q git@github.com:redacted/supreme-octo-robot.git src || exit 2
cd src || exit 2
# No identity is set here: the clone inherits the venue's
# configured global identity (the one approved pair). A
# hardcoded pair in this script is how an empty email was
# minted into gate trees before the venues carried one.

# Fetch every constituent and prove its tip is present
# before any merge is attempted.
for i in "${!BRANCHES[@]}"; do
  git fetch -q origin "${BRANCHES[$i]}" || exit 2
  if ! git cat-file -e "${SHAS[$i]}^{commit}" 2>/dev/null; then
    echo "union-gate: constituent ${BRANCHES[$i]} ${SHAS[$i]} is not present after fetch" >&2
    exit 2
  fi
done

# Form the union: the first tip is the base, the rest merge
# in the order given. A conflicted merge names the
# constituent and its conflicted paths and fails the fire.
git checkout -q --detach "${SHAS[0]}" || exit 2
for ((i = 1; i < ${#BRANCHES[@]}; i++)); do
  if ! git merge --no-edit "${SHAS[$i]}" > "../merge-output-$RUN_ID.txt" 2>&1; then
    cat "../merge-output-$RUN_ID.txt" >&2
    conflicts=$(git diff --name-only --diff-filter=U)
    if [ -n "$conflicts" ]; then
      echo "union-gate: merge conflict in constituent ${BRANCHES[$i]} ${SHAS[$i]}" >&2
      printf '%s\n' "$conflicts" >&2
    else
      echo "union-gate: merge failed for constituent ${BRANCHES[$i]} ${SHAS[$i]}" >&2
    fi
    exit 1
  fi
done

for i in "${!BRANCHES[@]}"; do
  if ! git merge-base --is-ancestor "${SHAS[$i]}" HEAD; then
    echo "union-gate: constituent ${BRANCHES[$i]} ${SHAS[$i]} is not an ancestor of HEAD" >&2
    exit 2
  fi
done

HEAD=$(git rev-parse HEAD)
echo "union head: $HEAD"
export TMPDIR="$PWD/../tmp-$RUN_ID"
export STARTER_DENYLIST_FILE=/home/agent/workspace/denylist.txt
# Divided thread budget: this gate's envelope is bounded to
# half the venue's pid ceiling. Library pools are capped per
# process, so the footprint is workers x capped pools, never
# workers sized as if each owned the whole machine.
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
export MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2
export POLARS_MAX_THREADS=2 RAYON_NUM_THREADS=2
mkdir -p "$TMPDIR"
python3 init_venv.py || exit 2
GATE_WORKERS=$(nproc) python3 check.py "${CHECK_PATHS[@]}" > "../check-output-$RUN_ID.txt" 2>&1
rc=$?
python3 - "$RUN_ID" "$rc" "$HEAD" <<'PY'
import json
import sys

json.dump(
    {"run_id": sys.argv[1], "check_rc": int(sys.argv[2]), "head": sys.argv[3]},
    open(f"../gate-result-{sys.argv[1]}.json", "w"),
    indent=1,
)
PY
tail -3 "../check-output-$RUN_ID.txt"
exit $rc
