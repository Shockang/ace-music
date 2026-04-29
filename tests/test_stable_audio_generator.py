"""Tests for Stable Audio generation tool."""
from unittest.mock import AsyncMock, patch

import pytest

from ace_music.schemas.audio import AudioOutput
from ace_music.tools.stable_audio_generator import (
    StableAudioConfig,
    StableAudioGenerator,
    StableAudioInput,
)


class TestStableAudioInput:
    def test_defaults(self):
        inp = StableAudioInput(description="tense underscore")
        assert inp.output_dir == "./output"
        assert inp.mode == "instrumental"


class TestStableAudioGenerator:
    def test_tool_properties(self):
        gen = StableAudioGenerator(StableAudioConfig(api_key="test-key"))
        assert gen.name == "stable_audio_generator"
        assert gen.output_schema is AudioOutput
        assert gen.is_read_only is False

    @pytest.mark.asyncio
    async def test_execute_success(self, tmp_path):
        gen = StableAudioGenerator(StableAudioConfig(api_key="test-key"))

        with (
            patch.object(
                gen,
                "_submit_job",
                new_callable=AsyncMock,
                return_value={"id": "job_1"},
            ),
            patch.object(
                gen,
                "_poll_job",
                new_callable=AsyncMock,
                return_value={"audio_url": "https://cdn.example.com/audio.mp3"},
            ),
            patch.object(
                gen,
                "_download_audio",
                new_callable=AsyncMock,
                return_value=str(tmp_path / "out.mp3"),
            ),
        ):
            result = await gen.execute(
                StableAudioInput(description="test", output_dir=str(tmp_path))
            )

        assert isinstance(result, AudioOutput)
        assert result.format == "mp3"
        assert result.file_path == str(tmp_path / "out.mp3")
