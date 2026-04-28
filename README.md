# ace-music

[简体中文](README.zh-CN.md)

[![CI](https://github.com/Shockang/ace-music/actions/workflows/ci.yml/badge.svg)](https://github.com/Shockang/ace-music/actions/workflows/ci.yml)
![License: MIT](https://img.shields.io/badge/license-MIT-0f172a.svg)
![Python 3.12](https://img.shields.io/badge/python-3.12-06b6d4.svg)

![ace-music banner](assets/readme-banner.svg)

Contract-driven AI music generation for Python workflows, automation pipelines, and scene-oriented soundtrack generation.

## Why ace-music

`ace-music` is a Python package for generating and validating music outputs with a workflow-friendly interface. It provides:

- a CLI with machine-readable JSON summaries
- a mock mode for smoke tests and CI
- a local ACE-Step path for GPU-backed generation
- a MiniMax path for cloud-backed generation
- structured input contracts for scene-aware orchestration

## Features

- Stable CLI: `generate` and `validate` commands with clear exit codes.
- Multiple backends: mock, local ACE-Step, and MiniMax.
- Structured contracts: `PipelineInput`, `AudioSceneContract`, and `DirectorBridge`.
- Automation-friendly outputs: JSON summaries, validation metadata, and predictable output paths.
- Testable release surface: CPU-safe mock mode lets contributors verify changes without GPU access.

## Quick Start

The shortest successful path uses mock mode and requires no GPU:

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

You should get a generated WAV file plus a JSON summary at `./output/last-run.json`.

## Installation

Development and mock-mode setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Optional GPU-oriented dependencies:

```bash
pip install -e ".[dev,model]"
```

`.[model]` installs the Python-side GPU/audio dependencies used by this project. The ACE-Step runtime itself is still an external prerequisite and must be installed/configured separately on the target machine. This extra is intentionally excluded from CI.

## Runtime Modes

| Mode | When to use it | Requirements |
| --- | --- | --- |
| Mock | smoke tests, CI, first-run validation | no GPU |
| ACE-Step local | local high-fidelity generation | compatible GPU, model setup |
| MiniMax | cloud backend path | `MINIMAX_API_KEY` |

## CLI Example

Generate audio:

```bash
ace-music generate \
  --mock \
  --description "dreamy synthwave with warm pads" \
  --duration 10 \
  --output-dir ./output \
  --summary-json ./output/run.json
```

Validate a generated WAV directly:

```bash
ace-music validate ./output/path-to-generated.wav \
  --expected-sample-rate 48000 \
  --expected-duration 10 \
  --duration-tolerance 5
```

## Python Example

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


asyncio.run(main())
```

## Architecture

```text
MusicAgent
  -> LyricsPlanner
  -> StylePlanner
  -> Generator or MiniMaxMusicGenerator
  -> PostProcessor
  -> OutputWorker
```

The default flow is contract-driven and stage-based. For more detail, see [docs/audio-engine-architecture.md](docs/audio-engine-architecture.md).

## Docs

- [Validation guide](docs/MUSIC_ENGINE_VALIDATION.md)
- [Architecture overview](docs/audio-engine-architecture.md)

## Troubleshooting

### `ModuleNotFoundError` after install

Activate the virtual environment and reinstall:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

### CUDA or GPU unavailable

Use `--mock` for smoke tests. For local ACE-Step generation, install `.[model]`, install/configure the ACE-Step runtime separately, and run on a machine with supported CUDA tooling.

### `MINIMAX_API_KEY` missing

Export the key before using the MiniMax backend:

```bash
export MINIMAX_API_KEY="your-key"
```

On macOS, the CLI uses a `spawn` worker context for cloud generation to avoid `fork()` crashes in subprocesses that initialize Objective-C-backed libraries.

### Mock mode does not match production quality

That is expected. Mock mode is for CLI validation, automation checks, and contribution workflows, not fidelity evaluation.

## Contributing

Contribution setup, quality gates, and PR expectations live in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
