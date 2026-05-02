<p align="center">
  <img src="assets/ace-music.png" alt="ace-music banner" width="100%">
</p>

<p align="center">
  <strong>Contract-driven AI music generation for Python workflows, automation pipelines, and scene-oriented soundtrack production.</strong><br>
  Stage-based pipeline, 11 tool modules, 269 passing tests, mock mode out of the box, three generation backends.
</p>

<p align="center">
  <a href="https://github.com/Shockang/ace-music/actions/workflows/ci.yml">
    <img alt="CI" src="https://github.com/Shockang/ace-music/actions/workflows/ci.yml/badge.svg">
  </a>
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-0f172a.svg">
  <img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-06b6d4.svg">
  <img alt="269 tests" src="https://img.shields.io/badge/tests-269_passed-22c55e.svg">
</p>

<p align="center">
  <a href="https://github.com/Shockang/auto-director">Companion Project: auto-director</a>
</p>

<p align="center">
  <a href="README.zh-CN.md">中文文档</a>
  ·
  <a href="https://github.com/Shockang/auto-director">auto-director</a>
  ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

## Overview

`ace-music` is a contract-driven music generation toolkit.

Instead of calling a model endpoint and hoping the output is the right length, format, and loudness, `ace-music` runs a structured pipeline with built-in validation at every stage:

```text
PipelineInput
  -> LyricsPlanner
  -> StylePlanner
  -> Generator (ACE-Step / MiniMax / StableAudio)
  -> PostProcessor
  -> OutputWorker
  -> PipelineOutput (validated)
```

The result is not "just an audio file."

The result is a validated, contract-shaped audio asset with metadata, validation records, and a machine-checkable summary.

## Highlights

| What | Detail |
| --- | --- |
| Stage-based pipeline | LyricsPlanner, StylePlanner, Generator, PostProcessor, OutputWorker |
| 11 tool modules | Each stage is a standalone, testable tool with typed input/output schemas |
| 9 schema modules | PipelineInput, PipelineOutput, AudioSceneContract, StyleInput, StyleOutput, LyricsInput, LyricsOutput, MaterialContext, OutputConfig |
| 3 backends | ACE-Step (local GPU), MiniMax (cloud), StableAudio (cloud) |
| Mock mode | Deterministic local WAV generation. No GPU, no API key, no network |
| Contract-driven | AudioSceneContract with mix policy, transition policy, TTS ducking, QA targets |
| Scene-aware bridge | DirectorBridge.Request / Response for auto-director integration |
| 269 passing tests | Full pipeline coverage including resume, validation, and edge cases |
| JSON summaries | Machine-readable run summaries with exit codes, validation, and metadata |

## Ecosystem Snapshot

```text
plain-text fiction
        |
        v
  auto-director
        |
        +--> story / cast / screenplay / scene blueprint / prompt package / review / delivery
        |
        +--> optional render handoff assets
        |
        +--> scene contracts, mood, timing
                |
                v
          ace-music
                |
                +--> scene-aware soundtrack generation
                +--> validated audio output with metadata
                +--> mix / ducking / loudness contracts
```

`auto-director` produces structured scene contracts. `ace-music` consumes those contracts and generates soundtrack audio that matches the mood, timing, and mix requirements of each scene.

The pairing is clean: `auto-director` handles story structure and visual production, `ace-music` handles the sound layer.

## Why Someone Might Star This

Because the repo solves the boring part of AI music generation that most demos skip:

- "Did the output file land at the right duration?" Built-in validation checks this.
- "Can I test the pipeline without a GPU?" Mock mode generates deterministic WAV files in CI.
- "Can I plug this into a larger workflow?" DirectorBridge gives you a typed request/response contract.
- "Can I resume a failed run?" The pipeline tracks completed stages and can pick up where it stopped.
- "Does the output satisfy mix requirements?" AudioSceneContract carries loudness targets, ducking rules, and transition policies.

That is more interesting than another "text to music" API wrapper.

## Try It In 60 Seconds

The shortest proof that the repository works. No GPU required:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ace-music generate \
  --mock \
  --description "short jazz improvisation" \
  --duration 5 \
  --output-dir ./output \
  --summary-json ./output/last-run.json
```

Then open `./output/last-run.json`. You get a WAV file plus a machine-readable summary with validation results, duration, sample rate, and timing.

## Pipeline Stages

```text
  PipelineInput
        |
        v
  1. LyricsPlanner .......... parse/structure lyrics text
        |
        v
  2. StylePlanner ........... map description + tags to ACE-Step params
        |
        v
  3. Generator .............. call ACE-Step / MiniMax / StableAudio
        |
        v
  4. PostProcessor .......... normalize, loudness, format conversion
        |
        v
  5. OutputWorker ........... write files + metadata + validation
        |
        v
  PipelineOutput
```

Each stage is a separate tool module with typed input and output schemas. The agent builds a plan from the input, then executes stages sequentially. EmotionMapper resolves style context internally during the StylePlanner stage. Cloud backends (MiniMax, StableAudio) skip most planning stages and go directly to generation.

## Tool Catalog

11 tool modules, each with a single responsibility:

| Module | What it does |
| --- | --- |
| `audio_validator` | Validate audio files against duration, sample rate, and format requirements |
| `emotion_mapper` | Map scene contracts to audio parameters (tempo, style tags, mix) |
| `generator` | ACE-Step local model generation with mock mode support |
| `lyrics_planner` | Parse and structure raw lyrics text into timed segments |
| `material_loader` | Load daily material context (inspiration, style, lyrics) |
| `minimax_generator` | MiniMax cloud API backend (instrumental, lyrics, cover modes) |
| `output` | Write final audio files, metadata JSON, and run validation |
| `post_processor` | DSP chain: normalize, loudness targeting, format conversion |
| `preset_resolver` | Resolve named style presets to concrete parameters |
| `stable_audio_generator` | StableAudio cloud API backend (instrumental only) |
| `style_planner` | Map description and tags to ACE-Step generation parameters |

## Runtime Modes

| Mode | When to use | Requirements |
| --- | --- | --- |
| Mock | CI, smoke tests, first run, no GPU | None |
| ACE-Step (local) | High-fidelity local generation | CUDA GPU, model weights, `pip install -e ".[model]"` |
| MiniMax (cloud) | Cloud generation without local GPU | `MINIMAX_API_KEY` environment variable |
| StableAudio (cloud) | Cloud instrumental generation | `STABILITY_API_KEY` environment variable |

Mock mode generates a deterministic sine-wave WAV. It is not a model output. It is a contract-shaped placeholder that exercises the entire pipeline except the model call.

## auto-director Integration

`ace-music` provides `DirectorBridge` as a typed request/response contract for scene-oriented soundtrack generation.

### DirectorBridge.Request

```python
from ace_music.bridge import DirectorBridge

request = DirectorBridge.Request(
    scene_id="scene_042",
    mood="melancholic",
    duration_seconds=30.0,
    style_reference="piano, slow tempo, minor key",
    scene_description="Character walks alone through rain-soaked streets at night",
    intensity=0.7,
    valence=-0.3,
    arousal=0.4,
    dialogue_density=0.2,
    tts_present=False,
    target_lufs=-16.0,
    preset_name="dark_ambient",
)
```

### DirectorBridge.Response

```python
response = DirectorBridge.Response(
    audio_path="/output/scene_042.wav",
    duration_seconds=29.8,
    format="wav",
    scene_id="scene_042",
    success=True,
    metadata={"seed": 42, "bpm": 72, "style": "dark ambient, piano"},
)
```

The bridge is how `auto-director` and `ace-music` talk. One produces scene contracts, the other produces audio that satisfies them.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Optional dependency groups:

| Extra | What it installs |
| --- | --- |
| `.[dev]` | Test runner, linters, dev tooling. Required for contributing. |
| `.[model]` | PyTorch, soundfile, and GPU/audio dependencies for local ACE-Step generation |
| `.[audio]` | Additional audio processing libraries |

The `.[model]` extra is excluded from CI. Install it only on machines with compatible CUDA tooling.

## CLI Reference

### generate

```bash
ace-music generate \
  --description "dreamy synthwave with warm pads" \
  --mock \
  --duration 10 \
  --backend acestep \
  --output-dir ./output \
  --summary-json ./output/run.json
```

Key flags (from `ace-music generate --help`):

| Flag | Default | Purpose |
| --- | --- | --- |
| `--description` | required | Natural language music description |
| `--backend` | `acestep` | `acestep`, `minimax`, or `stable_audio` |
| `--mode` | `instrumental` | `instrumental`, `lyrics`, or `cover` (MiniMax) |
| `--model-variant` | `2b` | `2b`, `xl-base`, `xl-sft`, `xl-turbo` (ACE-Step) |
| `--duration` | `30.0` | Target duration, 5-240 seconds |
| `--mock` | off | Deterministic local WAV, no GPU |
| `--preset` | none | Named style preset |
| `--seed` | random | Reproducibility seed |
| `--format` | `wav` | Output audio format |
| `--output-dir` | `./output` | Where to write files |
| `--target-lufs` | none | Target output loudness |
| `--total-timeout` | auto | Wall-clock command timeout |
| `--summary-json` | none | Write machine-readable JSON summary |

### validate

```bash
ace-music validate ./output/generated.wav \
  --expected-sample-rate 48000 \
  --expected-duration 10 \
  --duration-tolerance 5
```

Checks sample rate, duration, and format. Returns exit code 0 on pass, 50 on failure. Always outputs a JSON summary.

## Python API

```python
import asyncio

from ace_music.agent import MusicAgent
from ace_music.schemas.pipeline import PipelineInput
from ace_music.tools.generator import GeneratorConfig


async def main() -> None:
    agent = MusicAgent(generator_config=GeneratorConfig(mock_mode=True))
    result = await agent.run(
        PipelineInput(
            description="A dreamy synthwave track about neon cities",
            duration_seconds=20.0,
            output_dir="./output",
        )
    )
    print(result.audio_path)
    print(result.duration_seconds)
    print(result.metadata.get("validation"))


asyncio.run(main())
```

All imports are real. All signatures match the source. Copy, paste, run.

### Batch generation

```python
results = await agent.run_sequence(
    [
        PipelineInput(description="Opening credits theme", duration_seconds=30.0),
        PipelineInput(description="Tense underscore", duration_seconds=45.0),
        PipelineInput(description="Closing credits", duration_seconds=30.0),
    ]
)
```

### Resume a failed run

```python
from ace_music.workspace import WorkspaceManager

workspace = WorkspaceManager(base_dir="./workspace")
result = await agent.resume(run_id="abc123", workspace=workspace)
```

## Architecture

```text
MusicAgent
  |
  +-- LyricsPlanner ........... src/ace_music/tools/lyrics_planner.py
  +-- StylePlanner ............ src/ace_music/tools/style_planner.py
  +-- EmotionMapper ........... src/ace_music/tools/emotion_mapper.py
  +-- PresetResolver .......... src/ace_music/tools/preset_resolver.py
  +-- MaterialLoader .......... src/ace_music/tools/material_loader.py
  |
  +-- ACEStepGenerator ........ src/ace_music/tools/generator.py
  +-- MiniMaxMusicGenerator ... src/ace_music/tools/minimax_generator.py
  +-- StableAudioGenerator .... src/ace_music/tools/stable_audio_generator.py
  |
  +-- PostProcessor ........... src/ace_music/tools/post_processor.py
  +-- AudioValidator .......... src/ace_music/tools/audio_validator.py
  +-- OutputWorker ............ src/ace_music/tools/output.py
  |
  +-- DirectorBridge .......... src/ace_music/bridge/__init__.py
  +-- WorkspaceManager ........ src/ace_music/workspace.py
  +-- FeatureRouter ........... src/ace_music/providers/router.py
```

Schema layer (`src/ace_music/schemas/`): `pipeline`, `audio_contract`, `audio`, `lyrics`, `material`, `output_config`, `preset`, `repair`, `style`.

The agent follows a Planning pattern: it builds an execution plan from the input, then runs stages sequentially. Each stage receives typed input and produces typed output. Validation runs after post-processing and again after output.

## Development

Run the full test suite:

```bash
pip install -e ".[dev]"
pytest -q
```

269 tests pass. 4 skipped (GPU-dependent). CI runs on every push.

Useful checks:

```bash
ace-music --help
ace-music generate --help
git diff --check
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contributor workflow.

## Docs

- [Architecture overview](docs/audio-engine-architecture.md)
- [Validation guide](docs/MUSIC_ENGINE_VALIDATION.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)

## Troubleshooting

### ModuleNotFoundError after install

Activate the venv and reinstall:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

### CUDA or GPU unavailable

Use `--mock` for smoke tests. For local ACE-Step generation, install `.[model]`, configure the ACE-Step runtime separately, and run on a machine with CUDA.

### MINIMAX_API_KEY missing

```bash
export MINIMAX_API_KEY="your-key"
```

On macOS, the CLI uses a `spawn` worker context for cloud generation. This avoids `fork()` crashes in subprocesses that initialize Objective-C libraries.

### Mock mode does not sound like a real model

That is expected. Mock mode exercises the pipeline, not the model. It generates a deterministic sine-wave WAV so you can verify contracts, validation, and output structure without GPU access.

## Current Scope

This repository is for contract-driven music generation and validation.

It is intentionally **not**:

- a hosted music service
- a DAW plugin
- a real-time audio server
- a model training framework
- a general-purpose audio editor

That focus keeps the codebase small, testable, and easy to reason about.

## License

MIT. See [LICENSE](LICENSE).
