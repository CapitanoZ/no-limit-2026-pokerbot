#!/bin/bash
# One command: sync this folder to the remote competition machine, benchmark there, print results.
#
# Why remotely: a decision gets only 1 ms, and a Mac does not run at the same speed as the
# competition's Linux machines, so timings taken on the Mac do not count.
#
# Usage:  tools/remote_bench.sh            benchmark the generic parts (tools/bench_core.py)
#         tools/remote_bench.sh SCRIPT     benchmark another script
#
# If the remote machine already has the starter kit environment (~/work/starter-kit/.venv),
# use its Python; otherwise use the system python3.12.

set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
HOST="no-limit-2026-build"
REMOTE_DIR="work/nl26"
SCRIPT="${1:-tools/bench_core.py}"

rsync -az --delete \
  --exclude '.venv' --exclude '__pycache__' --exclude 'starter-kit' \
  --exclude 'offline/out' --exclude '.DS_Store' \
  "$HERE/" "$HOST:$REMOTE_DIR/"

ssh "$HOST" "cd ~/$REMOTE_DIR && \
  PY=python3.12; \
  if [ -x ~/work/starter-kit/.venv/bin/python ]; then PY=~/work/starter-kit/.venv/bin/python; fi; \
  echo \"remote machine: \$(hostname), Python: \$(\$PY --version)\"; \
  OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \$PY $SCRIPT"
