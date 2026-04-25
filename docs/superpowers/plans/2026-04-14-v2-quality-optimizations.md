# ace-music V2 Quality Optimizations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize ace-music's output persistence, preset system, provider support, and DirectorBridge integration — building on the stable v2 foundation (113 tests passing, E2E verified on RTX 3090 Ti) without breaking the verified pipeline.

**Architecture:** Four independent enhancement groups, each testable in isolation: (1) configurable output persistence with Obsidian path support and flat naming, (2) dark suspense preset for the thriller use case, (3) MiniMax provider + provider config wiring into MusicAgent, (4) DirectorBridge Request/Response enhancement with scene context and error handling. Each group adds value without modifying existing behavior.

**Tech Stack:** Python 3.12, Pydantic 2, PyYAML, httpx, pytest + pytest-asyncio, ruff

---

## Scope Note

The v2 plan (`2026-04-14-ace-music-v2.md`) is **fully implemented**: structured output directories, preset system (21 presets, 4 YAML files), workspace manifests, resume support, and provider abstraction (ChatProvider protocol, DeepSeekProvider, FeatureRouter) are all in place and tested (113 tests passing).

**This plan covers the remaining quality optimizations from the spec:**

| Priority | Optimization | Status Before This Plan | This Plan |
|----------|-------------|------------------------|-----------|
| P0 | Output persistence to Obsidian | OutputWorker saves to `./output/{slug}/{ts}/` nested dirs | Add flat naming mode, OutputConfig, Obsidian path factory |
| P1 | Dark suspense preset | 21 presets across 4 files, no `dark_suspense` | Add dark_suspense to cinematic.yaml |
| P2 | MiniMax provider | Only DeepSeekProvider implemented | Add MiniMaxProvider (OpenAI-compatible) |
| P2 | Provider wiring into agent | FeatureRouter exists but unused | Wire into MusicAgent.__init__ as optional param |
| P3 | DirectorBridge enhancement | Basic Request/Response with 8/5 fields | Add scene_description, intensity, preset_name, success, error |

**Risk constraints (from spec):**
- Do NOT modify Windows-side `acestep_generate.py`
- Do NOT install `torchcodec`
- Do NOT break existing E2E pipeline (the only fully verified project)
- Run `pytest tests/ -q --tb=short` after every change — must maintain 113+ passing

---

## File Structure

```
src/ace_music/
  schemas/
    output_config.py        # CREATE — OutputConfig model (base_dir, naming, filename_template)
    __init__.py             # MODIFY — add OutputConfig re-export (line 8, line 21)
    pipeline.py             # MODIFY — add output_config field to PipelineInput
  tools/
    output.py               # MODIFY — accept OutputConfig in OutputInput, add flat naming
  providers/
    minimax.py              # CREATE — MiniMaxProvider (OpenAI-compatible API)
    __init__.py             # MODIFY — add MiniMaxProvider re-export (line 4, line 10)
  bridge/
    __init__.py             # MODIFY — add fields to Request/Response
    director_bridge.py      # MODIFY — handle new fields in conversion
  agent.py                  # MODIFY — accept optional FeatureRouter + pass OutputConfig
configs/
  default.yaml              # MODIFY — add output.naming and provider config sections
  presets/
    cinematic.yaml          # MODIFY — add dark_suspense preset (after line 43)
tests/
  test_output_config.py     # CREATE — OutputConfig schema tests
  test_output.py            # MODIFY — add TestOutputWorkerFlatNaming class
  test_preset_resolver.py   # MODIFY — add TestDarkSuspensePreset class
  test_providers.py         # MODIFY — add TestMiniMaxProvider class
  test_pipeline.py          # MODIFY — add TestPipelineWithOutputConfig, TestAgentWithFeatureRouter, TestDirectorBridgeEnhanced
```

---

## Task 1: OutputConfig Schema (P0)

**Files:**
- Create: `src/ace_music/schemas/output_config.py`
- Modify: `src/ace_music/schemas/__init__.py`
- Create: `tests/test_output_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_output_config.py
"""Tests for OutputConfig schema."""

import pytest

from ace_music.schemas.output_config import OutputConfig


class TestOutputConfigDefaults:
    def test_default_values(self):
        config = OutputConfig()
        assert config.base_dir == "./output"
        assert config.naming == "nested"
        assert config.create_metadata is True

    def test_custom_values(self):
        config = OutputConfig(
            base_dir="/tmp/music",
            naming="flat",
            filename_template="{slug}_{date}",
        )
        assert config.base_dir == "/tmp/music"
        assert config.naming == "flat"

    def test_invalid_naming_rejected(self):
        with pytest.raises(Exception):
            OutputConfig(naming="invalid")


class TestOutputConfigObsidianFactory:
    def test_obsidian_factory_sets_flat_naming(self):
        config = OutputConfig.for_obsidian(base="/tmp/test_output")
        assert config.naming == "flat"
        assert config.base_dir == "/tmp/test_output"

    def test_obsidian_factory_default_path_contains_music(self):
        config = OutputConfig.for_obsidian()
        assert "outputs/music" in config.base_dir

    def test_obsidian_factory_custom_base(self):
        config = OutputConfig.for_obsidian(base="/custom/path")
        assert config.base_dir == "/custom/path"
        assert config.naming == "flat"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_output_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ace_music.schemas.output_config'`

- [ ] **Step 3: Implement OutputConfig schema**

```python
# src/ace_music/schemas/output_config.py
"""Output configuration for music generation pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class OutputConfig(BaseModel):
    """Configuration for output file management.

    Controls how output files are named and organized:
    - "nested": {base_dir}/{style_slug}/{timestamp}/audio.wav (default, development)
    - "flat": {base_dir}/{slug}_{date}_{seq}.wav (production, Obsidian integration)
    """

    base_dir: str = Field(
        default="./output",
        description="Base output directory for generated audio files",
    )
    naming: Literal["nested", "flat"] = Field(
        default="nested",
        description="File naming strategy: 'nested' creates subdirectories, 'flat' uses descriptive filenames",
    )
    filename_template: str = Field(
        default="{slug}_{date}_{seq:03d}",
        description="Filename template for flat naming mode. Available vars: slug, date, seq",
    )
    create_metadata: bool = Field(
        default=True,
        description="Write sidecar metadata JSON alongside audio files",
    )

    @classmethod
    def for_obsidian(cls, base: str | None = None) -> OutputConfig:
        """Create config targeting Obsidian outputs directory.

        Args:
            base: Custom base path. Defaults to ~/Library/Mobile Documents/.../outputs/music
        """
        obsidian_base = base or str(
            Path.home()
            / "Library/Mobile Documents/iCloud~md~obsidian/Documents/AI/outputs/music"
        )
        return cls(
            base_dir=obsidian_base,
            naming="flat",
        )
```

- [ ] **Step 4: Re-export from schemas/__init__.py**

Edit `src/ace_music/schemas/__init__.py`:

Add import after line 7:
```python
from .output_config import OutputConfig
```

Add `"OutputConfig"` to the `__all__` list (alphabetically, after `"PipelineOutput"`):
```python
    "OutputConfig",
    "PipelineOutput",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_output_config.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -q --tb=short`
Expected: 113+ tests passing, no regressions.

- [ ] **Step 7: Commit**

```bash
git add src/ace_music/schemas/output_config.py src/ace_music/schemas/__init__.py tests/test_output_config.py
git commit -m "feat(schemas): add OutputConfig with flat naming and Obsidian path support"
```

---

## Task 2: OutputWorker Flat Naming Mode (P0)

**Files:**
- Modify: `src/ace_music/tools/output.py`
- Modify: `tests/test_output.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_output.py`:

```python
from ace_music.schemas.output_config import OutputConfig


class TestOutputWorkerFlatNaming:
    @pytest.mark.asyncio
    async def test_flat_naming_creates_descriptive_filename(self, worker, sample_audio, tmp_path):
        """Flat mode should create {slug}_{date}_{seq:03d}.wav directly in base_dir."""
        config = OutputConfig(base_dir=str(tmp_path / "music"), naming="flat")
        result = await worker.execute(
            OutputInput(
                audio=sample_audio,
                style=StyleOutput(prompt="suspense, dark, thriller"),
                seed=42,
                description="test",
                output_config=config,
            )
        )
        path = Path(result.audio_path)
        assert path.parent == tmp_path / "music"
        assert "suspense" in path.stem
        assert path.suffix == ".wav"

    @pytest.mark.asyncio
    async def test_flat_naming_auto_increments_sequence(self, worker, sample_audio, tmp_path):
        """Multiple runs should auto-increment the sequence number."""
        config = OutputConfig(base_dir=str(tmp_path / "music"), naming="flat")
        result1 = await worker.execute(
            OutputInput(
                audio=sample_audio,
                style=StyleOutput(prompt="pop"),
                seed=1,
                output_config=config,
            )
        )
        result2 = await worker.execute(
            OutputInput(
                audio=sample_audio,
                style=StyleOutput(prompt="pop"),
                seed=2,
                output_config=config,
            )
        )
        stem1 = Path(result1.audio_path).stem
        stem2 = Path(result2.audio_path).stem
        assert stem1.rsplit("_", 1)[-1] != stem2.rsplit("_", 1)[-1]

    @pytest.mark.asyncio
    async def test_flat_naming_writes_metadata(self, worker, sample_audio, tmp_path):
        """Flat mode should still write metadata JSON alongside audio."""
        config = OutputConfig(base_dir=str(tmp_path / "music"), naming="flat")
        result = await worker.execute(
            OutputInput(
                audio=sample_audio,
                style=StyleOutput(prompt="ambient"),
                seed=42,
                output_config=config,
            )
        )
        assert result.metadata_path is not None
        assert Path(result.metadata_path).exists()
        metadata = json.loads(Path(result.metadata_path).read_text())
        assert metadata["seed"] == 42

    @pytest.mark.asyncio
    async def test_nested_mode_unchanged_when_no_config(self, worker, sample_audio, tmp_path):
        """Without OutputConfig, behavior should be identical to current nested mode."""
        result = await worker.execute(
            OutputInput(
                audio=sample_audio,
                style=StyleOutput(prompt="electronic, synthwave"),
                seed=42,
                output_dir=str(tmp_path / "output"),
            )
        )
        path = Path(result.audio_path)
        assert path.parent.parent.name == "electronic"
        assert path.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_output.py::TestOutputWorkerFlatNaming -v`
Expected: FAIL — `OutputInput.__init__()` got an unexpected keyword argument `output_config`.

- [ ] **Step 3: Add OutputConfig import and field to OutputInput**

Edit `src/ace_music/tools/output.py`:

Add import after line 12:
```python
from ace_music.schemas.output_config import OutputConfig
```

Add field to `OutputInput` class (after `output_dir` field, line 27):
```python
    output_config: OutputConfig | None = None
```

The complete `OutputInput` class should be:
```python
class OutputInput(BaseModel):
    """Input for the output worker."""

    audio: ProcessedAudio
    style: StyleOutput
    seed: int | None = None
    lyrics_text: str = ""
    description: str = ""
    output_dir: str = "./output"
    output_config: OutputConfig | None = None
```

- [ ] **Step 4: Add _next_flat_path method to OutputWorker**

Add this method to the `OutputWorker` class in `src/ace_music/tools/output.py`, after the `_slugify` method:

```python
    def _next_flat_path(self, base_dir: Path, slug: str, ext: str, template: str) -> Path:
        """Generate next flat filename with auto-incremented sequence."""
        date = time.strftime("%Y%m%d")
        existing = list(base_dir.glob(f"{slug}_{date}_*.{ext}"))
        seq = len(existing) + 1
        stem = template.format(slug=slug, date=date, seq=seq)
        return base_dir / f"{stem}.{ext}"
```

- [ ] **Step 5: Replace execute() to support both modes**

Replace the entire `execute` method (lines 73-124) in `src/ace_music/tools/output.py`:

```python
    async def execute(self, input_data: OutputInput) -> OutputResult:
        config = input_data.output_config
        src = Path(input_data.audio.file_path)

        if config:
            base_dir = Path(config.base_dir)
            base_dir.mkdir(parents=True, exist_ok=True)

            if config.naming == "flat":
                slug = self._slugify(input_data.style.prompt)
                dest = self._next_flat_path(
                    base_dir, slug, src.suffix.lstrip("."), config.filename_template
                )
            else:
                style_slug = self._slugify(input_data.style.prompt)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                out_dir = base_dir / style_slug / timestamp
                out_dir.mkdir(parents=True, exist_ok=True)
                dest = out_dir / src.name
        else:
            base_dir = Path(input_data.output_dir)
            style_slug = self._slugify(input_data.style.prompt)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            out_dir = base_dir / style_slug / timestamp
            out_dir.mkdir(parents=True, exist_ok=True)
            dest = out_dir / src.name

        # Copy audio file
        if src.resolve() != dest.resolve():
            import shutil

            shutil.copy2(str(src), str(dest))
        final_path = str(dest)

        # Build metadata
        metadata = {
            "generator": "ace-music",
            "version": ace_music.__version__,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "description": input_data.description,
            "style": {
                "prompt": input_data.style.prompt,
                "guidance_scale": input_data.style.guidance_scale,
                "scheduler_type": input_data.style.scheduler_type,
                "infer_step": input_data.style.infer_step,
            },
            "audio": {
                "duration_seconds": input_data.audio.duration_seconds,
                "format": input_data.audio.format,
                "sample_rate": input_data.audio.sample_rate,
                "loudness_lufs": input_data.audio.loudness_lufs,
                "peak_db": input_data.audio.peak_db,
            },
            "seed": input_data.seed,
            "lyrics": input_data.lyrics_text if input_data.lyrics_text else None,
        }

        # Write metadata JSON
        meta_file: Path | None = None
        if not config or config.create_metadata:
            meta_file = dest.parent / f"{dest.stem}_metadata.json"
            meta_file.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

        logger.info("Output written: %s", final_path)

        return OutputResult(
            audio_path=final_path,
            metadata_path=str(meta_file) if meta_file else None,
            duration_seconds=input_data.audio.duration_seconds,
            format=input_data.audio.format,
            sample_rate=input_data.audio.sample_rate,
            metadata=metadata,
        )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_output.py -v`
Expected: All tests PASS (3 existing + 4 new = 7 total).

- [ ] **Step 7: Run full test suite**

Run: `pytest tests/ -q --tb=short`
Expected: All tests passing, no regressions.

- [ ] **Step 8: Commit**

```bash
git add src/ace_music/tools/output.py tests/test_output.py
git commit -m "feat(output): add flat naming mode with auto-incrementing sequence for Obsidian integration"
```

---

## Task 3: Config Integration + Agent Wiring (P0)

**Files:**
- Modify: `src/ace_music/schemas/pipeline.py`
- Modify: `src/ace_music/agent.py`
- Modify: `configs/default.yaml`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pipeline.py`:

```python
from ace_music.schemas.output_config import OutputConfig


class TestPipelineWithOutputConfig:
    @pytest.mark.asyncio
    async def test_pipeline_passes_output_config_to_worker(self, tmp_path):
        """MusicAgent should pass OutputConfig through to OutputWorker."""
        agent = MusicAgent(generator_config=GeneratorConfig(mock_mode=True))
        config = OutputConfig(base_dir=str(tmp_path / "flat_output"), naming="flat")
        result = await agent.run(
            PipelineInput(
                description="test flat output",
                duration_seconds=5.0,
                output_config=config,
            )
        )
        assert Path(result.audio_path).parent == tmp_path / "flat_output"
        assert Path(result.audio_path).exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline.py::TestPipelineWithOutputConfig -v`
Expected: FAIL — `PipelineInput.__init__()` got an unexpected keyword argument `output_config`.

- [ ] **Step 3: Add output_config to PipelineInput**

Edit `src/ace_music/schemas/pipeline.py`:

Add import after line 3:
```python
from ace_music.schemas.output_config import OutputConfig
```

Add field to `PipelineInput` class (after `infer_step` field, line 34):
```python
    output_config: OutputConfig | None = Field(
        default=None, description="Output configuration (naming, path, metadata)"
    )
```

- [ ] **Step 4: Modify MusicAgent.run() to pass OutputConfig**

Edit `src/ace_music/agent.py` — update the Stage 5 OutputInput construction (around line 192-199):

Change:
```python
        out_input = OutputInput(
            audio=processed,
            style=style_output,
            seed=seed,
            lyrics_text=lyrics_output.formatted_lyrics if lyrics_output else "",
            description=input_data.description,
            output_dir=input_data.output_dir,
        )
```

To:
```python
        out_input = OutputInput(
            audio=processed,
            style=style_output,
            seed=seed,
            lyrics_text=lyrics_output.formatted_lyrics if lyrics_output else "",
            description=input_data.description,
            output_dir=input_data.output_dir,
            output_config=input_data.output_config,
        )
```

- [ ] **Step 5: Update configs/default.yaml output section**

Edit `configs/default.yaml` — replace the `output:` section (lines 38-40):

```yaml
output:
  save_dir: "./output"
  include_metadata: true
  naming: "nested"                    # "nested" (dev) or "flat" (production/Obsidian)
  filename_template: "{slug}_{date}_{seq:03d}"
  # Uncomment for Obsidian integration:
  # obsidian_base: "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/AI/outputs/music"
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_pipeline.py::TestPipelineWithOutputConfig -v`
Expected: PASS.

- [ ] **Step 7: Run full test suite**

Run: `pytest tests/ -q --tb=short`
Expected: All tests passing.

- [ ] **Step 8: Commit**

```bash
git add src/ace_music/schemas/pipeline.py src/ace_music/agent.py configs/default.yaml tests/test_pipeline.py
git commit -m "feat(pipeline): wire OutputConfig through PipelineInput to OutputWorker"
```

---

## Task 4: Dark Suspense Preset (P1)

**Files:**
- Modify: `configs/presets/cinematic.yaml`
- Modify: `tests/test_preset_resolver.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_preset_resolver.py`:

```python
class TestDarkSuspensePreset:
    @pytest.mark.asyncio
    async def test_dark_suspense_resolves_by_id(self):
        """dark_suspense preset should be resolvable by exact ID."""
        resolver = PresetResolver()
        match = await resolver.resolve("dark_suspense")
        assert match is not None
        assert match.preset.id == "dark_suspense"
        assert match.confidence == 1.0
        assert match.match_method == "exact_id"

    @pytest.mark.asyncio
    async def test_dark_suspense_has_correct_params(self):
        """dark_suspense should have 40 infer steps and electronic genre."""
        resolver = PresetResolver()
        match = await resolver.resolve("dark_suspense")
        assert match is not None
        preset = match.preset
        assert preset.infer_step == 40
        assert preset.guidance_scale == 15.0
        assert "electronic" in preset.genres

    @pytest.mark.asyncio
    async def test_dark_suspense_fuzzy_match(self):
        """Searching for suspense/dark keywords should find dark_suspense."""
        resolver = PresetResolver()
        match = await resolver.resolve("dark suspense thriller")
        assert match is not None
        assert match.preset.id == "dark_suspense"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_preset_resolver.py::TestDarkSuspensePreset -v`
Expected: FAIL — `assert match is not None` fails because `dark_suspense` preset does not exist.

- [ ] **Step 3: Add dark_suspense preset to cinematic.yaml**

Edit `configs/presets/cinematic.yaml` — append after the `cinematic_action` preset (after line 43):

```yaml

  - id: dark_suspense
    name: "暗黑悬疑"
    description: "悬疑氛围音乐，紧张低频，电子合成器，适合金融惊悚场景"
    prompt: "suspense, dark, tension, low frequency, electronic synthesizer, thriller, ominous"
    guidance_scale: 15.0
    omega_scale: 10.0
    infer_step: 40
    genres: ["electronic"]
    mood: ["dark"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_preset_resolver.py::TestDarkSuspensePreset -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -q --tb=short`
Expected: All tests passing.

- [ ] **Step 6: Commit**

```bash
git add configs/presets/cinematic.yaml tests/test_preset_resolver.py
git commit -m "feat(presets): add dark_suspense preset for thriller/suspense scenes"
```

---

## Task 5: MiniMax Provider (P2)

**Files:**
- Create: `src/ace_music/providers/minimax.py`
- Modify: `src/ace_music/providers/__init__.py`
- Modify: `tests/test_providers.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_providers.py`:

```python
from ace_music.providers.minimax import MiniMaxProvider


class TestMiniMaxProvider:
    def test_init_requires_api_key(self):
        """MiniMax provider should require an API key."""
        import os

        original = os.environ.pop("MINIMAX_API_KEY", None)
        try:
            with pytest.raises(ValueError, match="API key"):
                MiniMaxProvider()
        finally:
            if original:
                os.environ["MINIMAX_API_KEY"] = original

    def test_init_with_explicit_key(self):
        """Explicit API key should work without env var."""
        provider = MiniMaxProvider(api_key="test-key")
        assert provider.name == "minimax"

    def test_init_from_env_var(self):
        """API key from environment variable should work."""
        import os

        os.environ["MINIMAX_API_KEY"] = "env-test-key"
        try:
            provider = MiniMaxProvider()
            assert provider.name == "minimax"
        finally:
            del os.environ["MINIMAX_API_KEY"]

    @pytest.mark.asyncio
    async def test_complete_sends_correct_payload(self):
        """complete() should call the MiniMax API with correct format."""
        provider = MiniMaxProvider(api_key="test-key")
        messages = [
            ChatMessage(role="system", content="You are a music planner."),
            ChatMessage(role="user", content="Plan ambient music."),
        ]

        import json
        from unittest.mock import AsyncMock, patch

        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Ambient plan: soft pads, slow tempo"}}],
            "model": "MiniMax-Text-01",
            "usage": {"total_tokens": 50},
        }
        mock_response.raise_for_status = lambda: None

        with patch("httpx.AsyncClient") as mock_client:
            instance = AsyncMock()
            instance.post.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = instance

            result = await provider.complete(messages)
            assert result.content == "Ambient plan: soft pads, slow tempo"
            assert result.model == "MiniMax-Text-01"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_providers.py::TestMiniMaxProvider -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ace_music.providers.minimax'`

- [ ] **Step 3: Implement MiniMaxProvider**

```python
# src/ace_music/providers/minimax.py
"""MiniMax LLM provider implementation.

Uses the OpenAI-compatible API format for MiniMax models.
"""

import logging
import os
from typing import Any

import httpx

from .base import ChatMessage, ChatResponse

logger = logging.getLogger(__name__)

MINIMAX_API_URL = "https://api.minimax.chat/v1/chat/completions"
MINIMAX_DEFAULT_MODEL = "MiniMax-Text-01"


class MiniMaxProvider:
    """MiniMax LLM provider using OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = MINIMAX_DEFAULT_MODEL,
        base_url: str = MINIMAX_API_URL,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("MINIMAX_API_KEY")
        if not self._api_key:
            raise ValueError(
                "MiniMax API key required. Pass api_key or set MINIMAX_API_KEY env var."
            )
        self._model = model
        self._base_url = base_url
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "minimax"

    async def _call_api(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Make the actual HTTP call to the MiniMax API."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(self._base_url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

    async def complete(self, messages: list[ChatMessage], **kwargs) -> ChatResponse:
        """Generate a chat completion via MiniMax API."""
        payload = {
            "model": kwargs.get("model", self._model),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2048),
        }

        try:
            result = await self._call_api(payload)
        except Exception as e:
            raise RuntimeError(f"MiniMax API request failed: {e}") from e

        choices = result.get("choices")
        if not choices or not isinstance(choices, list):
            raise RuntimeError(f"MiniMax returned unexpected response: {result}")

        message = choices[0].get("message", {})
        content = message.get("content")
        if not content:
            raise RuntimeError(f"MiniMax returned empty content: {result}")

        return ChatResponse(
            content=content,
            model=result.get("model", self._model),
            usage=result.get("usage", {}),
        )
```

- [ ] **Step 4: Re-export from providers/__init__.py**

Edit `src/ace_music/providers/__init__.py`:

Add import after line 4:
```python
from .minimax import MiniMaxProvider
```

Add `"MiniMaxProvider"` to the `__all__` list (alphabetically):
```python
    "DeepSeekProvider",
    "FeatureRouter",
    "MiniMaxProvider",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_providers.py::TestMiniMaxProvider -v`
Expected: All 4 tests PASS.

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -q --tb=short`
Expected: All tests passing.

- [ ] **Step 7: Commit**

```bash
git add src/ace_music/providers/minimax.py src/ace_music/providers/__init__.py tests/test_providers.py
git commit -m "feat(providers): add MiniMax LLM provider with OpenAI-compatible API"
```

---

## Task 6: Provider Config + Agent Wiring (P2)

**Files:**
- Modify: `src/ace_music/agent.py`
- Modify: `configs/default.yaml`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pipeline.py`:

```python
from ace_music.providers.deepseek import DeepSeekProvider
from ace_music.providers.router import FeatureRouter


class TestAgentWithFeatureRouter:
    def test_agent_accepts_feature_router(self):
        """MusicAgent should accept an optional FeatureRouter."""
        provider = DeepSeekProvider(api_key="test-key")
        router = FeatureRouter(default=provider)
        agent = MusicAgent(
            generator_config=GeneratorConfig(mock_mode=True),
            feature_router=router,
        )
        assert agent._feature_router is not None

    def test_agent_works_without_feature_router(self):
        """MusicAgent should work without a FeatureRouter (backward compatible)."""
        agent = MusicAgent(generator_config=GeneratorConfig(mock_mode=True))
        assert agent._feature_router is None

    @pytest.mark.asyncio
    async def test_pipeline_runs_with_router(self, tmp_path):
        """Pipeline should work end-to-end with a FeatureRouter configured."""
        provider = DeepSeekProvider(api_key="test-key")
        router = FeatureRouter(default=provider)
        agent = MusicAgent(
            generator_config=GeneratorConfig(mock_mode=True),
            feature_router=router,
        )
        result = await agent.run(
            PipelineInput(
                description="test with router",
                duration_seconds=5.0,
                output_dir=str(tmp_path),
            )
        )
        assert result.audio_path
        assert Path(result.audio_path).exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline.py::TestAgentWithFeatureRouter -v`
Expected: FAIL — `MusicAgent.__init__()` got an unexpected keyword argument `feature_router`.

- [ ] **Step 3: Add feature_router to MusicAgent.__init__()**

Edit `src/ace_music/agent.py`:

Add import after line 26:
```python
from ace_music.providers.router import FeatureRouter
```

Modify `__init__` method (lines 43-53) to accept `feature_router`:

```python
    def __init__(
        self,
        generator_config: GeneratorConfig | None = None,
        preset_resolver: PresetResolver | None = None,
        feature_router: FeatureRouter | None = None,
    ) -> None:
        self._lyrics_planner = LyricsPlanner()
        self._style_planner = StylePlanner()
        self._generator = ACEStepGenerator(generator_config)
        self._post_processor = PostProcessor()
        self._output_worker = OutputWorker()
        self._preset_resolver = preset_resolver or PresetResolver()
        self._feature_router = feature_router
```

Note: Only the `feature_router` parameter and `self._feature_router` line are new. The rest of `__init__` stays the same.

- [ ] **Step 4: Add provider config section to configs/default.yaml**

Edit `configs/default.yaml` — append after the `output:` section:

```yaml

# LLM Provider configuration (optional — pipeline works without LLM)
# Uncomment and configure when using LLM-assisted lyrics/style planning:
# providers:
#   default: deepseek
#   feature_overrides:
#     lyrics_planning: deepseek
#     style_planning: minimax
#   deepseek:
#     model: deepseek-chat
#     base_url: https://api.deepseek.com/v1/chat/completions
#   minimax:
#     model: MiniMax-Text-01
#     base_url: https://api.minimax.chat/v1/chat/completions
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_pipeline.py::TestAgentWithFeatureRouter -v`
Expected: All 3 tests PASS.

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -q --tb=short`
Expected: All tests passing.

- [ ] **Step 7: Commit**

```bash
git add src/ace_music/agent.py configs/default.yaml tests/test_pipeline.py
git commit -m "feat(agent): accept optional FeatureRouter for multi-provider LLM support"
```

---

## Task 7: DirectorBridge Enhancement (P3)

**Files:**
- Modify: `src/ace_music/bridge/__init__.py`
- Modify: `src/ace_music/bridge/director_bridge.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_pipeline.py`:

```python
from ace_music.bridge import DirectorBridge


class TestDirectorBridgeEnhanced:
    def test_request_accepts_scene_description(self):
        """Request should accept optional scene_description field."""
        req = DirectorBridge.Request(
            scene_id="scene_001",
            mood="suspenseful",
            duration_seconds=30.0,
            scene_description="A detective examines evidence in a dimly lit room",
        )
        assert req.scene_description == "A detective examines evidence in a dimly lit room"

    def test_request_accepts_intensity(self):
        """Request should accept optional intensity field (0.0-1.0)."""
        req = DirectorBridge.Request(
            scene_id="scene_002",
            mood="tense",
            duration_seconds=30.0,
            intensity=0.8,
        )
        assert req.intensity == 0.8

    def test_request_accepts_preset_name(self):
        """Request should accept optional preset_name for style preset selection."""
        req = DirectorBridge.Request(
            scene_id="scene_003",
            mood="dark",
            duration_seconds=30.0,
            preset_name="dark_suspense",
        )
        assert req.preset_name == "dark_suspense"

    def test_request_accepts_is_instrumental(self):
        """Request should accept is_instrumental flag."""
        req = DirectorBridge.Request(
            scene_id="scene_004",
            mood="calm",
            duration_seconds=60.0,
            is_instrumental=True,
        )
        assert req.is_instrumental is True

    def test_response_includes_success_field(self):
        """Response should include a success flag."""
        resp = DirectorBridge.Response(
            audio_path="/tmp/test.wav",
            duration_seconds=30.0,
            scene_id="scene_001",
            success=True,
        )
        assert resp.success is True

    def test_response_includes_error_field(self):
        """Response should include optional error message for failures."""
        resp = DirectorBridge.Response(
            audio_path="",
            duration_seconds=0.0,
            scene_id="scene_001",
            success=False,
            error="Generation failed: GPU out of memory",
        )
        assert resp.success is False
        assert resp.error == "Generation failed: GPU out of memory"

    def test_request_to_pipeline_maps_new_fields(self):
        """Conversion should map preset_name, is_instrumental, and scene_description."""
        from ace_music.bridge.director_bridge import request_to_pipeline_input

        req = DirectorBridge.Request(
            scene_id="scene_005",
            mood="dark",
            duration_seconds=30.0,
            preset_name="dark_suspense",
            is_instrumental=True,
            scene_description="Night cityscape with rain",
        )
        pipeline_input = request_to_pipeline_input(req)
        assert pipeline_input.preset_name == "dark_suspense"
        assert pipeline_input.is_instrumental is True
        assert "rain" in pipeline_input.description
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline.py::TestDirectorBridgeEnhanced -v`
Expected: FAIL — `DirectorBridge.Request.__init__()` got an unexpected keyword argument `scene_description`.

- [ ] **Step 3: Enhance DirectorBridge Request**

Edit `src/ace_music/bridge/__init__.py` — add new fields to the `Request` class (after `seed` field, line 31):

```python
        scene_description: str | None = Field(
            default=None, description="Full scene description for context-aware music generation"
        )
        intensity: float | None = Field(
            default=None, ge=0.0, le=1.0, description="Emotional intensity (0.0=subtle, 1.0=extreme)"
        )
        preset_name: str | None = Field(
            default=None, description="Style preset name to use (e.g. 'dark_suspense')"
        )
        is_instrumental: bool = Field(
            default=False, description="Generate instrumental (no vocals)"
        )
```

- [ ] **Step 4: Enhance DirectorBridge Response**

Edit `src/ace_music/bridge/__init__.py` — add new fields to the `Response` class (after `scene_id` field, line 43):

```python
        success: bool = Field(default=True, description="Whether generation succeeded")
        error: str | None = Field(
            default=None, description="Error message if generation failed"
        )
```

- [ ] **Step 5: Update conversion functions**

Replace `src/ace_music/bridge/director_bridge.py` entirely:

```python
"""DirectorBridge: auto-director integration adapter.

Converts DirectorBridge.Request into PipelineInput and
PipelineOutput into DirectorBridge.Response.
"""

from ace_music.bridge import DirectorBridge
from ace_music.schemas.pipeline import PipelineInput, PipelineOutput


def request_to_pipeline_input(req: DirectorBridge.Request) -> PipelineInput:
    """Convert a DirectorBridge.Request to PipelineInput."""
    description_parts: list[str] = []
    if req.style_reference:
        description_parts.append(req.style_reference)
    elif req.scene_description:
        description_parts.append(req.scene_description)
    else:
        description_parts.append(f"{req.mood} background music")

    if req.scene_description and req.style_reference:
        description_parts.append(req.scene_description)

    return PipelineInput(
        description=" ".join(description_parts),
        lyrics=req.lyrics_hint,
        duration_seconds=req.duration_seconds,
        mood=req.mood,
        tempo_preference=req.tempo_preference,
        output_format=req.output_format,
        seed=req.seed,
        preset_name=req.preset_name,
        is_instrumental=req.is_instrumental,
    )


def pipeline_output_to_response(
    output: PipelineOutput, req: DirectorBridge.Request
) -> DirectorBridge.Response:
    """Convert PipelineOutput to DirectorBridge.Response."""
    return DirectorBridge.Response(
        audio_path=output.audio_path,
        duration_seconds=output.duration_seconds,
        format=output.format,
        metadata=output.metadata,
        scene_id=req.scene_id,
        success=True,
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_pipeline.py::TestDirectorBridgeEnhanced -v`
Expected: All 7 tests PASS.

- [ ] **Step 7: Run full test suite (including existing DirectorBridge tests)**

Run: `pytest tests/ -q --tb=short`
Expected: All tests passing. Existing `TestDirectorBridge` tests still pass because all new fields have defaults.

- [ ] **Step 8: Commit**

```bash
git add src/ace_music/bridge/__init__.py src/ace_music/bridge/director_bridge.py tests/test_pipeline.py
git commit -m "feat(bridge): enhance DirectorBridge with scene context, intensity, preset, and error handling"
```

---

## E2E Verification

After all tasks are complete, run the full verification:

```bash
# 1. Unit tests — verify no regressions from 113 baseline
cd /Users/shockang/novel/ace-music
pytest tests/ -q --tb=short 2>&1 | tail -5
# Expected: All tests passing (120+ with new tests)

# 2. GPU status check
ssh -i ~/.ssh/id_ed25519_win -o ConnectTimeout=5 shockang@100.69.202.122 "hostname"

# 3. Generate test music with dark_suspense preset
python3 scripts/run_ace_step.sh --preset dark_suspense --duration 30 --output /tmp/ace_music_v2_opt.wav

# 4. Verify output
file /tmp/ace_music_v2_opt.wav
ls -la /tmp/ace_music_v2_opt.wav
# Expected: WAV/PCM 48kHz, ~5.5MB

# 5. (If Obsidian output configured) Verify formal output
ls -la ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/AI/outputs/music/
# Expected: Files with descriptive names like dark_suspense_20260414_001.wav
```

### Acceptance Criteria

- [ ] Unit tests: all passing, no regressions from 113 baseline
- [ ] Music generation: WAV format, ~5.5MB, <60s on RTX 3090 Ti
- [ ] Flat naming: files saved with descriptive names when OutputConfig.naming="flat"
- [ ] dark_suspense preset: resolves by ID and fuzzy match, generates correct style
- [ ] MiniMax provider: instantiates, follows ChatProvider protocol, handles errors
- [ ] DirectorBridge: new Request fields (scene_description, intensity, preset_name, is_instrumental) validated
- [ ] DirectorBridge: new Response fields (success, error) validated
- [ ] Existing pipeline: works unchanged without any new features configured
