#!/usr/bin/env bash
# Strip re-measure: provisioned denylist scan over the composed
# strip tree (formation/strip-composed @ 5e551f1e), canary first.
# Payloads are staged in the venue-side strip-remeasure-stage
# directory by the seat's staging driver over the runner's SSH
# channel (the denylist is untracked provisioned material; it
# never rides a tracked file).
# The literal itself is never printed: the scanner reports rule,
# path and line only, and the canary plants the list's first
# literal by file surgery, never by echo.
set -u
# pipefail: the verdict block below pipes through tee so the run
# dir carries verdict.txt; without pipefail the script's exit
# face is tee's (0) even on a FINDINGS or CANARY verdict, and a
# later reader trusting the record's exit over the verdict file
# reads a failed measure as clean. With pipefail the block's
# exit (2 stage-fail, 3 canary-not-flagged, 4 findings) is the
# script's.
set -o pipefail
STAGE="$HOME/strip-remeasure-stage"
TIP="5e551f1e1c8523ed8474f1cdc74259c905b9ba45"
TREE_SHA="6f319fa7df792eb041bb4b2eb1539a05da18043f"
export SCHEDULER_DENYLIST_FILE="$STAGE/denylist.txt"

{
  echo "strip re-measure: $(date -u +%Y-%m-%dT%H:%M:%SZ) host $(hostname)"
  git clone -q "$STAGE/tree.bundle" tree || { echo "VERDICT: STAGE-FAIL clone"; exit 2; }
  cd tree || exit 2
  git checkout -q "$TIP" || { echo "VERDICT: STAGE-FAIL checkout"; exit 2; }
  HEAD=$(git rev-parse HEAD)
  TREE=$(git rev-parse 'HEAD^{tree}')
  echo "HEAD: $HEAD"
  echo "tree: $TREE"
  if [ "$HEAD" != "$TIP" ] || [ "$TREE" != "$TREE_SHA" ]; then
    echo "VERDICT: STAGE-FAIL tree assertion"
    exit 2
  fi
  echo "tree assertion: OK"
  cd ..

  # Canary: a copy of the tree with the list's first literal
  # planted into a tracked markdown file. The scan must flag it;
  # a canary that does not flag proves the scan is not armed and
  # voids the clean reading.
  cp -a tree canary
  python3 - "$STAGE/denylist.txt" canary <<'PYEOF'
import subprocess, sys
denylist_path, root = sys.argv[1], sys.argv[2]
literals = [ln.strip() for ln in open(denylist_path, encoding="utf-8")
            if ln.strip() and not ln.strip().startswith("#")]
assert literals, "denylist carries no literals"
out = subprocess.run(["git", "-C", root, "ls-files", "*.md"],
                     capture_output=True, text=True)
targets = [ln for ln in out.stdout.splitlines() if ln.strip()]
assert targets, "no tracked markdown file for the canary"
target = root + "/" + targets[0]
with open(target, "a", encoding="utf-8") as fh:
    fh.write("\n" + literals[0] + "\n")
print("canary planted in:", targets[0])
PYEOF
  python3 "$STAGE/portability.py" --root "$PWD/canary" --fail-on-denylist > canary-scan.log 2>&1
  CANARY_LINE=$(grep -E '^denylist: [0-9]+ finding' canary-scan.log | head -1)
  echo "canary scan: $CANARY_LINE"
  CANARY_N=$(echo "$CANARY_LINE" | grep -oE '[0-9]+' | head -1)
  if [ -z "$CANARY_N" ] || [ "$CANARY_N" -lt 1 ]; then
    echo "VERDICT: CANARY-NOT-FLAGGED — the clean reading is void"
    exit 3
  fi
  echo "CANARY: FLAGGED ($CANARY_N finding(s))"

  # Clean scan over the pristine composed tree.
  python3 "$STAGE/portability.py" --root "$PWD/tree" --fail-on-denylist > clean-scan.log 2>&1
  CLEAN_LINE=$(grep -E '^denylist: [0-9]+ finding' clean-scan.log | head -1)
  echo "clean scan: $CLEAN_LINE"
  PORT_LINE=$(grep -E '^portability:' clean-scan.log | head -1)
  echo "clean scan generic leg: $PORT_LINE"
  CLEAN_N=$(echo "$CLEAN_LINE" | grep -oE '[0-9]+' | head -1)
  if [ "$CLEAN_N" = "0" ]; then
    echo "VERDICT: CLEAN — canary flagged, composed tree reads zero"
  else
    echo "VERDICT: FINDINGS — composed tree reads $CLEAN_N denylist finding(s)"
    grep -E '^denylist/personal-literal' clean-scan.log | head -20
    exit 4
  fi
} | tee verdict.txt
