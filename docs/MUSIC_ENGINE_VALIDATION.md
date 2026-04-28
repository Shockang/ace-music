# Music Engine Validation Guide

## Overview

This guide describes how to validate `ace-music` in public, reproducible environments. It focuses on three supported validation lanes:

- mock-mode smoke tests
- local ACE-Step validation
- MiniMax API validation

Use mock mode first. It is the fastest way to verify installation, CLI wiring, and output validation behavior.

## Validation Lanes

| Lane | Goal | Requirements |
| --- | --- | --- |
| Mock | verify CLI, output writing, and JSON summaries | Python only |
| Local ACE-Step | verify local GPU-backed generation | compatible GPU, model dependencies |
| MiniMax | verify cloud-backed generation | `MINIMAX_API_KEY` |

## 1. Mock Smoke Test

Run:

```bash
ace-music generate \
  --mock \
  --description "short ambient piano motif" \
  --duration 5 \
  --output-dir ./output \
  --summary-json ./output/mock-summary.json
```

Expected:

- command exits with code `0`
- a WAV file is written into `./output`
- `./output/mock-summary.json` contains a `status: success` payload

## 2. Local ACE-Step Validation

Install model extras:

```bash
pip install -e ".[dev,model]"
```

Run a short local generation:

```bash
ace-music generate \
  --description "warm ambient synth with gentle pulse" \
  --duration 10 \
  --output-dir ./output \
  --summary-json ./output/acestep-summary.json
```

Expected:

- command exits with code `0`
- generated audio is written into `./output`
- summary JSON contains `status: success`

If your environment cannot provide CUDA-backed ACE-Step generation yet, use `--mock` until the local model path is ready.

## 3. MiniMax Validation

Export the API key:

```bash
export MINIMAX_API_KEY="your-key"
```

Run a short cloud generation:

```bash
ace-music generate \
  --backend minimax \
  --description "cinematic ambient theme with soft percussion" \
  --duration 10 \
  --output-dir ./output \
  --summary-json ./output/minimax-summary.json
```

Expected:

- command exits with code `0`
- an audio file is written into `./output`
- summary JSON contains `status: success`

## 4. Validate Existing Audio

Run:

```bash
ace-music validate ./output/example.wav \
  --expected-sample-rate 48000 \
  --expected-duration 30 \
  --duration-tolerance 5
```

Expected:

- command exits with code `0` for valid audio
- output JSON includes `validation` details such as duration and sample rate checks

## 5. Output Checks

For generated or imported outputs, verify:

- file exists and is non-empty
- reported duration is within tolerance
- sample rate matches expectations
- summary JSON is written when `--summary-json` is passed

## Troubleshooting

### `ace-music` command not found

Activate the virtual environment and reinstall:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

### Local ACE-Step generation fails because CUDA is unavailable

Use mock mode first:

```bash
ace-music generate --mock --description "test" --duration 5
```

Then verify your local model and CUDA setup separately before retrying production generation.

### MiniMax generation fails with an API-key error

Confirm that `MINIMAX_API_KEY` is exported in the current shell:

```bash
echo "${MINIMAX_API_KEY:+set}"
```

### Output validation fails

Use the `validate` command to inspect duration and sample-rate mismatches, then compare the summary JSON against the file on disk.
