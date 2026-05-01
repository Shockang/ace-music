"""Stable Audio API generator."""

from __future__ import annotations

import asyncio
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

STABILITY_AUDIO_BASE_URL = "https://api.stability.ai"
STABILITY_AUDIO_SUBMIT_PATH = "/v2beta/audio/stable-audio-2/text-to-audio"
STABILITY_AUDIO_STATUS_PATH = "/v2beta/audio/stable-audio-2/generations/{job_id}"


class StableAudioInput(BaseModel):
    description: str
    duration_seconds: float = Field(default=30.0, ge=5.0, le=180.0)
    mode: Literal["instrumental"] = "instrumental"
    output_dir: str = "./output"


class StableAudioConfig(BaseModel):
    api_key: str | None = None
    base_url: str = STABILITY_AUDIO_BASE_URL
    timeout: float = 120.0
    rate_limit_per_minute: int = 20
    audio_format: str = "mp3"
    poll_interval_seconds: float = 2.0
    poll_timeout_seconds: float = 600.0

    def model_post_init(self, __context: Any) -> None:
        if self.api_key is None:
            self.api_key = os.environ.get("STABILITY_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Stability API key required. Pass api_key or set STABILITY_API_KEY env var."
            )


class StableAudioGenerator(MusicTool[StableAudioInput, AudioOutput]):
    def __init__(self, config: StableAudioConfig | None = None) -> None:
        self._config = config or StableAudioConfig()

    @property
    def name(self) -> str:
        return "stable_audio_generator"

    @property
    def description(self) -> str:
        return "Generate music using Stability Stable Audio API"

    @property
    def input_schema(self) -> type[StableAudioInput]:
        return StableAudioInput

    @property
    def output_schema(self) -> type[AudioOutput]:
        return AudioOutput

    @property
    def is_read_only(self) -> bool:
        return False

    def _looks_like_audio(self, content: bytes) -> bool:
        return (
            content.startswith(b"ID3")
            or content.startswith(b"RIFF")
            or content.startswith(b"\xff\xfb")
            or content.startswith(b"\xff\xf3")
            or content.startswith(b"\xff\xf2")
        )

    async def _submit_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self._config.timeout) as client:
            response = await client.post(
                f"{self._config.base_url}{STABILITY_AUDIO_SUBMIT_PATH}",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    async def _poll_job(self, job_id: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._config.api_key}"}
        async with httpx.AsyncClient(timeout=self._config.timeout) as client:
            response = await client.get(
                f"{self._config.base_url}{STABILITY_AUDIO_STATUS_PATH.format(job_id=job_id)}",
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    async def _download_audio(self, url: str, output_dir: str) -> str:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = (
            f"stable_audio_{int(time.time())}_{uuid.uuid4().hex[:8]}.{self._config.audio_format}"
        )
        filepath = out_dir / filename

        async with httpx.AsyncClient(timeout=self._config.timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            content = response.content

        if not self._looks_like_audio(content):
            raise GenerationFailedError("Downloaded payload is not a recognized audio file")

        filepath.write_bytes(content)

        return str(filepath)

    def _build_payload(self, input_data: StableAudioInput) -> dict[str, Any]:
        return {
            "prompt": input_data.description,
            "duration": input_data.duration_seconds,
            "output_format": self._config.audio_format,
        }

    def _is_terminal_success(self, result: dict[str, Any]) -> bool:
        status = str(result.get("status", "")).lower()
        return status in {"succeeded", "completed", "complete"} or (
            not status and (result.get("audio_url") or result.get("result", {}).get("audio_url"))
        )

    def _is_terminal_failure(self, result: dict[str, Any]) -> bool:
        return str(result.get("status", "")).lower() in {
            "failed",
            "error",
            "cancelled",
            "canceled",
        }

    def _extract_error_message(self, result: dict[str, Any]) -> str | None:
        error = result.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("detail") or error.get("error")
            if message:
                return str(message)
        if isinstance(error, str) and error:
            return error
        for key in ("message", "detail"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    def _extract_audio_url(self, result: dict[str, Any]) -> str:
        status = str(result.get("status", "")).lower()
        if self._is_terminal_failure(result):
            message = self._extract_error_message(result)
            if message:
                raise GenerationFailedError(
                    f"Stable Audio generation failed: status={status}, error={message}"
                )
            raise GenerationFailedError(f"Stable Audio generation failed: status={status}")
        if status and status not in {"succeeded", "completed", "complete"}:
            raise GenerationFailedError(f"Stable Audio generation not ready: status={status}")

        audio_url = result.get("audio_url") or result.get("result", {}).get("audio_url")
        if not audio_url:
            raise GenerationFailedError("Stable Audio response missing audio_url")
        return audio_url

    async def execute(self, input_data: StableAudioInput) -> AudioOutput:
        try:
            submitted = await self._submit_job(self._build_payload(input_data))
            job_id = submitted.get("id") or submitted.get("job_id")
            if not job_id:
                raise GenerationFailedError("Stable Audio response missing job id")

            last_polled: dict[str, Any] | None = None
            started_at = time.monotonic()
            while True:
                polled = await self._poll_job(job_id)
                last_polled = polled
                if self._is_terminal_success(polled) or self._is_terminal_failure(polled):
                    break

                elapsed = time.monotonic() - started_at
                if elapsed >= self._config.poll_timeout_seconds:
                    status = str(polled.get("status", "")).lower() or "unknown"
                    raise GenerationFailedError(
                        "Stable Audio generation timed out after "
                        f"{self._config.poll_timeout_seconds:g}s: status={status}"
                    )
                await asyncio.sleep(self._config.poll_interval_seconds)

            audio_url = self._extract_audio_url(last_polled or {})
            audio_path = await self._download_audio(audio_url, input_data.output_dir)
        except httpx.HTTPError as exc:
            raise GenerationFailedError(f"Stable Audio API request failed: {exc}") from exc
        except ValueError as exc:
            raise GenerationFailedError(f"Stable Audio configuration error: {exc}") from exc

        return AudioOutput(
            file_path=audio_path,
            duration_seconds=input_data.duration_seconds,
            sample_rate=44100,
            format=self._config.audio_format,
            channels=2,
        )
