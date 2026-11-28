#!/usr/bin/env bash
# gate-wrap-example-20261127 — scoped gate formed from the canonical gate-job
# template (template/gate-job/ in the local adapter). Formation
# substitutes the __TOKENS__ below; the template README is the
# formation form.
#
# Order is the discipline: form the tree hermetically in the
# job-private DEST, assert its composition by sha BEFORE any
# verdict is read, then run the scoped check once — one
# re-proof on red, in the same fire — and emit the products.
# The verdict is read from products/gate-result.json, never
# from the log alone.
set -uo pipefail

JOB="gate-wrap-example-20261127"
BRANCH="main"          # clone source branch
WANT="c1c7d67289e96c6bc5c55217f5e0801d13f514f0"          # the tree the gate judges, full sha
ASSERT_TIP="0"  # 1: branch tip must equal WANT
                             # (transport-branch form); 0: landed
                             # tree — the HEAD assertion binds
CHECK_PATHS="tests/engine/forms/sections"
WORKERS="8"        # sized from the venue resource
THREADS="2"        # probe at formation, never copied

RUN_DIR=$(pwd)
PROD=$RUN_DIR/products
WORK=$RUN_DIR/work
DEST=$WORK/tree
mkdir -p "$PROD" "$WORK"
exec > >(tee -a "$PROD/gate-log.txt") 2>&1
export PATH="$HOME/.local/bin:$PATH"

# The clone source is a formation value, never a template
# literal: REPO_URL from the environment, or the job dir's
# planted repo-url.txt (untracked; repo-url.txt.example is
# the tracked form).
if [ -z "${REPO_URL:-}" ] && [ -f "$RUN_DIR/repo-url.txt" ]; then
  REPO_URL=$(cat "$RUN_DIR/repo-url.txt")
fi
[ -n "${REPO_URL:-}" ] || { echo "REPO_URL unset: formation value missing"; exit 2; }

# Composition expectations, populated at formation from the
# gated head: every listed file's sha256 equals the head's
# content, every listed path is absent. Empty lists assert
# nothing beyond the HEAD sha.
declare -A EXPECTED_SHA256=(
  ["specimen_sec/engine/forms/sections/items/legal_proceedings.py"]="483c77a4fedcbdfc900ca75f64f9231c7094e4fe87cdd32233d074b7b5d78a7d"
  ["specimen_sec/engine/forms/sections/models.py"]="329ec5387a17652410d3ed017efc6ebc26ccf885e58e86bac7b077e977a69e63"
  ["tests/engine/forms/sections/items/test_legal_proceedings.py"]="5ecd67469d1a5c5732219362d32c0df37609d4040a857dddd05bea1e47f97dbe"
  ["specimen_sec/engine/forms/sections/README.md"]="31a47c2bb090a97465f5eb9aa973ea21c5ef7b90721185201c65dd5bee3b28ae"
)
EXPECTED_ABSENT=(
  "specimen_sec/engine/forms/sections/items/legal.py"
  "specimen_sec/engine/forms/schedules/legal.py"
)

write_result() {
  JOB="$JOB" RESULT_STATE="$1" WANT="$WANT" HEAD="${HEAD:-}" \
  COMPOSITION="${COMPOSITION:-}" SHA_ASSERTED="${SHA_ASSERTED:-0}" \
  ABSENT_ASSERTED="${ABSENT_ASSERTED:-0}" CHECK_RC="${CHECK_RC:-}" \
  TESTS_PASSED="${TESTS_PASSED:-}" TESTS_FAILED="${TESTS_FAILED:-}" \
  VERDICT_SOURCE="${VERDICT_FILE:-}" \
  python3 - "$PROD/gate-result.json" <<'PYEOF'
import json, os, sys

def num(name):
    v = os.environ.get(name, "")
    return int(v) if v.lstrip("-").isdigit() else None

doc = {
    "job": os.environ["JOB"],
    "state": os.environ["RESULT_STATE"],
    "want": os.environ["WANT"],
    "head": os.environ["HEAD"] or None,
    "composition": os.environ["COMPOSITION"] or None,
    "sha_asserted": int(os.environ["SHA_ASSERTED"]),
    "absent_asserted": int(os.environ["ABSENT_ASSERTED"]),
    "check_rc": num("CHECK_RC"),
    "verdict_source": os.environ["VERDICT_SOURCE"] or None,
    "tests_passed": num("TESTS_PASSED"),
    "tests_failed": num("TESTS_FAILED"),
}
with open(sys.argv[1], "w") as fh:
    json.dump(doc, fh, indent=1)
PYEOF
}

fail() {
  echo "WRAP FAIL: $1"
  write_result failed
  exit 2
}

# Hermetic formation: DEST is rebuilt from the clone alone,
# so no previous tenant's files linger in the gated tree.
rm -rf "$DEST"
git clone -q -b "$BRANCH" "$REPO_URL" "$DEST" || fail "clone failed"
cd "$DEST" || exit 2
if [ "$ASSERT_TIP" = "1" ]; then
  REMOTE=$(git ls-remote "$REPO_URL" "refs/heads/$BRANCH" | cut -f1)
  echo "ls-remote $BRANCH: $REMOTE"
  [ "$REMOTE" = "$WANT" ] || fail "branch tip mismatch, want $WANT"
fi
git checkout -q "$WANT" || fail "checkout of $WANT failed"
HEAD=$(git rev-parse HEAD)
echo "gate tree: $HEAD"
[ "$HEAD" = "$WANT" ] || fail "HEAD mismatch, want $WANT"

# Composition assertion, before any verdict is read.
SHA_ASSERTED=0
for path in "${!EXPECTED_SHA256[@]}"; do
  [ -f "$path" ] || fail "expected file missing: $path"
  actual=$(sha256sum "$path" | cut -d' ' -f1)
  [ "$actual" = "${EXPECTED_SHA256[$path]}" ] || fail "sha mismatch: $path"
  SHA_ASSERTED=$((SHA_ASSERTED + 1))
done
ABSENT_ASSERTED=0
for path in "${EXPECTED_ABSENT[@]}"; do
  [ ! -e "$path" ] || fail "expected-absent path present: $path"
  ABSENT_ASSERTED=$((ABSENT_ASSERTED + 1))
done
COMPOSITION=exact
echo "composition exact: $SHA_ASSERTED file sha(s), $ABSENT_ASSERTED absence(s)"
write_result composed

# Seed venv, formed by the tree's own builder when absent —
# in the hermetic DEST it is always formed fresh.
python3 init_venv.py > "$PROD/venv-log.txt" 2>&1 \
  || fail "venv formation failed (see venv-log.txt)"
export TMPDIR="$WORK/tmp"
mkdir -p "$TMPDIR"
export POLARS_MAX_THREADS=$THREADS OMP_NUM_THREADS=$THREADS \
       OMP_THREAD_LIMIT=$THREADS OPENBLAS_NUM_THREADS=$THREADS \
       MKL_NUM_THREADS=$THREADS RAYON_NUM_THREADS=$THREADS \
       NUMEXPR_NUM_THREADS=$THREADS VECLIB_MAXIMUM_THREADS=$THREADS

# Scoped check, once; one re-proof on red in the same fire.
# Both runs stand in the products; the result record names
# the verdict source.
.venv/bin/python check.py $CHECK_PATHS --workers "$WORKERS" \
  > "$PROD/check.txt" 2>&1
CHECK_RC=$?
VERDICT_FILE=check.txt
if [ $CHECK_RC -ne 0 ]; then
  echo "first run red (rc=$CHECK_RC); re-proof once in the same fire"
  .venv/bin/python check.py $CHECK_PATHS --workers "$WORKERS" \
    > "$PROD/check-reproof.txt" 2>&1
  CHECK_RC=$?
  VERDICT_FILE=check-reproof.txt
fi
TESTS_PASSED=$(grep -oE "[0-9]+ passed" "$PROD/$VERDICT_FILE" | tail -1 | grep -oE "^[0-9]+") || true
TESTS_FAILED=$(grep -oE "[0-9]+ failed" "$PROD/$VERDICT_FILE" | tail -1 | grep -oE "^[0-9]+") || true
TESTS_FAILED=${TESTS_FAILED:-0}
if [ $CHECK_RC -eq 0 ]; then
  write_result complete
  echo "GATE GREEN"
else
  write_result failed
  echo "GATE RED"
  grep -E "^FAILED|^ERROR" "$PROD/$VERDICT_FILE" | head -15 || true
fi
echo DONE
exit $CHECK_RC
