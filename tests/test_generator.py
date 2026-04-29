"""Tests for ACEStepGenerator (mock mode)."""

import builtins
import os
from pathlib import Path

import pytest

from ace_music.errors import DependencyUnavailableError, GPUUnavailableError
from ace_music.mcp.config import ModelConfig
from ace_music.mcp.loader import load_generator_config
from ace_music.schemas.audio import AudioOutput
from ace_music.schemas.lyrics import LyricsOutput
from ace_music.schemas.style import StyleOutput
from ace_music.tools.generator import ACEStepGenerator, GenerationInput, GeneratorConfig


@pytest.fixture
def generator():
    config = GeneratorConfig(mock_mode=True)
    return ACEStepGenerator(config)


@pytest.fixture
def sample_input(tmp_path):
    return GenerationInput(
        lyrics=LyricsOutput(formatted_lyrics="[verse]\nTest lyrics"),
        style=StyleOutput(prompt="pop, electronic"),
        audio_duration=5.0,
        seed=42,
        output_dir=str(tmp_path),
    )


class TestGeneratorProperties:
    def test_name(self, generator):
        assert generator.name == "generator"

    def test_is_not_read_only(self, generator):
        assert generator.is_read_only is False

    def test_is_not_concurrency_safe(self, generator):
        assert generator.is_concurrency_safe is False

    def test_generator_config_model_variant_defaults_to_2b(self):
        config = GeneratorConfig()
        assert config.model_variant == "2b"

    def test_load_generator_config_accepts_model_variant(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "model:\n"
            "  checkpoint_dir: /models/ace-step\n"
            "  model_variant: xl-sft\n"
            "  cpu_offload: true\n"
        )

        config = load_generator_config(config_path)

        assert config.model_variant == "xl-sft"
        assert config.checkpoint_dir == "/models/ace-step"
        assert config.cpu_offload is True

    def test_model_config_resolved_checkpoint_dir_suffixes_xl_variants(self):
        config = ModelConfig(
            checkpoint_dir="/models/ace-step",
            model_variant="xl-sft",
        )

        assert config.resolved_checkpoint_dir == "/models/ace-step/xl-sft"


class TestMockGeneration:
    @pytest.mark.asyncio
    async def test_mock_generates_wav(self, generator, sample_input):
        result = await generator.execute(sample_input)
        assert isinstance(result, AudioOutput)
        assert result.format == "wav"
        assert result.duration_seconds == 5.0
        assert os.path.exists(result.file_path)

    @pytest.mark.asyncio
    async def test_mock_seed_reproducible(self, generator, sample_input):
        result1 = await generator.execute(sample_input)
        result2 = await generator.execute(sample_input)
        assert result1.duration_seconds == result2.duration_seconds
        assert result1.sample_rate == result2.sample_rate

    @pytest.mark.asyncio
    async def test_mock_creates_output_dir(self, generator, tmp_path):
        out_dir = tmp_path / "nested" / "output"
        inp = GenerationInput(
            lyrics=LyricsOutput(formatted_lyrics=""),
            style=StyleOutput(prompt="ambient"),
            audio_duration=5.0,
            seed=1,
            output_dir=str(out_dir),
        )
        result = await generator.execute(inp)
        assert out_dir.exists()
        assert os.path.exists(result.file_path)

    @pytest.mark.asyncio
    async def test_instrumental_generation(self, generator, tmp_path):
        inp = GenerationInput(
            lyrics=LyricsOutput(formatted_lyrics="", is_instrumental=True),
            style=StyleOutput(prompt="ambient, atmospheric"),
            audio_duration=10.0,
            output_dir=str(tmp_path),
        )
        result = await generator.execute(inp)
        assert result.duration_seconds == 10.0


class TestValidateInput:
    def test_validate_generation_input(self, generator, tmp_path):
        data = {
            "lyrics": {"formatted_lyrics": "[verse]\nTest", "is_instrumental": False},
            "style": {"prompt": "pop"},
            "audio_duration": 30.0,
            "output_dir": str(tmp_path),
        }
        result = generator.validate_input(data)
        assert result.audio_duration == 30.0


class TestProductionModeDiagnostics:
    def test_missing_acestep_dependency_is_explicit(self, monkeypatch):
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "acestep.pipeline_ace_step":
                raise ImportError("No module named 'acestep'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        generator = ACEStepGenerator(GeneratorConfig(mock_mode=False, require_cuda=False))

        with pytest.raises(DependencyUnavailableError) as exc:
            generator._ensure_pipeline()

        assert "ACE-Step" in str(exc.value)
        assert "mock" in str(exc.value).lower()

    def test_missing_acestep_can_explicitly_fallback_to_mock(self, monkeypatch):
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "acestep.pipeline_ace_step":
                raise ImportError("No module named 'acestep'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        generator = ACEStepGenerator(
            GeneratorConfig(
                mock_mode=False,
                require_cuda=False,
                allow_mock_fallback=True,
            )
        )

        generator._ensure_pipeline()

        assert generator._pipeline == "mock"


class TestModelVariantBehavior:
    def test_xl_model_variant_resolves_checkpoint_subdir(self):
        generator = ACEStepGenerator(
            GeneratorConfig(
                checkpoint_dir="/models/ace-step",
                model_variant="xl-base",
                mock_mode=False,
            )
        )

        resolved = generator._resolve_checkpoint_dir()

        assert resolved == Path("/models/ace-step/xl-base")

    def test_xl_model_variant_requires_sufficient_vram(self):
        generator = ACEStepGenerator(
            GeneratorConfig(
                model_variant="xl-turbo",
                cpu_offload=False,
                mock_mode=False,
            )
        )

        with pytest.raises(GPUUnavailableError) as exc:
            generator._validate_model_variant_vram(available_vram_gb=19.5)

        assert "xl-turbo" in str(exc.value)
        assert "20GB" in str(exc.value)
