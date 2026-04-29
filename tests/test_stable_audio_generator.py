"""Tests for Stable Audio generation tool."""
from unittest.mock import AsyncMock, patch

import pytest

from ace_music.errors import GenerationFailedError
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

    @pytest.mark.asyncio
    async def test_execute_raises_for_nonterminal_poll_response(self, tmp_path):
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
                return_value={"status": "processing"},
            ),
            pytest.raises(GenerationFailedError, match="not ready"),
        ):
            await gen.execute(StableAudioInput(description="test", output_dir=str(tmp_path)))

    @pytest.mark.asyncio
    async def test_execute_raises_for_missing_api_key(self, tmp_path):
        with (
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(ValueError, match="Stability API key required"),
        ):
            gen = StableAudioGenerator(config=StableAudioConfig(api_key=""))
            await gen.execute(
                StableAudioInput(description="test", output_dir=str(tmp_path))
            )

    @pytest.mark.asyncio
    async def test_download_audio_rejects_non_audio_body(self, tmp_path):
        gen = StableAudioGenerator(StableAudioConfig(api_key="test-key"))

        with patch("ace_music.tools.stable_audio_generator.httpx.AsyncClient.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.raise_for_status = lambda: None
            mock_response.content = b"<html>not audio</html>"
            mock_get.return_value = mock_response

            with pytest.raises(GenerationFailedError, match="not a recognized audio file"):
                await gen._download_audio("https://cdn.example.com/audio.mp3", str(tmp_path))

    def test_extract_audio_url_rejects_nonterminal_payload(self):
        gen = StableAudioGenerator(StableAudioConfig(api_key="test-key"))

        with pytest.raises(GenerationFailedError, match="not ready"):
            gen._extract_audio_url({"status": "processing"})
