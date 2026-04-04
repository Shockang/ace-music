"""Tests for ACEStepGenerator (mock mode)."""

import os

import pytest

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
