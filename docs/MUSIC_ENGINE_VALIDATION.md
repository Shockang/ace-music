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
