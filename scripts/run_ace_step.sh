#!/usr/bin/env bash
# run_ace_step.sh — Generate music via ACE-Step on Windows GPU.
# Thin compatibility wrapper around the Python remote runner.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/run_remote_ace_step.py" "$@"
