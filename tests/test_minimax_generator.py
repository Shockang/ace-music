"""Tests for MiniMax music generation tool."""

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError

from ace_music.errors import GenerationFailedError
from ace_music.schemas.audio import AudioOutput
from ace_music.tools.minimax_generator import (
    MiniMaxMusicConfig,
    MiniMaxMusicGenerator,
    MiniMaxMusicInput,
    RateLimiter,
)


class TestMiniMaxMusicInput:
    def test_defaults(self):
        inp = MiniMaxMusicInput(description="test song")
        assert inp.mode == "instrumental"
        assert inp.lyrics is None
        assert inp.ref_audio is None
        assert inp.output_dir == "./output"

    def test_lyrics_mode(self):
        inp = MiniMaxMusicInput(
            description="pop ballad",
            mode="lyrics",
            lyrics="[verse]\nHello world",
        )
        assert inp.mode == "lyrics"
        assert inp.lyrics == "[verse]\nHello world"

    def test_invalid_mode_raises(self):
        with pytest.raises(ValidationError):
            MiniMaxMusicInput(description="test", mode="disco")

    def test_cover_mode_with_ref_audio(self):
        inp = MiniMaxMusicInput(
            description="rock cover",
            mode="cover",
            ref_audio="/path/to/song.mp3",
        )
        assert inp.mode == "cover"
        assert inp.ref_audio == "/path/to/song.mp3"

    def test_description_max_length(self):
        long_desc = "x" * 2001
        with pytest.raises(ValidationError):
            MiniMaxMusicInput(description=long_desc)

    def test_lyrics_max_length(self):
        long_lyrics = "x" * 3501
        with pytest.raises(ValidationError):
            MiniMaxMusicInput(description="test", lyrics=long_lyrics)


class TestMiniMaxMusicConfig:
    def test_defaults(self):
        config = MiniMaxMusicConfig(api_key="test-key")
        assert config.base_url == "https://api.minimaxi.com/v1/music_generation"
        assert config.timeout == 120.0
        assert config.rate_limit_per_minute == 5
        assert config.sample_rate == 44100
        assert config.audio_format == "mp3"

    def test_from_env(self):
        with patch.dict("os.environ", {"MINIMAX_API_KEY": "env-key"}):
            config = MiniMaxMusicConfig()
            assert config.api_key == "env-key"

    def test_missing_key_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            import os

            if "MINIMAX_API_KEY" in os.environ:
                del os.environ["MINIMAX_API_KEY"]
            with pytest.raises(ValueError, match="MINIMAX_API_KEY"):
                MiniMaxMusicConfig(api_key=None)


class TestRateLimiter:
    def test_acquire_within_limit(self):
        limiter = RateLimiter(max_calls=5, period_seconds=60.0)
        start = time.monotonic()
        asyncio.run(limiter.acquire())
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    def test_acquire_tracks_calls(self):
        limiter = RateLimiter(max_calls=3, period_seconds=60.0)
        asyncio.run(limiter.acquire())
        asyncio.run(limiter.acquire())
        assert len(limiter._timestamps) == 2

    def test_acquire_waits_when_limit_reached(self):
        limiter = RateLimiter(max_calls=2, period_seconds=1.0)
        asyncio.run(limiter.acquire())
        asyncio.run(limiter.acquire())
        start = time.monotonic()
        asyncio.run(limiter.acquire())
        elapsed = time.monotonic() - start
        assert elapsed >= 0.5

    def test_old_calls_expire(self):
        limiter = RateLimiter(max_calls=2, period_seconds=0.1)
        asyncio.run(limiter.acquire())
        asyncio.run(limiter.acquire())
        time.sleep(0.15)
        start = time.monotonic()
        asyncio.run(limiter.acquire())
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    def test_acquire_does_not_double_count_after_wait(self):
        """After waiting through a full window the limiter should hold exactly
        max_calls timestamps, not max_calls + 1."""
        limiter = RateLimiter(max_calls=2, period_seconds=0.2)
        asyncio.run(limiter.acquire())
        asyncio.run(limiter.acquire())
        asyncio.run(limiter.acquire())  # waits for window to slide
        assert len(limiter._timestamps) <= 2


class TestMiniMaxMusicGenerator:
    def test_tool_properties(self):
        config = MiniMaxMusicConfig(api_key="test-key")
        gen = MiniMaxMusicGenerator(config)
        assert gen.name == "minimax_generator"
        assert gen.input_schema == MiniMaxMusicInput
        assert gen.output_schema == AudioOutput
        assert gen.is_read_only is False
        assert gen.is_concurrency_safe is False

    def test_build_payload_instrumental(self):
        config = MiniMaxMusicConfig(api_key="test-key")
        gen = MiniMaxMusicGenerator(config)
        inp = MiniMaxMusicInput(description="jazz piano, summer vibes")
        payload = gen._build_payload(inp)
        assert payload["model"] == "music-2.6"
        assert payload["prompt"] == "jazz piano, summer vibes"
        assert payload["is_instrumental"] is True
        assert payload["audio_setting"]["sample_rate"] == 44100
        assert payload["audio_setting"]["format"] == "mp3"
        assert payload["output_format"] == "url"

    def test_build_payload_lyrics_with_optimizer(self):
        config = MiniMaxMusicConfig(api_key="test-key")
        gen = MiniMaxMusicGenerator(config)
        inp = MiniMaxMusicInput(description="chinese folk", mode="lyrics")
        payload = gen._build_payload(inp)
        assert payload["is_instrumental"] is False
        assert payload.get("lyrics_optimizer") is True
        assert "lyrics" not in payload

    def test_build_payload_lyrics_with_text(self):
        config = MiniMaxMusicConfig(api_key="test-key")
        gen = MiniMaxMusicGenerator(config)
        inp = MiniMaxMusicInput(
            description="pop song", mode="lyrics", lyrics="[verse]\nHello"
        )
        payload = gen._build_payload(inp)
        assert payload["lyrics"] == "[verse]\nHello"
        assert "lyrics_optimizer" not in payload

    def test_build_payload_cover(self):
        config = MiniMaxMusicConfig(api_key="test-key")
        gen = MiniMaxMusicGenerator(config)
        inp = MiniMaxMusicInput(
            description="rock version", mode="cover", ref_audio="/tmp/song.mp3"
        )
        payload = gen._build_payload(inp)
        assert payload["model"] == "music-cover"
        assert payload["ref_audio"] == "/tmp/song.mp3"

    @pytest.mark.asyncio
    async def test_execute_instrumental(self, tmp_path):
        config = MiniMaxMusicConfig(api_key="test-key")
        gen = MiniMaxMusicGenerator(config)

        mock_response = {
            "data": {"audio_url": "https://cdn.example.com/audio.mp3"},
            "base_resp": {"status_code": 0},
        }

        with (
            patch.object(gen, "_call_api", new_callable=AsyncMock, return_value=mock_response),
            patch.object(gen, "_download_audio", new_callable=AsyncMock) as mock_dl,
        ):
            audio_path = str(tmp_path / "test.mp3")
            Path(audio_path).write_bytes(b"fake mp3 data")
            mock_dl.return_value = audio_path

            inp = MiniMaxMusicInput(
                description="light jazz", output_dir=str(tmp_path)
            )
            result = await gen.execute(inp)

        assert isinstance(result, AudioOutput)
        assert result.format == "mp3"
        assert result.sample_rate == 44100

    @pytest.mark.asyncio
    async def test_execute_api_error_raises(self, tmp_path):
        config = MiniMaxMusicConfig(api_key="test-key")
        gen = MiniMaxMusicGenerator(config)

        with patch.object(gen, "_call_api", new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = RuntimeError("API error")
            inp = MiniMaxMusicInput(description="test", output_dir=str(tmp_path))
            with pytest.raises(GenerationFailedError, match="API error"):
                await gen.execute(inp)

    @pytest.mark.asyncio
    async def test_execute_bad_response_raises(self, tmp_path):
        config = MiniMaxMusicConfig(api_key="test-key")
        gen = MiniMaxMusicGenerator(config)

        with patch.object(
            gen, "_call_api", new_callable=AsyncMock, return_value={"bad": "data"}
        ):
            inp = MiniMaxMusicInput(description="test", output_dir=str(tmp_path))
            with pytest.raises(GenerationFailedError, match="audio_url"):
                await gen.execute(inp)

    @pytest.mark.asyncio
    async def test_execute_http_status_error_surfaces_status(self, tmp_path):
        """An HTTPStatusError from MiniMax should map to GenerationFailedError
        with the actual status code in the message."""
        config = MiniMaxMusicConfig(api_key="test-key")
        gen = MiniMaxMusicGenerator(config)

        request = httpx.Request("POST", config.base_url)
        response = MagicMock(spec=httpx.Response)
        response.status_code = 429
        response.text = "Too Many Requests"
        http_err = httpx.HTTPStatusError("429", request=request, response=response)

        with patch.object(gen, "_call_api", new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = http_err
            inp = MiniMaxMusicInput(description="test", output_dir=str(tmp_path))
            with pytest.raises(GenerationFailedError, match="429"):
                await gen.execute(inp)

    @pytest.mark.asyncio
    async def test_execute_business_error_surfaces_message(self, tmp_path):
        """`base_resp.status_code != 0` should surface the actual reason
        instead of a misleading 'missing audio_url' message."""
        config = MiniMaxMusicConfig(api_key="test-key")
        gen = MiniMaxMusicGenerator(config)

        bad_business = {
            "data": {},
            "base_resp": {"status_code": 1004, "status_msg": "quota exhausted"},
        }
        with patch.object(
            gen, "_call_api", new_callable=AsyncMock, return_value=bad_business
        ):
            inp = MiniMaxMusicInput(description="test", output_dir=str(tmp_path))
            with pytest.raises(GenerationFailedError, match="quota exhausted"):
                await gen.execute(inp)

    @pytest.mark.asyncio
    async def test_execute_cover_missing_ref_audio_raises(self, tmp_path):
        """Cover mode with a non-existent ref_audio should fail fast with a
        clear error rather than letting MiniMax 400 us."""
        config = MiniMaxMusicConfig(api_key="test-key")
        gen = MiniMaxMusicGenerator(config)

        inp = MiniMaxMusicInput(
            description="cover test",
            mode="cover",
            ref_audio=str(tmp_path / "does_not_exist.mp3"),
            output_dir=str(tmp_path),
        )
        with pytest.raises(GenerationFailedError, match="ref_audio not found"):
            await gen.execute(inp)
