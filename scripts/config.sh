#!/usr/bin/env bash
# config.sh — Shared configuration for Windows GPU operations
# Source this file: source "$(dirname "$0")/config.sh"

# NOTE: Each executable script sets its own `set -euo pipefail`.
# This file only defines variables and functions.

# --- Locale (ensure UTF-8 for prompts with non-ASCII chars) ---
export LANG="${LANG:-en_US.UTF-8}"

# --- Connection (override via environment) ---
WINDOWS_HOST="${ACE_WINDOWS_HOST:-100.69.202.122}"
WINDOWS_USER="${ACE_WINDOWS_USER:-shockang}"
SSH_KEY="${ACE_SSH_KEY:-$HOME/.ssh/id_ed25519_win}"
SSH_PORT="${ACE_SSH_PORT:-22}"

# --- SMB ---
SMB_SHARE_NAME="${ACE_SMB_SHARE:-share}"
MOUNT_POINT="${ACE_MOUNT_POINT:-/Volumes/share}"

# --- ACE-Step paths on Windows ---
ACE_SCRIPT_DIR="${ACE_SCRIPT_DIR:-C:/Users/shockang}"
ACE_OUTPUT_DIR="${ACE_OUTPUT_DIR:-C:/share}"

# --- Defaults ---
DEFAULT_TIMEOUT="${ACE_TIMEOUT:-300}"
GPU_VRAM_THRESHOLD_GB="${ACE_GPU_THRESHOLD:-20}"

# --- Logging ---
log_info()  { echo "[$(date '+%H:%M:%S')] [INFO]  $*"; }
log_warn()  { echo "[$(date '+%H:%M:%S')] [WARN]  $*" >&2; }
log_error() { echo "[$(date '+%H:%M:%S')] [ERROR] $*" >&2; }

# --- SSH helper: run command on Windows machine ---
# Usage: ssh_cmd "command arg1 arg2"
ssh_cmd() {
    ssh -i "$SSH_KEY" \
        -o ConnectTimeout=10 \
        -o StrictHostKeyChecking=accept-new \  # trust-on-first-use; verify host key on first connect
        -o ServerAliveInterval=30 \
        -o ServerAliveCountMax=3 \
        -p "$SSH_PORT" \
        "${WINDOWS_USER}@${WINDOWS_HOST}" \
        "$@"
}

# --- Retry helper: retry ATTEMPTS DELAY COMMAND [args...] ---
# Usage: retry 3 5 ssh_cmd "echo hello"
retry() {
    local attempts="$1"
    local delay="$2"
    shift 2

    for i in $(seq 1 "$attempts"); do
        if "$@"; then
            return 0
        fi
        if [ "$i" -lt "$attempts" ]; then
            log_warn "Attempt $i/$attempts failed, retrying in ${delay}s..."
            sleep "$delay"
        fi
    done
    log_error "All $attempts attempts failed"
    return 1
}
