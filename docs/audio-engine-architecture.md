# ace-music Audio Engine Architecture

## Overview

`ace-music` is a stage-based music generation engine for automation-friendly Python workflows. It supports text-driven generation, validation, and scene-aware orchestration through structured contracts instead of ad-hoc prompt passing.

The public package exposes two core usage styles:

- direct CLI or Python generation with `PipelineInput`
- scene-oriented orchestration with `AudioSceneContract` and `DirectorBridge`

## Core Pipeline

The full local pipeline (v0.3.0) runs through these stages:

```text
PipelineInput
  -> LyricsPlanner        (parse/structure lyrics)
  -> StylePlanner          (map style to generation params)
  -> EmotionMapper         (scene contract -> audio parameters, called inside StylePlanner)
  -> Generator             (ACE-Step / MiniMax / StableAudio)
  -> PostProcessor         (normalize, DSP chain, format conversion)
  -> OutputWorker          (write files + metadata)
  -> PipelineOutput
```

Each stage produces structured data rather than mutating shared global state. That makes the pipeline easier to validate, resume, and integrate into broader automation systems.

Not all stages run every time. The agent builds a plan from the input, then executes it. Instrumental tracks skip lyrics planning. Cloud backends skip most local processing.

## Pipeline Variants

`MusicAgent._build_plan()` selects one of three execution paths based on `PipelineInput.backend`.

### Local ACE-Step Pipeline

`_run_local_pipeline` is the full path. It runs lyrics planning, style planning, local ACE-Step generation, post-processing with the DSP chain, and output writing. This path supports all features: contracts, material context, presets, scene mapping, and mastering.

### MiniMax Cloud Pipeline

`_run_minimax_pipeline` is a simplified path. It sends the description and optional lyrics to the MiniMax cloud API, receives a processed MP3, and writes output directly. No local post-processing runs because MiniMax handles normalization and format conversion server-side.

### StableAudio Cloud Pipeline

`_run_stable_audio_pipeline` is another cloud path, using the Stability AI Stable Audio 2 API. It only supports instrumental generation (no lyrics, no reference audio). The pipeline submits a text-to-audio job, polls until completion, downloads the result, and writes output. Like MiniMax, it skips local post-processing.

## Execution Lanes

| Lane | Purpose | Notes |
| --- | --- | --- |
| Mock | smoke tests and CI | deterministic local WAV generation, no GPU required |
| Local ACE-Step | GPU-backed generation | requires model dependencies and compatible hardware |
| MiniMax | cloud generation | skips local post-processing, uses API-backed output |
| StableAudio | cloud generation | instrumental only, uses Stability AI Stable Audio 2 API |

The public CLI keeps these lanes behind the same `generate` command so callers can switch between them without replacing their surrounding workflow.

## Tool Modules

### LyricsPlanner

Parses raw text into structured lyrics with segments (verse, chorus, bridge). Skipped for instrumental tracks. When material context provides lyrics, those take priority over the raw description.

### StylePlanner

Maps description, style tags, tempo preference, mood, and optional presets into a `StyleOutput` with a generation prompt. Can receive a `FeatureRouter` to route LLM calls to specific providers.

### EmotionMapper

Maps an `AudioSceneContract` to concrete audio generation parameters. This is the bridge between scene intent and generation reality.

The mapper produces a `MappedAudioParameters` object containing:

- **style tags** derived from mood, valence/arousal, and scene role
- **tempo preference** estimated from arousal and shot density
- **guidance scale** calculated from intensity and pace
- **prompt suffix** with mood, intensity, pace, scene description, and transition info
- **mix policy** with adjusted BGM gain, ducking, and sidechain settings
- **transition policy** carried through from the contract
- **QA targets** carried through for downstream validation

Two mapping modes exist. When `valence` is set on the contract, the mapper uses the Russell Circumplex model to derive style tags and key suggestions from four quadrants (excited, calm, nervous, sad). Otherwise, it falls back to a direct mood-to-tag lookup table.

### Generator (ACE-Step)

Local GPU-backed generation using the ACE-Step model. Accepts a `GenerationInput` with lyrics, style, duration, seed, output format. Supports model variants: 2b, xl-base, xl-sft, xl-turbo. The agent caches generator instances by config to avoid redundant model loading.

### MiniMax Generator

Cloud-backed generation via the MiniMax API. Accepts description, mode, lyrics, and optional reference audio. Requires `MINIMAX_API_KEY`. Outputs processed MP3.

### StableAudio Generator

Cloud-backed generation via the Stability AI Stable Audio 2 API. Accepts description and duration (5-180s). Requires `STABILITY_API_KEY`.

The generator submits a text-to-audio job, then polls the API at configurable intervals until the job completes or times out. It validates that downloaded content looks like audio (checks for ID3, RIFF, or MPEG frame headers) before writing to disk. Outputs MP3 at 44100 Hz stereo.

### PostProcessor

The DSP mastering chain. Runs after generation in the local pipeline. Processes audio through multiple stages:

1. **Silence trimming**: removes leading and trailing silence below a threshold (default -60 dB)
2. **Loudness normalization**: targets EBU R128 integrated loudness (default -14 LUFS) using `pyloudnorm`, with peak limiting to prevent clipping after gain adjustment
3. **DSP chain** (when `pedalboard` is installed): applies a mastering chain with high-pass filter, bass/treble EQ shelves, compressor, and brick-wall limiter
4. **Ducking**: when the contract specifies TTS present with sidechain source, applies dynamic ducking (envelope-based per TTS segment) or static gain reduction
5. **Format conversion**: writes the final output in the target format (default WAV)
6. **LUFS remeasurement**: measures final loudness after all processing for accurate metadata

Three mix profiles are available for the DSP chain:

| Profile | HPF | Bass | Treble | Comp Threshold | Comp Ratio | Limiter |
| --- | --- | --- | --- | --- | --- | --- |
| streaming | 80 Hz | +1.0 dB | +1.5 dB | -12 dB | 3.0 | -1.0 dB |
| radio | 80 Hz | +0.5 dB | +2.5 dB | -15 dB | 4.0 | -1.0 dB |
| cinematic | 60 Hz | +2.0 dB | +0.5 dB | -10 dB | 2.0 | -1.5 dB |

Scene contracts can override the target LUFS via `contract.mix.target_lufs`.

### OutputWorker

Writes final audio files and metadata. Produces generated audio, JSON metadata about generation parameters, optional machine-readable summaries, and structured output paths.

### MaterialLoader

Loads structured music material from JSON files in a directory. Used for scene-aware generation where external context (style summaries, mood tags, lyrics snippets) influences the generation pipeline.

Three loading modes:

- `load()`: reads all `*.json` files from the directory, merges entries
- `load_latest()`: reads only the most recently modified file
- `load_file(filename)`: reads a specific file by name or absolute path

Each JSON file contains an `entries` array with `content`, `category`, `tags`, `mood`, and `style` fields. The loader returns a `MaterialContext` that the agent resolves into effective description, style tags, mood, and lyrics before passing them to planners.

### FeatureRouter

Routes LLM completion requests to different providers based on feature name. Each pipeline feature (lyrics_planning, style_planning, etc.) can be bound to a specific provider. Unbound features fall back to the default.

This lets the agent use different LLM backends for different planning tasks. For example, style planning could use a larger model while lyrics planning uses a faster one.

## Structured Contracts

### `PipelineInput`

`PipelineInput` is the direct public input model for CLI and Python usage. It carries description, duration, language, style hints, output options, validation targets, and backend selection.

### `AudioSceneContract`

`AudioSceneContract` is a higher-level scene description used when an orchestration system already knows timing, mood, dialogue pressure, loudness targets, or transition constraints. It helps upstream systems pass intent in a structured way instead of flattening everything into a single text prompt.

### `DirectorBridge`

`DirectorBridge` is the package's public scene-to-music adapter contract. It defines a request/response shape that external orchestrators can map into `PipelineInput` and convert back into generated-audio results.

## Output Artifacts

The engine produces:

- generated audio files
- metadata about generation parameters and validation
- optional machine-readable JSON summaries
- structured output paths suitable for automation or downstream processing

This output model is designed for reproducibility and post-run inspection, not just interactive use.

## Validation Model

Validation is treated as part of the engine surface, not a separate afterthought. The CLI exposes a dedicated `validate` command, and generation flows can record expected sample rate, duration targets, and tolerances for automation checks.

In the local pipeline, validation runs twice: once after post-processing and once after final output. Both must pass for the pipeline to succeed. Cloud pipelines validate at the output stage.

## Agent Methods

`MusicAgent` exposes these public methods:

| Method | Purpose |
| --- | --- |
| `run(input_data)` | Execute the full pipeline for a single input |
| `run_sequence(inputs)` | Execute multiple inputs with shared style planning |
| `resume(run_id, workspace)` | Resume a failed or interrupted pipeline from the last completed stage |

`run_sequence` is optimized for batch generation. When all inputs have contracts and use the ACE-Step backend, it plans styles in a single batch call to `StylePlanner.plan_sequence` before running individual pipelines, avoiding redundant LLM calls.

## Design Goals

- predictable stage boundaries
- reproducible CLI behavior
- public-safe integration contracts
- mock-first contribution workflow
- minimal assumptions about the caller's infrastructure
