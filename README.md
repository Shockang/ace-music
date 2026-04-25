# ace-music

AI music generation agent powered by ACE-Step 1.5.

Planning-mode architecture: LyricsPlanner → StylePlanner → GenerationWorker → PostProcessor → OutputWorker.

## Setup

```bash
# Create venv and install
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# With model support (GPU required)
pip install -e ".[dev,model]"
```

## Usage

### CLI

```bash
# Smoke test without GPU/model dependencies
ace-music generate \
  --mock \
  --description "short jazz improvisation" \
  --duration 5 \
  --output-dir ./output \
  --summary-json ./output/last-run.json

# Validate an existing WAV for automation gates
ace-music validate ./output/example.wav \
  --expected-sample-rate 48000 \
  --expected-duration 30 \
  --duration-tolerance 5
```

The CLI prints a JSON summary to stdout and optionally writes the same summary
to `--summary-json` for cron/closed-loop automation. Production generation no
longer silently falls back to mock audio when ACE-Step or CUDA is unavailable;
use `--mock` for local smoke tests or `--allow-mock-fallback` only when that
fallback is intentional.

Exit codes are grouped for diagnostics:

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 2 | Input validation error |
| 20 | Dependency unavailable |
| 21 | GPU unavailable |
| 30 | Generation failed |
| 40 | Stage timeout |
| 50 | Output validation failed |

### Python

```python
from ace_music.agent import MusicAgent
from ace_music.schemas.pipeline import PipelineInput

agent = MusicAgent()
result = await agent.run(PipelineInput(
    description="A dreamy synthwave track about neon cities",
    duration_seconds=60.0,
))
print(result.audio_path)
```

`PipelineInput` includes automation hardening knobs:

- `stage_timeout_seconds` for non-generation stages.
- `generation_timeout_seconds` for the model call.
- `expected_sample_rate`, `min_valid_duration_seconds`, and
  `duration_tolerance_seconds` for final WAV validation.

## Architecture

```
MusicAgent (planner)
  ├── LyricsPlanner   — parse & structure lyrics
  ├── StylePlanner    — map style description to ACE-Step params
  ├── Generator       — call ACE-Step model (or mock)
  ├── PostProcessor   — format conversion, loudness normalization
  └── OutputWorker    — final file + metadata
```

## License

MIT
