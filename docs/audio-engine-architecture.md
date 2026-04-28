# ace-music Audio Engine Architecture

## Overview

`ace-music` is a stage-based music generation engine for automation-friendly Python workflows. It supports text-driven generation, validation, and scene-aware orchestration through structured contracts instead of ad-hoc prompt passing.

The public package exposes two core usage styles:

- direct CLI or Python generation with `PipelineInput`
- scene-oriented orchestration with `AudioSceneContract` and `DirectorBridge`

## Core Pipeline

The default local pipeline is:

```text
MusicAgent
  -> LyricsPlanner
  -> StylePlanner
  -> Generator
  -> PostProcessor
  -> OutputWorker
```

Each stage produces structured data rather than mutating shared global state. That makes the pipeline easier to validate, resume, and integrate into broader automation systems.

## Execution Paths

`ace-music` currently supports three execution lanes:

| Lane | Purpose | Notes |
| --- | --- | --- |
| Mock | smoke tests and CI | deterministic local WAV generation |
| Local ACE-Step | GPU-backed generation | requires model dependencies and compatible hardware |
| MiniMax | cloud generation | skips local post-processing and uses API-backed output |

The public CLI keeps these lanes behind the same `generate` command so callers can switch between them without replacing their surrounding workflow.

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

## Design Goals

- predictable stage boundaries
- reproducible CLI behavior
- public-safe integration contracts
- mock-first contribution workflow
- minimal assumptions about the caller's infrastructure
