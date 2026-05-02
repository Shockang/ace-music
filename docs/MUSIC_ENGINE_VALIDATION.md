# Music Engine Validation Guide

## Overview

This guide describes how to validate `ace-music` in public, reproducible environments. It covers four supported validation lanes:

- mock-mode smoke tests
- local ACE-Step validation
- MiniMax API validation
- Stable Audio API validation

Use mock mode first. It is the fastest way to verify installation, CLI wiring, and output validation behavior.

## Validation Lanes

| Lane | Goal | Requirements |
| --- | --- | --- |
| Mock | verify CLI, output writing, and JSON summaries | Python only |
| Local ACE-Step | verify local GPU-backed generation | compatible GPU, model dependencies |
| MiniMax | verify cloud-backed generation | `MINIMAX_API_KEY` |
| Stable Audio | verify Stability AI generation | `STABILITY_API_KEY` |

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

### Mock Mode Pipeline Stages

In mock mode, the pipeline runs all stages with deterministic stubs:

1. **EmotionMapper**: maps the scene contract's mood and intensity to style tags, tempo preference, and mix parameters using the Russell Circumplex model.
2. **PostProcessor**: copies the input file unchanged, reports `target_lufs` (default -14.0) and `peak_db` (-1.0) in metadata.
3. **StableAudioGenerator**: not invoked in mock mode. Only exercised through the `stable_audio` backend path.

## 2. Local ACE-Step Validation

Install the optional GPU-oriented extras:

```bash
pip install -e ".[dev,model]"
```

These extras do not install the ACE-Step runtime itself. Treat ACE-Step as an external prerequisite that must already be available on the machine before attempting local backend validation.

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

If your environment cannot provide a configured ACE-Step runtime plus CUDA-backed execution yet, use `--mock` until the local model path is ready.

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

## 4. Stable Audio Validation

Export the Stability API key:

```bash
export STABILITY_API_KEY="your-key"
```

Run a generation with the Stable Audio backend:

```bash
ace-music generate \
  --backend stable_audio \
  --description "gentle ambient piano with reverb" \
  --duration 10 \
  --output-dir ./output \
  --summary-json ./output/stable-summary.json
```

Stable Audio only supports instrumental mode. The `--mode` flag defaults to `instrumental` for this backend. Duration must be between 5 and 180 seconds.

Expected:

- command exits with code `0`
- an MP3 file (default format) is written into `./output`
- summary JSON contains `status: success`

### Stable Audio Validation Checks

The generator validates:

- `STABILITY_API_KEY` is set or passed via config. Raises `ValueError` if missing.
- Duration is clamped to the 5-180 second range by the input schema (`ge=5.0, le=180.0`).
- Downloaded payload is a recognized audio format (checks for ID3, RIFF, or MPEG frame headers). Raises `GenerationFailedError` if the response is not audio.
- Job polling respects `poll_timeout_seconds` (default 600s). Raises `GenerationFailedError` on timeout.

## 5. Validate Existing Audio

Run against a generated WAV:

```bash
ace-music validate ./output/path-to-generated.wav \
  --expected-sample-rate 48000 \
  --expected-duration 5 \
  --duration-tolerance 5
```

Expected:

- command exits with code `0` for valid audio
- output JSON includes `validation` details such as duration and sample rate checks

## 6. Output Checks

For generated or imported outputs, verify:

- file exists and is non-empty
- reported duration is within tolerance
- sample rate matches expectations
- summary JSON is written when `--summary-json` is passed

For CI, the recommended sequence is:

1. install the package in editable mode
2. run Ruff
3. run pytest
4. run a mock generation smoke test
5. run `validate` against the generated WAV

## 7. Tool-Specific Validation

### EmotionMapper

Validates the deterministic mapping from scene contracts to audio parameters.

**What it checks:**

- `AudioSceneContract` fields (mood, intensity, valence, arousal, shot_count, dialogue_density) produce deterministic `MappedAudioParameters`.
- The Russell Circumplex model maps valence/arousal pairs to the correct quadrant tags and key suggestions (major/minor).
- Pace estimation handles arousal thresholds, shot count density, and circumplex tempo modifiers.
- Guidance scale is bounded between 8.0 and 20.0, and increases with intensity.
- Mix derivation adjusts `bgm_gain_db` based on `dialogue_density` and sets `sidechain_source` when TTS is present.
- Style tags are deduplicated and lowercased.
- `to_metadata()` returns a JSON-safe dictionary.

The EmotionMapper module is exercised indirectly through `test_style_planner.py` and `test_pipeline.py`, which cover the style resolution path where EmotionMapper is called internally.

### PostProcessor DSP

Validates audio post-processing: loudness normalization, format conversion, and DSP effects.

**What it checks:**

- Loudness targeting defaults to -14.0 LUFS (EBU R128). The `target_lufs` value can be overridden via `--target-lufs` or the scene contract's `mix.target_lufs`.
- Peak limiting prevents clipping after LUFS gain adjustment (caps at 0.999 linear).
- Silence trimming removes audio below the threshold (default -60 dB) from the start and end.
- Format conversion supports `wav` (default) and other `soundfile`-compatible formats.
- Mix profiles (`streaming`, `radio`, `cinematic`) apply different HPF, EQ, compression, and limiting parameters via the `pedalboard` DSP chain.
- When `pedalboard` is not installed, the DSP chain is skipped and only LUFS normalization runs.
- When `pyloudnorm` is not installed, falls back to peak normalization (-1.0 dB).
- Dynamic ducking is applied when TTS segments are present and `sidechain_source="tts"`.
- Mock mode copies the input file and reports target loudness values without processing.
- Contract overrides from `audio_contract.mix` take precedence over CLI defaults.

**Run tests:**

```bash
pytest tests/test_post_processor.py -v
```

### Stable Audio Generator

Validates the Stability AI Stable Audio API integration.

**What it checks:**

- API key validation: raises `ValueError` if neither `api_key` nor `STABILITY_API_KEY` env var is provided.
- Duration clamped to 5-180 seconds by the Pydantic input schema.
- Job submission sends prompt, duration, and output format to the Stability API.
- Polling loop detects terminal success states (`succeeded`, `completed`, `complete`) and failure states (`failed`, `error`, `cancelled`).
- Timeout protection: raises `GenerationFailedError` if polling exceeds `poll_timeout_seconds`.
- Downloaded content is validated as audio by checking file headers (ID3, RIFF, MPEG frame sync).
- HTTP errors are wrapped in `GenerationFailedError` with descriptive messages.

**Run tests:**

```bash
pytest tests/test_stable_audio_generator.py -v
```

## 8. Optional Dependency Verification

The project uses three optional dependency groups. Each group can be installed and verified independently.

### `[dev]` Group

Test and lint tools required for contribution workflows.

```bash
pip install -e ".[dev]"
```

Includes: `pytest>=8.0`, `pytest-asyncio>=0.23`, `pytest-cov>=5.0`, `ruff>=0.5`.

Verify:

```bash
pytest --tb=no -q
ruff check src/ tests/
```

### `[model]` Group

GPU and audio processing dependencies for local generation.

```bash
pip install -e ".[dev,model]"
```

Includes: `torch>=2.1`, `torchaudio>=2.1`, `transformers>=4.40`, `soundfile>=0.12`, `numpy>=1.26`, `pyloudnorm>=0.1.0`.

Verify:

```bash
python -c "import torch; print('CUDA:', torch.cuda.is_available())"
python -c "import soundfile; print('soundfile OK')"
python -c "import pyloudnorm; print('pyloudnorm OK')"
```

### `[audio]` Group

Additional audio processing libraries for advanced DSP.

```bash
pip install -e ".[audio]"
```

Includes: `pedalboard>=0.9.0`.

Verify:

```bash
python -c "import pedalboard; print('pedalboard OK')"
```

When `pedalboard` is missing, the PostProcessor skips the DSP chain and logs a warning. Not required for CI.

### Full Install

```bash
pip install -e ".[dev,model,audio]"
```

## 9. Test Matrix

All test files and their coverage areas.

| Test File | Coverage Area |
| --- | --- |
| `test_audio_contract.py` | AudioSceneContract schema validation |
| `test_audio_validator.py` | Audio file validation (sample rate, duration) |
| `test_cli.py` | CLI argument parsing and command dispatch |
| `test_generator.py` | ACE-Step local generator and GeneratorConfig |
| `test_lyrics_planner.py` | Lyrics parsing and structuring |
| `test_material_pipeline.py` | Material loading pipeline integration |
| `test_material.py` | MaterialContext schema |
| `test_minimax_generator.py` | MiniMax cloud backend |
| `test_output_config.py` | OutputConfig schema |
| `test_output.py` | OutputWorker file writing |
| `test_pipeline.py` | Full pipeline orchestration |
| `test_post_processor.py` | PostProcessor: normalization, DSP, ducking |
| `test_preset_resolver.py` | Preset resolution logic |
| `test_preset_schemas.py` | Preset schema validation |
| `test_providers.py` | Generator provider registration |
| `test_regression_runner.py` | Regression test runner |
| `test_resume.py` | Pipeline resume behavior |
| `test_stable_audio_generator.py` | StableAudio API client |
| `test_style_planner.py` | StylePlanner mapping |
| `test_workspace.py` | Workspace directory management |

Run the full suite:

```bash
pytest --tb=no -q
```

Expected: 269 passed, 4 skipped, 0 failed.

Run specific tool tests:

```bash
pytest tests/test_post_processor.py \
       tests/test_stable_audio_generator.py -v
```

Run with coverage:

```bash
pytest --cov=src/ace_music --cov-report=term-missing --tb=short
```

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

### Stable Audio generation fails with a configuration error

Confirm that `STABILITY_API_KEY` is set:

```bash
echo "${STABILITY_API_KEY:+set}"
```

The generator raises `ValueError` at initialization if no key is available.

### Stable Audio generation times out

Increase the poll timeout in config or check your network connection:

```bash
# Default timeout is 600 seconds. Check API status separately:
curl -s -H "Authorization: Bearer $STABILITY_API_KEY" \
  https://api.stability.ai/v2beta/audio/stable-audio-2/text-to-audio \
  -X POST -H "Content-Type: application/json" \
  -d '{"prompt":"test","duration":5}' | head -c 200
```

### PostProcessor skips DSP chain

This means `pedalboard` is not installed. The LUFS normalization still runs via `pyloudnorm` (part of `[model]`). For the full DSP chain with mix profiles:

```bash
pip install -e ".[audio]"
python -c "import pedalboard; print('OK')"
```

### Output validation fails

Use the `validate` command to inspect duration and sample-rate mismatches, then compare the summary JSON against the file on disk.
