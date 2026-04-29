"""Stable Audio API generator."""

from __future__ import annotations

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
            f"stable_audio_{int(time.time())}_{uuid.uuid4().hex[:8]}."
            f"{self._config.audio_format}"
        )
        filepath = out_dir / filename

        async with httpx.AsyncClient(timeout=self._config.timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            filepath.write_bytes(response.content)

        if response.content[:3] != b"ID3" and not response.content.startswith(b"RIFF"):
            raise GenerationFailedError("Downloaded payload is not a recognized audio file")

        return str(filepath)

    def _build_payload(self, input_data: StableAudioInput) -> dict[str, Any]:
        return {
            "prompt": input_data.description,
            "duration": input_data.duration_seconds,
            "output_format": self._config.audio_format,
        }

    def _extract_audio_url(self, result: dict[str, Any]) -> str:
        status = str(result.get("status", "")).lower()
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

            polled = await self._poll_job(job_id)
            audio_url = self._extract_audio_url(polled)
            audio_path = await self._download_audio(audio_url, input_data.output_dir)
        except httpx.HTTPError as exc:
            raise GenerationFailedError(f"Stable Audio API request failed: {exc}") from exc

        return AudioOutput(
            file_path=audio_path,
            duration_seconds=input_data.duration_seconds,
            sample_rate=44100,
            format=self._config.audio_format,
            channels=2,
        )
