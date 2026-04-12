# Music Engine Windows GPU Scripts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create operational scripts to mount Windows SMB share, check GPU status, and invoke ACE-Step music generation on a remote Windows RTX 3090 Ti via SSH over Tailscale.

**Architecture:** Mac-side scripts orchestrate a remote Windows GPU machine. A shared `config.sh` holds connection params and helper functions. Each script is standalone but sources shared config. The GPU checker is Python for parseable output + testability. SSH commands include timeouts, retries, and error handling. Output files travel back to Mac via SMB.

**Tech Stack:** Bash 3.2+ (macOS), Python 3.12, SSH, SMB, nvidia-smi, Tailscale networking

**Prerequisites:**
- Tailscale connected between Mac (`shockang`) and Windows (`100.69.202.122`)
- SSH key `~/.ssh/id_ed25519_win` set up for Windows machine
- Windows has `acestep_generate.py` at `C:/Users/shockang/` (or `ACE_SCRIPT_DIR`)
- Windows has SMB share configured at `share` name
- `shellcheck` available on Mac (`brew install shellcheck`)

---

## File Structure

```
scripts/
├── config.sh                    # Shared config: SSH params, SMB paths, logging, retry helper
├── mount_windows_smb.sh         # SMB mount/unmount/check operations
├── run_ace_step.sh              # ACE-Step generation via SSH with timeout
├── check_windows_gpu.py         # GPU status checker with structured output
tests/
├── test_check_gpu.py            # Unit tests for GPU checker (mocked SSH)
docs/
├── MUSIC_ENGINE_VALIDATION.md   # Validation procedures and success criteria
```

---

### Task 1: Shared Shell Configuration

**Files:**
- Create: `scripts/config.sh`

- [ ] **Step 1: Create scripts directory**

```bash
mkdir -p scripts
```

- [ ] **Step 2: Write scripts/config.sh**

```bash
cat > scripts/config.sh << 'CONFIG_EOF'
#!/usr/bin/env bash
# config.sh — Shared configuration for Windows GPU operations
# Source this file: source "$(dirname "$0")/config.sh"

set -euo pipefail

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
        -o StrictHostKeyChecking=accept-new \
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
CONFIG_EOF
```

- [ ] **Step 3: Verify syntax**

Run: `bash -n scripts/config.sh && echo "OK"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add scripts/config.sh
git commit -m "feat: add shared shell config for Windows GPU operations"
```

---

### Task 2: SMB Mount Script

**Files:**
- Create: `scripts/mount_windows_smb.sh`

- [ ] **Step 1: Write scripts/mount_windows_smb.sh**

```bash
cat > scripts/mount_windows_smb.sh << 'SMB_EOF'
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
    mount | grep -q " ${MOUNT_POINT} "
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
SMB_EOF
chmod +x scripts/mount_windows_smb.sh
```

- [ ] **Step 2: Verify syntax and permissions**

Run: `bash -n scripts/mount_windows_smb.sh && echo "Syntax OK"`
Expected: `Syntax OK`

Run: `test -x scripts/mount_windows_smb.sh && echo "Executable OK"`
Expected: `Executable OK`

- [ ] **Step 3: Run shellcheck (if available)**

Run: `shellcheck scripts/mount_windows_smb.sh || true`

Review any warnings. Expected: no errors (warnings about `sudo` are acceptable).

- [ ] **Step 4: Commit**

```bash
git add scripts/mount_windows_smb.sh
git commit -m "feat: add SMB mount script for Windows GPU share"
```

---

### Task 3: GPU Checker — Write Failing Tests

**Files:**
- Create: `tests/test_check_gpu.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for scripts/check_windows_gpu.py — GPU status checker.

Tests mock SSH subprocess calls to verify parsing and logic.
"""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts/ to path so we can import check_windows_gpu as a module
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from check_windows_gpu import GPUStatus, check_gpu, parse_nvidia_smi


class TestParseNvidiaSmi:
    """Test nvidia-smi CSV output parsing."""

    def test_parse_rtx_3090ti_idle(self):
        output = "NVIDIA GeForce RTX 3090 Ti, 24576, 2048, 22528, 2"
        status = parse_nvidia_smi(output)
        assert status.name == "NVIDIA GeForce RTX 3090 Ti"
        assert status.vram_total_mb == 24576
        assert status.vram_used_mb == 2048
        assert status.vram_free_mb == 22528
        assert status.utilization_pct == 2

    def test_parse_rtx_3090ti_busy(self):
        output = "NVIDIA GeForce RTX 3090 Ti, 24576, 22528, 2048, 97"
        status = parse_nvidia_smi(output)
        assert status.vram_used_mb == 22528
        assert status.vram_free_mb == 2048
        assert status.utilization_pct == 97

    def test_parse_raises_on_bad_format(self):
        with pytest.raises(ValueError, match="Unexpected nvidia-smi output"):
            parse_nvidia_smi("not enough fields")

    def test_parse_raises_on_empty(self):
        with pytest.raises(ValueError):
            parse_nvidia_smi("")


class TestGPUStatus:
    """Test GPUStatus data class and derived properties."""

    def test_vram_conversions(self):
        status = GPUStatus(
            name="RTX 3090 Ti",
            vram_total_mb=24576,
            vram_used_mb=8192,
            vram_free_mb=16384,
            utilization_pct=15,
        )
        assert status.vram_used_gb == pytest.approx(8.0)
        assert status.vram_free_gb == pytest.approx(16.0)

    def test_can_generate_when_under_threshold(self):
        status = GPUStatus(
            name="RTX 3090 Ti",
            vram_total_mb=24576,
            vram_used_mb=8192,
            vram_free_mb=16384,
            utilization_pct=15,
        )
        assert status.can_generate is True

    def test_cannot_generate_when_over_threshold(self):
        status = GPUStatus(
            name="RTX 3090 Ti",
            vram_total_mb=24576,
            vram_used_mb=22528,
            vram_free_mb=2048,
            utilization_pct=95,
        )
        assert status.can_generate is False

    def test_can_generate_at_boundary(self):
        """Exactly 20 GB used should still allow generation (< not <=)."""
        status = GPUStatus(
            name="RTX 3090 Ti",
            vram_total_mb=24576,
            vram_used_mb=20480,  # exactly 20 GB
            vram_free_mb=4096,
            utilization_pct=50,
        )
        assert status.can_generate is True


class TestCheckGpu:
    """Test the SSH-based GPU check with mocked subprocess."""

    @patch("check_windows_gpu.subprocess.run")
    def test_check_gpu_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="NVIDIA GeForce RTX 3090 Ti, 24576, 4096, 20480, 5\n",
            stderr="",
        )
        status = check_gpu()
        assert isinstance(status, GPUStatus)
        assert status.name == "NVIDIA GeForce RTX 3090 Ti"
        assert status.vram_used_mb == 4096
        assert status.can_generate is True

    @patch("check_windows_gpu.subprocess.run")
    def test_check_gpu_ssh_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=255,
            stdout="",
            stderr="Connection refused",
        )
        with pytest.raises(RuntimeError, match="SSH command failed"):
            check_gpu()

    @patch("check_windows_gpu.subprocess.run")
    def test_check_gpu_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=30)
        with pytest.raises(subprocess.TimeoutExpired):
            check_gpu()

    @patch("check_windows_gpu.subprocess.run")
    def test_check_gpu_uses_correct_ssh_args(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="RTX 3090 Ti, 24576, 4096, 20480, 5\n",
            stderr="",
        )
        check_gpu()

        call_args = mock_run.call_args
        cmd = call_args[0][0] if call_args[0] else call_args[1].get("args", [])
        assert cmd[0] == "ssh"
        assert "-i" in cmd
        assert "shockang@100.69.202.122" in cmd
        assert "nvidia-smi" in " ".join(cmd)
```

- [ ] **Step 2: Run tests to verify they fail (module not found)**

Run: `cd /Users/shockang/novel/ace-music && python -m pytest tests/test_check_gpu.py -v 2>&1 | head -20`
Expected: `ModuleNotFoundError: No module named 'check_windows_gpu'` (confirming the import fails)

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_check_gpu.py
git commit -m "test: add GPU checker tests (red — implementation pending)"
```

---

### Task 4: GPU Checker — Implement to Pass Tests

**Files:**
- Create: `scripts/check_windows_gpu.py`

- [ ] **Step 1: Write scripts/check_windows_gpu.py**

```python
#!/usr/bin/env python3
"""Check Windows GPU status via SSH.

Queries nvidia-smi on the remote Windows GPU machine and reports
VRAM usage, utilization, and whether the GPU is available for
music generation.

Usage:
    python scripts/check_windows_gpu.py              # human-readable output
    python scripts/check_windows_gpu.py --json        # JSON output
    python scripts/check_windows_gpu.py --threshold 15  # custom threshold

Exit codes:
    0 — GPU ready for generation
    1 — GPU busy (VRAM above threshold)
    2 — Error (SSH failure, parse error, etc.)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass

# --- Configuration (override via environment) ---
import os

WINDOWS_HOST = os.environ.get("ACE_WINDOWS_HOST", "100.69.202.122")
WINDOWS_USER = os.environ.get("ACE_WINDOWS_USER", "shockang")
SSH_KEY = os.environ.get("ACE_SSH_KEY", "~/.ssh/id_ed25519_win")
SSH_PORT = int(os.environ.get("ACE_SSH_PORT", "22"))
VRAM_THRESHOLD_GB = float(os.environ.get("ACE_GPU_THRESHOLD", "20"))

NVIDIA_SMI_QUERY = (
    "nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,"
    "utilization.gpu --format=csv,noheader,nounits"
)


@dataclass
class GPUStatus:
    """Parsed GPU status from nvidia-smi."""

    name: str
    vram_total_mb: int
    vram_used_mb: int
    vram_free_mb: int
    utilization_pct: int

    @property
    def vram_used_gb(self) -> float:
        return self.vram_used_mb / 1024

    @property
    def vram_free_gb(self) -> float:
        return self.vram_free_mb / 1024

    @property
    def can_generate(self) -> bool:
        return self.vram_used_gb < VRAM_THRESHOLD_GB


def ssh_run(command: str, timeout: int = 30) -> str:
    """Run a command on the Windows GPU machine via SSH.

    Returns stdout on success. Raises RuntimeError on non-zero exit,
    subprocess.TimeoutExpired on timeout.
    """
    ssh_key = os.path.expanduser(SSH_KEY)
    result = subprocess.run(
        [
            "ssh",
            "-i", ssh_key,
            "-o", "ConnectTimeout=10",
            "-o", "StrictHostKeyChecking=accept-new",
            "-p", str(SSH_PORT),
            f"{WINDOWS_USER}@{WINDOWS_HOST}",
            command,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"SSH command failed: {result.stderr.strip()}")
    return result.stdout


def parse_nvidia_smi(output: str) -> GPUStatus:
    """Parse nvidia-smi CSV output into GPUStatus.

    Expected format: "GPU Name, total_mb, used_mb, free_mb, util_pct"
    """
    parts = [p.strip() for p in output.strip().split(",")]
    if len(parts) != 5:
        raise ValueError(f"Unexpected nvidia-smi output format: {output!r}")

    return GPUStatus(
        name=parts[0],
        vram_total_mb=int(parts[1]),
        vram_used_mb=int(parts[2]),
        vram_free_mb=int(parts[3]),
        utilization_pct=int(parts[4]),
    )


def check_gpu() -> GPUStatus:
    """Check GPU status on the remote Windows machine.

    Queries nvidia-smi via SSH and returns parsed status.
    Raises on SSH failure or parse errors.
    """
    output = ssh_run(NVIDIA_SMI_QUERY)
    return parse_nvidia_smi(output)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check Windows GPU status via SSH",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=VRAM_THRESHOLD_GB,
        help=f"VRAM used threshold in GB (default: {VRAM_THRESHOLD_GB})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output as JSON",
    )
    args = parser.parse_args()

    try:
        status = check_gpu()

        if args.json_output:
            print(json.dumps({
                "name": status.name,
                "vram_total_gb": round(status.vram_total_mb / 1024, 1),
                "vram_used_gb": round(status.vram_used_gb, 1),
                "vram_free_gb": round(status.vram_free_gb, 1),
                "utilization_pct": status.utilization_pct,
                "can_generate": status.vram_used_gb < args.threshold,
            }, indent=2))
        else:
            total_gb = status.vram_total_mb / 1024
            print(f"GPU: {status.name}")
            print(
                f"VRAM: {status.vram_used_mb}/{status.vram_total_mb} MB "
                f"({status.vram_used_gb:.1f}/{total_gb:.1f} GB)"
            )
            print(f"Utilization: {status.utilization_pct}%")

            if status.vram_used_gb < args.threshold:
                print(
                    f"Status: READY "
                    f"({status.vram_used_gb:.1f} GB used, "
                    f"threshold {args.threshold} GB)"
                )
            else:
                print(
                    f"Status: BUSY "
                    f"({status.vram_used_gb:.1f} GB used, "
                    f"threshold {args.threshold} GB)"
                )
                print(
                    "Suggestion: Wait for GPU to free, or kill GPU processes:"
                )
                print(
                    f"  ssh -i {SSH_KEY} {WINDOWS_USER}@{WINDOWS_HOST} "
                    f"'nvidia-smi --query-compute-apps=pid --format=csv,noheader'"
                )

        sys.exit(0 if status.vram_used_gb < args.threshold else 1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd /Users/shockang/novel/ace-music && python -m pytest tests/test_check_gpu.py -v`

Expected output:

```
tests/test_check_gpu.py::TestParseNvidiaSmi::test_parse_rtx_3090ti_idle PASSED
tests/test_check_gpu.py::TestParseNvidiaSmi::test_parse_rtx_3090ti_busy PASSED
tests/test_check_gpu.py::TestParseNvidiaSmi::test_parse_raises_on_bad_format PASSED
tests/test_check_gpu.py::TestParseNvidiaSmi::test_parse_raises_on_empty PASSED
tests/test_check_gpu.py::TestGPUStatus::test_vram_conversions PASSED
tests/test_check_gpu.py::TestGPUStatus::test_can_generate_when_under_threshold PASSED
tests/test_check_gpu.py::TestGPUStatus::test_cannot_generate_when_over_threshold PASSED
tests/test_check_gpu.py::TestGPUStatus::test_can_generate_at_boundary PASSED
tests/test_check_gpu.py::TestCheckGpu::test_check_gpu_success PASSED
tests/test_check_gpu.py::TestCheckGpu::test_check_gpu_ssh_failure PASSED
tests/test_check_gpu.py::TestCheckGpu::test_check_gpu_timeout PASSED
tests/test_check_gpu.py::TestCheckGpu::test_check_gpu_uses_correct_ssh_args PASSED
12 passed
```

- [ ] **Step 3: Make script executable**

```bash
chmod +x scripts/check_windows_gpu.py
```

- [ ] **Step 4: Verify existing tests still pass**

Run: `cd /Users/shockang/novel/ace-music && python -m pytest -v --tb=short`
Expected: all tests pass (existing + new)

- [ ] **Step 5: Commit**

```bash
git add scripts/check_windows_gpu.py
git commit -m "feat: add Windows GPU status checker with SSH and nvidia-smi parsing"
```

---

### Task 5: ACE-Step Generation Runner Script

**Files:**
- Create: `scripts/run_ace_step.sh`

- [ ] **Step 1: Write scripts/run_ace_step.sh**

```bash
cat > scripts/run_ace_step.sh << 'RUNNER_EOF'
#!/usr/bin/env bash
# run_ace_step.sh — Generate music via ACE-Step on Windows GPU
#
# Usage:
#   ./scripts/run_ace_step.sh --test
#   ./scripts/run_ace_step.sh --prompt "Ambient electronic, chill" --duration 30
#   ./scripts/run_ace_step.sh --prompt "Piano ballad, sad" --duration 60 --steps 40

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

# --- Defaults ---
PROMPT=""
DURATION=30
STEPS=20
TEST_MODE=false
TEST_DURATION=10
TIMEOUT="$DEFAULT_TIMEOUT"
SKIP_GPU_CHECK=false
SKIP_SMB_CHECK=false
CPU_OFFLOAD=true

# --- Usage ---
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Generate music using ACE-Step on Windows GPU via SSH.

Options:
  --prompt TEXT          Music description (required unless --test)
  --duration SECS        Duration in seconds (default: 30, range: 5-240)
  --steps N              Diffusion steps (default: 20, range: 1-200)
  --test [SECS]          Quick test mode (default: 10s)
  --timeout SECS         SSH timeout in seconds (default: 300)
  --no-cpu-offload       Disable CPU offload
  --skip-gpu-check       Skip GPU status check
  --skip-smb-check       Skip SMB mount check
  -h, --help             Show this help

Examples:
  $(basename "$0") --test
  $(basename "$0") --prompt "电子氛围音乐，舒缓节奏" --duration 30
  $(basename "$0") --prompt "Jazz piano, upbeat" --duration 60 --steps 40
EOF
    exit 0
}

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --prompt)         PROMPT="$2"; shift 2 ;;
        --duration)       DURATION="$2"; shift 2 ;;
        --steps)          STEPS="$2"; shift 2 ;;
        --test)
            TEST_MODE=true
            if [[ "${2:-}" =~ ^[0-9]+$ ]]; then
                TEST_DURATION="$2"
                shift 2
            else
                shift
            fi
            ;;
        --timeout)        TIMEOUT="$2"; shift 2 ;;
        --no-cpu-offload) CPU_OFFLOAD=false; shift ;;
        --skip-gpu-check) SKIP_GPU_CHECK=true; shift ;;
        --skip-smb-check) SKIP_SMB_CHECK=true; shift ;;
        -h|--help)        usage ;;
        *)                log_error "Unknown option: $1"; exit 1 ;;
    esac
done

# --- Apply test mode overrides ---
if [[ "$TEST_MODE" == "true" ]]; then
    PROMPT="test tone, ambient electronic, short"
    DURATION="$TEST_DURATION"
    STEPS=10
fi

# --- Validate ---
if [[ -z "$PROMPT" ]]; then
    log_error "--prompt is required (or use --test for quick test)"
    exit 1
fi

if [[ "$DURATION" -lt 5 || "$DURATION" -gt 240 ]]; then
    log_error "Duration must be 5-240 seconds, got $DURATION"
    exit 1
fi

if [[ "$STEPS" -lt 1 || "$STEPS" -gt 200 ]]; then
    log_error "Steps must be 1-200, got $STEPS"
    exit 1
fi

# --- Check SMB mount ---
if [[ "$SKIP_SMB_CHECK" == "false" ]]; then
    log_info "Checking SMB share..."
    if ! "$SCRIPT_DIR/mount_windows_smb.sh" check; then
        log_info "Mounting SMB share..."
        if ! "$SCRIPT_DIR/mount_windows_smb.sh" mount; then
            log_error "Cannot mount SMB share. Aborting."
            exit 1
        fi
    fi
fi

# --- Check GPU ---
if [[ "$SKIP_GPU_CHECK" == "false" ]]; then
    log_info "Checking GPU status..."
    if ! python3 "$SCRIPT_DIR/check_windows_gpu.py"; then
        log_error "GPU not ready (VRAM above threshold)."
        log_error "Use --skip-gpu-check to override, or wait for GPU to free."
        exit 1
    fi
fi

# --- Build generation command ---
TIMESTAMP=$(date +%s)
OUTPUT_FILE="${ACE_OUTPUT_DIR}/music_${TIMESTAMP}.wav"

OFFLOAD_FLAG=""
if [[ "$CPU_OFFLOAD" == "true" ]]; then
    OFFLOAD_FLAG="--cpu_offload"
fi

# Escape single quotes in prompt for SSH
ESCAPED_PROMPT="${PROMPT//\'/\'\\\'\'}"

GENERATE_CMD="cd ${ACE_SCRIPT_DIR} && python acestep_generate.py --prompt '${ESCAPED_PROMPT}' --duration ${DURATION} --output ${OUTPUT_FILE} --steps ${STEPS} ${OFFLOAD_FLAG}"

# --- Execute ---
log_info "Generating ${DURATION}s of music..."
log_info "  Prompt: ${PROMPT}"
log_info "  Steps: ${STEPS}"
log_info "  CPU offload: ${CPU_OFFLOAD}"
log_info "  Timeout: ${TIMEOUT}s"
log_info "  Remote output: ${OUTPUT_FILE}"

START_TIME=$(date +%s)

if ! timeout "$TIMEOUT" ssh_cmd "$GENERATE_CMD"; then
    EXIT_CODE=$?
    if [[ $EXIT_CODE -eq 124 ]]; then
        log_error "Generation timed out after ${TIMEOUT}s"
    else
        log_error "Generation failed with exit code ${EXIT_CODE}"
    fi
    exit 1
fi

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
log_info "Generation completed in ${ELAPSED}s"

# --- Verify output ---
SMB_FILE="${MOUNT_POINT}/music_${TIMESTAMP}.wav"

if [[ -f "$SMB_FILE" ]]; then
    FILE_SIZE=$(stat -f%z "$SMB_FILE" 2>/dev/null || stat -c%s "$SMB_FILE" 2>/dev/null || echo "unknown")
    log_info "Output file: ${SMB_FILE}"
    log_info "File size: ${FILE_SIZE} bytes"

    # Basic validation: WAV should be > 1KB
    if [[ "$FILE_SIZE" -gt 1024 ]]; then
        log_info "SUCCESS — music file looks valid"
    else
        log_warn "File is very small (${FILE_SIZE} bytes), generation may have failed"
    fi
else
    log_warn "Output file not found at ${SMB_FILE}"
    log_warn "It may still be writing. Check with:"
    log_warn "  ls -la ${MOUNT_POINT}/music_*.wav"
fi
RUNNER_EOF
chmod +x scripts/run_ace_step.sh
```

- [ ] **Step 2: Verify syntax**

Run: `bash -n scripts/run_ace_step.sh && echo "Syntax OK"`
Expected: `Syntax OK`

- [ ] **Step 3: Run shellcheck**

Run: `shellcheck scripts/run_ace_step.sh || true`
Review warnings. Note: `source` sourcing and `set -e` are fine; address any real issues.

- [ ] **Step 4: Verify help output**

Run: `scripts/run_ace_step.sh --help`
Expected: usage text showing options and examples.

- [ ] **Step 5: Verify validation catches bad input**

Run: `scripts/run_ace_step.sh --prompt "test" --duration 300 2>&1; echo "Exit: $?"`
Expected: `[ERROR] Duration must be 5-240 seconds, got 300` and exit code 1.

Run: `scripts/run_ace_step.sh 2>&1; echo "Exit: $?"`
Expected: `[ERROR] --prompt is required` and exit code 1.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_ace_step.sh
git commit -m "feat: add ACE-Step generation runner with SSH, GPU check, and timeout"
```

---

### Task 6: Validation Documentation

**Files:**
- Create: `docs/MUSIC_ENGINE_VALIDATION.md`

- [ ] **Step 1: Create docs directory and write validation document**

```bash
mkdir -p docs
```

Write `docs/MUSIC_ENGINE_VALIDATION.md`:

```markdown
# Music Engine Validation Guide

## Overview

This document describes how to validate the ACE-Step music generation pipeline
between a Mac (client) and a Windows GPU machine (RTX 3090 Ti) connected via
Tailscale. The pipeline uses SSH for command execution and SMB for file transfer.

## Prerequisites

### Mac Side
- [ ] Tailscale installed and connected
- [ ] SSH key at `~/.ssh/id_ed25519_win` (or set `ACE_SSH_KEY`)
- [ ] `shellcheck` for script validation (`brew install shellcheck`)
- [ ] Python 3.12+

### Windows Side
- [ ] Tailscale installed and connected (IP: `100.69.202.122`)
- [ ] OpenSSH Server running
- [ ] NVIDIA driver + CUDA installed
- [ ] `acestep_generate.py` at `C:/Users/shockang/`
- [ ] SMB share named `share` pointing to `C:/share`

## Step 1: Connectivity Check

```bash
# Test SSH connection
ssh -i ~/.ssh/id_ed25519_win shockang@100.69.202.122 "echo connected"

# Test Tailscale ping
tailscale ping 100.69.202.122
```

Expected: `connected` response, low latency ping.

## Step 2: SMB Mount Check

```bash
# Check current status
./scripts/mount_windows_smb.sh status

# Mount if needed
./scripts/mount_windows_smb.sh mount

# Verify
ls /Volumes/share/
```

Expected: SMB share mounted and readable.

## Step 3: GPU Status Check

```bash
# Human-readable output
python3 scripts/check_windows_gpu.py

# JSON output (for scripts)
python3 scripts/check_windows_gpu.py --json

# Custom threshold
python3 scripts/check_windows_gpu.py --threshold 15
```

Expected:
- GPU name: `NVIDIA GeForce RTX 3090 Ti`
- Status: `READY` (VRAM used < 20 GB)
- Exit code: 0

## Step 4: Quick Test Generation

```bash
# 10-second test
./scripts/run_ace_step.sh --test

# Custom test duration
./scripts/run_ace_step.sh --test 15
```

Expected:
- Generation completes in under 2 minutes
- WAV file appears at `/Volumes/share/music_*.wav`
- File size > 1 KB

## Step 5: Full Generation Test

```bash
./scripts/run_ace_step.sh \
  --prompt "电子氛围音乐，舒缓节奏" \
  --duration 30
```

Expected:
- Generation completes in under 5 minutes
- Output: 30 +/- 5 second WAV file
- Sample rate: 48000 Hz

## Step 6: Verify Output

```bash
# Check file exists and has content
ls -la /Volumes/share/music_*.wav

# Verify format
file /Volumes/share/music_*.wav

# Check duration (requires ffprobe)
ffprobe /Volumes/share/music_*.wav 2>&1 | grep Duration
```

Expected:
- `file` output: `RIFF (little-endian) data, WAVE audio`
- Duration: approximately 30 seconds

## Success Criteria

| Criterion | Target |
|-----------|--------|
| SMB share accessible | `/Volumes/share` mounted |
| GPU VRAM available | < 20 GB used |
| Test generation (10s) | < 2 minutes total |
| Full generation (30s) | < 5 minutes total |
| Output duration | 30 +/- 5 seconds |
| Output format | WAV, 48000 Hz |
| File transfer | Appears via SMB |

## Troubleshooting

### SSH Connection Refused
```bash
# Check Tailscale status
tailscale status

# Verify Windows SSH server is running
# On Windows: Get-Service sshd
```

### SMB Mount Fails
```bash
# Try manual mount
mount_smbfs //shockang@100.69.202.122/share /Volumes/share

# Check Windows firewall allows SMB (port 445)
```

### GPU Not Ready
```bash
# Check what is using GPU
python3 scripts/check_windows_gpu.py --json

# On Windows, list GPU processes:
# nvidia-smi --query-compute-apps=pid,name,used_memory --format=csv
```

### Generation Timeout
```bash
# Increase timeout
./scripts/run_ace_step.sh --prompt "..." --duration 30 --timeout 600

# Skip GPU check if false positive
./scripts/run_ace_step.sh --prompt "..." --duration 30 --skip-gpu-check
```

### File Not Found After Generation
```bash
# The file may still be writing. Wait and check:
ls -la /Volumes/share/music_*.wav

# Check Windows output directly:
ssh -i ~/.ssh/id_ed25519_win shockang@100.69.202.122 "dir C:\\share\\music_*.wav"
```

## Environment Variables

All scripts respect these environment variables for configuration:

| Variable | Default | Description |
|----------|---------|-------------|
| `ACE_WINDOWS_HOST` | `100.69.202.122` | Windows GPU machine IP |
| `ACE_WINDOWS_USER` | `shockang` | SSH username |
| `ACE_SSH_KEY` | `~/.ssh/id_ed25519_win` | SSH private key path |
| `ACE_SSH_PORT` | `22` | SSH port |
| `ACE_SMB_SHARE` | `share` | SMB share name |
| `ACE_MOUNT_POINT` | `/Volumes/share` | Local mount point |
| `ACE_SCRIPT_DIR` | `C:/Users/shockang` | Windows ACE-Step script dir |
| `ACE_OUTPUT_DIR` | `C:/share` | Windows output directory |
| `ACE_TIMEOUT` | `300` | Default SSH timeout (seconds) |
| `ACE_GPU_THRESHOLD` | `20` | VRAM threshold (GB) |
```

- [ ] **Step 2: Verify docs render correctly**

Run: `head -20 docs/MUSIC_ENGINE_VALIDATION.md`
Expected: document header and overview visible.

- [ ] **Step 3: Commit**

```bash
git add docs/MUSIC_ENGINE_VALIDATION.md
git commit -m "docs: add music engine validation guide"
```

---

### Task 7: Final Verification — All Tests Pass

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/shockang/novel/ace-music && python -m pytest -v --tb=short`
Expected: all tests pass (existing pipeline tests + new GPU checker tests).

- [ ] **Step 2: Lint all Python files**

Run: `cd /Users/shockang/novel/ace-music && ruff check src/ tests/ scripts/check_windows_gpu.py`
Expected: no errors.

- [ ] **Step 3: Shellcheck all shell scripts**

Run: `shellcheck scripts/config.sh scripts/mount_windows_smb.sh scripts/run_ace_step.sh || true`
Expected: no errors (warnings acceptable).

- [ ] **Step 4: Verify all deliverables exist**

Run:
```bash
test -f scripts/config.sh && echo "config.sh OK" || echo "MISSING"
test -f scripts/mount_windows_smb.sh && echo "mount_windows_smb.sh OK" || echo "MISSING"
test -x scripts/mount_windows_smb.sh && echo "mount_windows_smb.sh executable" || echo "NOT EXECUTABLE"
test -f scripts/check_windows_gpu.py && echo "check_windows_gpu.py OK" || echo "MISSING"
test -x scripts/check_windows_gpu.py && echo "check_windows_gpu.py executable" || echo "NOT EXECUTABLE"
test -f scripts/run_ace_step.sh && echo "run_ace_step.sh OK" || echo "MISSING"
test -x scripts/run_ace_step.sh && echo "run_ace_step.sh executable" || echo "NOT EXECUTABLE"
test -f docs/MUSIC_ENGINE_VALIDATION.md && echo "MUSIC_ENGINE_VALIDATION.md OK" || echo "MISSING"
test -f tests/test_check_gpu.py && echo "test_check_gpu.py OK" || echo "MISSING"
```

Expected: all files present and executables marked.

- [ ] **Step 5: Commit any remaining fixes**

```bash
git add -A
git status  # verify nothing unexpected
# Only commit if there are actual changes
git diff --cached --quiet || git commit -m "chore: final verification cleanup"
```

---

## Spec Coverage Check

| Spec Requirement | Covered By |
|---|---|
| SMB mount script with check/mount/unmount | Task 2: `scripts/mount_windows_smb.sh` |
| SMB authentication support | Task 2: uses `//user@host/share` format |
| SMB timeout and retry | Task 2: retries with mount_smbfs then open fallback |
| ACE-Step complete SSH invocation | Task 5: `scripts/run_ace_step.sh` |
| GPU state check (VRAM) | Task 3-4: `scripts/check_windows_gpu.py` |
| Generation monitoring with timeout | Task 5: `timeout` wrapper + elapsed time reporting |
| GPU cleanup suggestion | Task 4: prints nvidia-smi query command |
| Validation document | Task 6: `docs/MUSIC_ENGINE_VALIDATION.md` |
| Environment variable configuration | Task 1: `scripts/config.sh` + Task 4 env vars |

## Placeholder Scan

No TBD, TODO, "implement later", "add error handling", or placeholder patterns found. All steps contain complete code.
