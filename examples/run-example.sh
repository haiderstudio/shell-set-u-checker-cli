#!/bin/sh
# Run the checker over each example file and show the result.
# The flagged example fails on purpose, so each run is allowed to fail.
set -eu
cd "$(dirname "$0")/.."
for f in examples/clean.sh examples/flagged.sh examples/edge.sh; do
  echo "== $f =="
  python3 src/shell_set_u_checker.py "$f" || true
  echo
done
echo "== examples/ : the whole folder =="
python3 src/shell_set_u_checker.py examples/ || true
