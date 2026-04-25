"""MiniMax Music API generator.

Calls the MiniMax Music 2.6 / music-cover API for cloud-based music generation.
Supports three modes: instrumental, lyrics (with AI auto-write), and cover.
Rate-limited to 5 requests per minute as per MiniMax Token Plan quota.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from ace_music.errors import GenerationFailedError
from ace_music.schemas.audio import AudioOutput
from ace_music.tools.base import MusicTool

logger = logging.getLogger(__name__)

MINIMAX_MUSIC_URL = "https://api.minimaxi.com/v1/music_generation"


class MiniMaxMusicInput(BaseModel):
    """Input for MiniMax music generation."""

    description: str = Field(description="Music description/prompt", max_length=2000)
    mode: Literal["instrumental", "lyrics", "cover"] = Field(
        default="instrumental",
        description="Generation mode: instrumental, lyrics, or cover",
    )
    lyrics: str | None = Field(default=None, max_length=3500)
    ref_audio: str | None = Field(
        default=None, description="Reference audio for cover mode"
    )
    output_dir: str = Field(default="./output")


class MiniMaxMusicConfig(BaseModel):
    """Configuration for MiniMax Music API access."""

    api_key: str | None = Field(default=None)
    base_url: str = MINIMAX_MUSIC_URL
    timeout: float = 120.0
    rate_limit_per_minute: int = 5
    sample_rate: int = 44100
    audio_format: str = "mp3"

    def model_post_init(self, __context: Any) -> None:
        if self.api_key is None:
            self.api_key = os.environ.get("MINIMAX_API_KEY")
        if not self.api_key:
            raise ValueError(
                "MiniMax API key required. Pass api_key or set MINIMAX_API_KEY env var."
            )


class RateLimiter:
    """Sliding-window rate limiter with async-safe locking.

    Releases the lock during sleep so concurrent waiters don't serialize
    their waits, and re-checks the window after waking to avoid double-counting
    timestamps.
    """

    def __init__(self, max_calls: int, period_seconds: float) -> None:
        self._max_calls = max_calls
        self._period = period_seconds
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                self._timestamps = [
                    t for t in self._timestamps if now - t < self._period
                ]
                if len(self._timestamps) < self._max_calls:
                    self._timestamps.append(now)
                    return
                wait_time = self._period - (now - self._timestamps[0])
            if wait_time > 0:
                logger.info("Rate limit reached, waiting %.1fs", wait_time)
                await asyncio.sleep(wait_time)


class MiniMaxMusicGenerator(MusicTool[MiniMaxMusicInput, AudioOutput]):
    """MiniMax Music 2.6 cloud API generator."""

    def __init__(self, config: MiniMaxMusicConfig | None = None) -> None:
        if config is None:
            config = MiniMaxMusicConfig()
        self._config = config
        self._rate_limiter = RateLimiter(
            max_calls=config.rate_limit_per_minute, period_seconds=60.0
        )

    @property
    def name(self) -> str:
        return "minimax_generator"

    @property
    def description(self) -> str:
        return "Generate music using MiniMax Music 2.6 cloud API"

    @property
    def input_schema(self) -> type[MiniMaxMusicInput]:
        return MiniMaxMusicInput

    @property
    def output_schema(self) -> type[AudioOutput]:
        return AudioOutput

    @property
    def is_read_only(self) -> bool:
        return False

    @property
    def is_concurrency_safe(self) -> bool:
        return False

    def _build_payload(self, input_data: MiniMaxMusicInput) -> dict[str, Any]:
        """Build API request payload from input."""
        model = "music-cover" if input_data.mode == "cover" else "music-2.6"
        payload: dict[str, Any] = {
            "model": model,
            "prompt": input_data.description,
            "audio_setting": {
                "sample_rate": self._config.sample_rate,
                "format": self._config.audio_format,
            },
            "output_format": "url",
        }

        if input_data.mode == "instrumental":
            payload["is_instrumental"] = True
        elif input_data.mode == "lyrics":
            payload["is_instrumental"] = False
            if input_data.lyrics:
                payload["lyrics"] = input_data.lyrics
            else:
                payload["lyrics_optimizer"] = True
        elif input_data.mode == "cover":
            payload["is_instrumental"] = False
            if input_data.ref_audio:
                payload["ref_audio"] = input_data.ref_audio

        return payload

    async def _call_api(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Call the MiniMax Music API.

        Note: do not log the request headers (Authorization bearer token) or
        the full payload at any level — the prompt may contain user content
        and the header carries the API key.
        """
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self._config.timeout) as client:
            response = await client.post(
                self._config.base_url, json=payload, headers=headers
            )
            response.raise_for_status()
            return response.json()

    def _extract_audio_url(self, result: dict[str, Any]) -> str:
        """Extract audio download URL from API response.

        MiniMax returns HTTP 200 with `base_resp.status_code != 0` for
        business-logic failures (quota exhausted, content rejected, etc.).
        Surface those before the generic 'missing audio_url' diagnostic so
        operators see the actual cause.
        """
        base_resp = result.get("base_resp") or {}
        status_code = base_resp.get("status_code", 0)
        if status_code != 0:
            status_msg = base_resp.get("status_msg", "unknown error")
            raise GenerationFailedError(
                f"MiniMax API error {status_code}: {status_msg}"
            )

        data = result.get("data") or {}
        url = data.get("audio_url")
        if not url:
            redacted_keys = sorted(result.keys())
            raise GenerationFailedError(
                f"MiniMax response missing audio_url; top-level keys: {redacted_keys}"
            )
        return url

    async def _download_audio(self, url: str, output_dir: str) -> str:
        """Download generated audio from URL to output directory."""
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        filename = (
            f"minimax_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            f".{self._config.audio_format}"
        )
        filepath = out_path / filename

        async with httpx.AsyncClient(timeout=self._config.timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            filepath.write_bytes(response.content)

        return str(filepath)

    async def execute(self, input_data: MiniMaxMusicInput) -> AudioOutput:
        """Generate music via MiniMax Music API."""
        if (
            input_data.mode == "cover"
            and input_data.ref_audio
            and not Path(input_data.ref_audio).is_file()
        ):
            raise GenerationFailedError(
                f"ref_audio not found: {input_data.ref_audio}"
            )

        await self._rate_limiter.acquire()

        payload = self._build_payload(input_data)
        logger.info(
            "MiniMax request: model=%s, mode=%s", payload["model"], input_data.mode
        )

        try:
            result = await self._call_api(payload)
        except httpx.HTTPStatusError as e:
            raise GenerationFailedError(
                f"MiniMax API returned {e.response.status_code}: {e.response.text[:200]}"
            ) from e
        except httpx.HTTPError as e:
            raise GenerationFailedError(
                f"MiniMax Music API request failed: {e}"
            ) from e
        except GenerationFailedError:
            raise
        except Exception as e:
            raise GenerationFailedError(
                f"MiniMax Music API request failed: {e}"
            ) from e

        audio_url = self._extract_audio_url(result)
        try:
            audio_path = await self._download_audio(audio_url, input_data.output_dir)
        except httpx.HTTPError as e:
            raise GenerationFailedError(
                f"MiniMax audio download failed: {e}"
            ) from e

        return AudioOutput(
            file_path=audio_path,
            duration_seconds=0.0,
            sample_rate=self._config.sample_rate,
            format=self._config.audio_format,
            channels=2,
        )
