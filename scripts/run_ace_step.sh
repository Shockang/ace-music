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

# --- Validate inputs ---
validate_number() {
    [[ "$1" =~ ^[0-9]+$ ]] || { log_error "$2 must be a positive integer, got: $1"; exit 1; }
}

if [[ -z "$PROMPT" ]]; then
    log_error "--prompt is required (or use --test for quick test)"
    exit 1
fi

validate_number "$DURATION" "--duration"
if [[ "$DURATION" -lt 5 || "$DURATION" -gt 240 ]]; then
    log_error "Duration must be 5-240 seconds, got $DURATION"
    exit 1
fi

validate_number "$STEPS" "--steps"
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

# Base64-encode prompt to eliminate shell injection risk.
# Base64 output is [A-Za-z0-9+/=] — no shell metacharacters.
# The prompt is passed via env var to remote Python, which decodes it
# and calls acestep_generate.py using subprocess (no shell interpretation).
PROMPT_B64=$(printf '%s' "$PROMPT" | base64)

OFFLOAD_ARG=""
if [[ "$CPU_OFFLOAD" == "true" ]]; then
    OFFLOAD_ARG=",'--cpu_offload'"
fi

GENERATE_CMD="cd ${ACE_SCRIPT_DIR} && ACE_PROMPT_B64='${PROMPT_B64}' python3 -c \"import base64,os,subprocess,sys;p=base64.b64decode(os.environ['ACE_PROMPT_B64']).decode();r=subprocess.run([sys.executable,'acestep_generate.py','--prompt',p,'--duration','${DURATION}','--output','${OUTPUT_FILE}','--steps','${STEPS}'${OFFLOAD_ARG}]);sys.exit(r.returncode)\""

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
