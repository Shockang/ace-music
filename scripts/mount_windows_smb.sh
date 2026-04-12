#!/usr/bin/env bash
# mount_windows_smb.sh — Mount, unmount, or check Windows SMB share
#
# Usage:
#   ./scripts/mount_windows_smb.sh           # mount (default)
#   ./scripts/mount_windows_smb.sh check     # check if mounted
#   ./scripts/mount_windows_smb.sh unmount   # unmount
#   ./scripts/mount_windows_smb.sh status    # print status only

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

SMB_URL="//${WINDOWS_USER}@${WINDOWS_HOST}/${SMB_SHARE_NAME}"

# --- Check if share is mounted ---
is_mounted() {
    mount | grep -qF " on ${MOUNT_POINT} "
}

# --- Print mount status ---
print_status() {
    if is_mounted; then
        log_info "SMB share mounted at ${MOUNT_POINT}"
        log_info "  URL: ${SMB_URL}"
        local avail
        avail=$(df -h "$MOUNT_POINT" 2>/dev/null | tail -1 | awk '{print $4}' || echo "unknown")
        log_info "  Available: ${avail}"
        return 0
    else
        log_warn "SMB share NOT mounted at ${MOUNT_POINT}"
        return 1
    fi
}

# --- Mount the share ---
do_mount() {
    if is_mounted; then
        log_info "Already mounted at ${MOUNT_POINT}"
        return 0
    fi

    # Create mount point if missing
    if [ ! -d "$MOUNT_POINT" ]; then
        log_info "Creating mount point: ${MOUNT_POINT}"
        sudo mkdir -p "$MOUNT_POINT"
    fi

    log_info "Mounting ${SMB_URL} -> ${MOUNT_POINT}"

    # Try mount_smbfs first (non-interactive, works in scripts)
    if mount_smbfs "$SMB_URL" "$MOUNT_POINT" 2>/dev/null; then
        log_info "Mounted successfully via mount_smbfs"
        return 0
    fi

    # Fallback: open command (may prompt in GUI)
    log_warn "mount_smbfs failed, trying open command (may prompt for password)..."
    if open "smb:${SMB_URL}"; then
        log_info "Waiting for mount..."
        local waited=0
        while [ "$waited" -lt 30 ]; do
            if is_mounted; then
                log_info "Mounted successfully via open command"
                return 0
            fi
            sleep 2
            waited=$((waited + 2))
        done
    fi

    log_error "Failed to mount SMB share after both methods"
    log_error "Try manually: mount_smbfs ${SMB_URL} ${MOUNT_POINT}"
    return 1
}

# --- Unmount ---
do_unmount() {
    if ! is_mounted; then
        log_info "Not mounted, nothing to do"
        return 0
    fi

    log_info "Unmounting ${MOUNT_POINT}..."
    if umount "$MOUNT_POINT" 2>/dev/null || diskutil unmount "$MOUNT_POINT" 2>/dev/null; then
        log_info "Unmounted successfully"
        return 0
    fi

    log_error "Failed to unmount. Try: sudo umount ${MOUNT_POINT}"
    return 1
}

# --- Main ---
ACTION="${1:-mount}"

case "$ACTION" in
    mount)    do_mount ;;
    check)    is_mounted ;;
    status)   print_status ;;
    unmount)  do_unmount ;;
    *)
        echo "Usage: $(basename "$0") [mount|check|status|unmount]" >&2
        exit 1
        ;;
esac
