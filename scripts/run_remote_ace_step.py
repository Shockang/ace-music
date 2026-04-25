#!/usr/bin/env python3
"""Run ACE-Step generation on a remote Windows GPU host via SSH.

This script is intentionally stdlib-only. It launches the long-running Windows
process detached from the SSH session, polls for completion, then fetches the
WAV via SMB if mounted or SCP as a non-interactive fallback.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Any

WINDOWS_HOST = os.environ.get("ACE_WINDOWS_HOST", "100.69.202.122")
WINDOWS_USER = os.environ.get("ACE_WINDOWS_USER", "shockang")
SSH_KEY = os.path.expanduser(os.environ.get("ACE_SSH_KEY", "~/.ssh/id_ed25519_win"))
SSH_PORT = os.environ.get("ACE_SSH_PORT", "22")
MOUNT_POINT = os.environ.get("ACE_MOUNT_POINT", "/Volumes/share")
ACE_SCRIPT_DIR = os.environ.get("ACE_SCRIPT_DIR", "C:/Users/shockang")
ACE_OUTPUT_DIR = os.environ.get("ACE_OUTPUT_DIR", "C:/share")
DEFAULT_TIMEOUT = int(os.environ.get("ACE_TIMEOUT", "300"))
LOCAL_OUTPUT_DIR = os.environ.get("ACE_LOCAL_OUTPUT_DIR", "./output/remote")
SCRIPT_DIR = Path(__file__).resolve().parent


class RemoteRunError(Exception):
    """Remote generation failed in a diagnosable way."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def log(level: str, message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] [{level:<5}] {message}", file=sys.stderr)


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode("ascii")


def cmd_quote(value: str) -> str:
    return '"' + value.replace('"', '\\"') + '"'


def ssh_run(
    command: str, timeout: float = 30, check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [
            "ssh",
            "-i",
            SSH_KEY,
            "-o",
            "ConnectTimeout=10",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=3",
            "-p",
            str(SSH_PORT),
            f"{WINDOWS_USER}@{WINDOWS_HOST}",
            command,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if check and result.returncode != 0:
        detail = "\n".join(
            part for part in [result.stdout.strip(), result.stderr.strip()] if part
        )
        raise RemoteRunError(
            detail or f"SSH command failed with {result.returncode}",
            result.returncode,
        )
    return result


def remote_python(code: str, *args: str, timeout: float = 30) -> str:
    bootstrap = "import base64,sys;exec(base64.b64decode(sys.argv[1]).decode())"
    command = " ".join(
        [
            "cd",
            "/d",
            cmd_quote(ACE_SCRIPT_DIR),
            "&&",
            "python",
            "-c",
            cmd_quote(bootstrap),
            b64(code),
            *(cmd_quote(arg) for arg in args),
        ]
    )
    return ssh_run(command, timeout=timeout).stdout.strip()


def run_gpu_check(skip: bool) -> None:
    if skip:
        log("INFO", "Skipping GPU status check")
        return
    log("INFO", "Checking GPU status...")
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "check_windows_gpu.py")],
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
    )
    if result.returncode != 0:
        raise RemoteRunError("GPU not ready; use --skip-gpu-check to override", result.returncode)


def is_mounted(path: str) -> bool:
    mount_point = Path(path)
    if not mount_point.exists():
        return False
    result = subprocess.run(["mount"], capture_output=True, text=True, check=False)
    return f" on {path} " in result.stdout


def choose_transfer(skip_smb_check: bool) -> str:
    if skip_smb_check:
        log("INFO", "SMB check skipped; using SCP fallback")
        return "scp"
    if is_mounted(MOUNT_POINT):
        log("INFO", f"SMB share is mounted at {MOUNT_POINT}")
        return "smb"
    log("WARN", f"SMB share is not mounted at {MOUNT_POINT}; using SCP fallback")
    return "scp"



def remote_log_tail(log_file: str) -> str:
    code = r'''
from pathlib import Path
import sys
path = Path(sys.argv[2])
print(path.read_text(encoding="utf-8", errors="replace")[-4000:] if path.exists() else "")
'''
    try:
        return remote_python(code, log_file, timeout=30)
    except Exception as exc:
        return f"<failed to read remote log: {exc}>"


def run_remote_generation_sync(
    prompt: str,
    duration: int,
    output_file: str,
    steps: int,
    log_file: str,
    cpu_offload: bool,
    timeout: int,
) -> None:
    code = r'''
import base64
import subprocess
import sys
import time

prompt = base64.b64decode(sys.argv[2]).decode()
duration, output_file, steps, log_file = sys.argv[3:7]
cpu_offload = sys.argv[7].lower() == "true"
timeout = float(sys.argv[8])
args = [
    sys.executable,
    "acestep_generate.py",
    "--prompt",
    prompt,
    "--duration",
    duration,
    "--output",
    output_file,
    "--steps",
    steps,
]
if cpu_offload:
    args.append("--cpu_offload")
started = time.time()
try:
    result = subprocess.run(
        args,
        cwd="C:/Users/shockang",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    output = result.stdout
except subprocess.TimeoutExpired as exc:
    output = exc.stdout if isinstance(exc.stdout, str) else ""
    result = subprocess.CompletedProcess(args, 124, output)
with open(log_file, "w", encoding="utf-8", errors="replace") as log:
    log.write(output)
    trailer = f"\n[ace-music] elapsed={time.time() - started:.1f}s "
    trailer += f"returncode={result.returncode}\n"
    log.write(trailer)
print(output[-4000:])
raise SystemExit(result.returncode)
'''
    try:
        remote_python(
            code,
            b64(prompt),
            str(duration),
            output_file,
            str(steps),
            log_file,
            str(cpu_offload).lower(),
            str(timeout),
            timeout=timeout + 60,
        )
    except RemoteRunError as exc:
        tail = remote_log_tail(log_file)
        if tail:
            log("WARN", f"Remote log tail:\n{tail}")
        if exc.exit_code == 124:
                raise RemoteRunError(
                f"Generation timed out after {timeout}s", 124
            ) from exc
        raise RemoteRunError(f"Remote generation failed: {exc}", exc.exit_code) from exc


def fetch_output(remote_path: str, timestamp: int, transfer_mode: str) -> Path:
    if transfer_mode == "smb":
        local_path = Path(MOUNT_POINT) / f"music_{timestamp}.wav"
        if local_path.exists():
            return local_path
        log("WARN", f"SMB path missing after generation: {local_path}; falling back to SCP")

    output_dir = Path(LOCAL_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    local_path = output_dir / f"music_{timestamp}.wav"
    log("INFO", f"Fetching remote output via SCP -> {local_path}")
    result = subprocess.run(
        [
            "scp",
            "-i",
            SSH_KEY,
            "-o",
            "ConnectTimeout=10",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-P",
            str(SSH_PORT),
            f"{WINDOWS_USER}@{WINDOWS_HOST}:{remote_path}",
            str(local_path),
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if result.returncode != 0:
        raise RemoteRunError("Failed to fetch remote output via SCP", result.returncode)
    return local_path


def validate_wav(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RemoteRunError(f"Output file not found: {path}")
    size = path.stat().st_size
    if size <= 1024:
        raise RemoteRunError(f"Output file too small ({size} bytes)")
    try:
        with wave.open(str(path), "rb") as wav:
            frames = wav.getnframes()
            sample_rate = wav.getframerate()
            channels = wav.getnchannels()
            duration = frames / sample_rate if sample_rate else 0.0
    except wave.Error as exc:
        raise RemoteRunError(f"Output is not a valid WAV: {exc}") from exc
    return {
        "file_size_bytes": size,
        "format": "wav",
        "sample_rate": sample_rate,
        "channels": channels,
        "duration_seconds": round(duration, 2),
    }


def write_summary(path: str | None, summary: dict[str, Any]) -> None:
    if not path:
        return
    summary_path = Path(path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate music using ACE-Step on Windows GPU via SSH"
    )
    parser.add_argument("--prompt", help="Music description (required unless --test)")
    parser.add_argument("--duration", type=int, default=30, help="Duration seconds, 5-240")
    parser.add_argument("--steps", type=int, default=20, help="Diffusion steps, 1-200")
    parser.add_argument(
        "--test", nargs="?", const=10, type=int, help="Quick test mode duration"
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT, help="Generation timeout seconds"
    )
    parser.add_argument(
        "--cpu-offload",
        action="store_true",
        help="Pass --cpu_offload if remote script supports it",
    )
    parser.add_argument("--skip-gpu-check", action="store_true", help="Skip GPU status check")
    parser.add_argument(
        "--skip-smb-check", action="store_true", help="Skip SMB mount check and use SCP"
    )
    parser.add_argument("--summary-json", help="Write machine-readable run summary JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    prompt = args.prompt
    duration = args.duration
    steps = args.steps
    if args.test is not None:
        prompt = "test tone, ambient electronic, short"
        duration = args.test
        steps = 10
    if not prompt:
        raise SystemExit("--prompt is required (or use --test)")
    if duration < 5 or duration > 240:
        raise SystemExit("--duration must be 5-240 seconds")
    if steps < 1 or steps > 200:
        raise SystemExit("--steps must be 1-200")

    timestamp = int(time.time())
    remote_path = f"{ACE_OUTPUT_DIR}/music_{timestamp}.wav"
    remote_log = f"{ACE_OUTPUT_DIR}/music_{timestamp}.log"
    started = time.time()
    summary: dict[str, Any] = {
        "status": "failed",
        "remote_audio_path": remote_path,
        "remote_log_path": remote_log,
    }

    try:
        transfer_mode = choose_transfer(args.skip_smb_check)
        run_gpu_check(args.skip_gpu_check)
        log("INFO", f"Generating {duration}s of music...")
        log("INFO", f"  Prompt: {prompt}")
        log("INFO", f"  Steps: {steps}")
        log("INFO", f"  CPU offload: {args.cpu_offload}")
        log("INFO", f"  Timeout: {args.timeout}s")
        log("INFO", f"  Remote output: {remote_path}")
        log("INFO", f"  Remote log: {remote_log}")
        run_remote_generation_sync(
            prompt, duration, remote_path, steps, remote_log, args.cpu_offload, args.timeout
        )
        local_path = fetch_output(remote_path, timestamp, transfer_mode)
        validation = validate_wav(local_path)
        elapsed = int(time.time() - started)
        summary = {
            "status": "success",
            "elapsed_seconds": elapsed,
            "audio_path": str(local_path),
            "remote_audio_path": remote_path,
            "remote_log_path": remote_log,
            "transfer_mode": transfer_mode if Path(MOUNT_POINT).exists() else "scp",
            **validation,
        }
        log("INFO", f"Generation completed in {elapsed}s")
        log("INFO", f"Output file: {local_path}")
        log("INFO", f"File size: {validation['file_size_bytes']} bytes")
        log("INFO", "SUCCESS — music file looks valid")
        write_summary(args.summary_json, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except RemoteRunError as exc:
        elapsed = int(time.time() - started)
        summary.update(
            {
                "status": "failed",
                "exit_code": exc.exit_code,
                "error": str(exc),
                "elapsed_seconds": elapsed,
            }
        )
        write_summary(args.summary_json, summary)
        log("ERROR", str(exc))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
