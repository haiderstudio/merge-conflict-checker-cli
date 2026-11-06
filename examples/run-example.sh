#!/bin/sh
# Run the checker on the bundled examples.
# Run from the repo root: sh examples/run-example.sh
# The check run exits 1 because two example files carry markers on
# purpose — that is the expected result here.
set -e
cd "$(dirname "$0")/.."
echo "--- check the clean file ---"
python3 src/merge_conflict_checker.py examples/clean.py
echo "--- check the conflicted files ---"
python3 src/merge_conflict_checker.py examples/conflicted.py examples/conflicted-diff3.txt || true
