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
import os
import subprocess
import sys
from dataclasses import dataclass

# --- Configuration (override via environment) ---
WINDOWS_HOST = os.environ.get("ACE_WINDOWS_HOST", "100.69.202.122")
WINDOWS_USER = os.environ.get("ACE_WINDOWS_USER", "shockang")
SSH_KEY = os.environ.get("ACE_SSH_KEY", "~/.ssh/id_ed25519_win")
SSH_PORT = int(os.environ.get("ACE_SSH_PORT", "22"))
VRAM_THRESHOLD_GB = float(os.environ.get("ACE_GPU_THRESHOLD", "20"))

NVIDIA_SMI_QUERY = (
    "nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,"
    "utilization.gpu --format=csv,noheader,nounits"
)


@dataclass(frozen=True)
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
        return self.vram_used_gb <= VRAM_THRESHOLD_GB


def ssh_run(command: str, timeout: int = 30) -> str:
    """Run a command on the Windows GPU machine via SSH.

    WARNING: The command string is interpreted by the remote shell.
    Only pass trusted, hardcoded strings — never user-controlled input.

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
                "can_generate": status.vram_used_gb <= args.threshold,
            }, indent=2))
        else:
            total_gb = status.vram_total_mb / 1024
            print(f"GPU: {status.name}")
            print(
                f"VRAM: {status.vram_used_mb}/{status.vram_total_mb} MB "
                f"({status.vram_used_gb:.1f}/{total_gb:.1f} GB)"
            )
            print(f"Utilization: {status.utilization_pct}%")

            if status.vram_used_gb <= args.threshold:
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

        sys.exit(0 if status.vram_used_gb <= args.threshold else 1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
