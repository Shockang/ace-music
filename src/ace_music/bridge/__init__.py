"""DirectorBridge: standardized scene-to-music integration contract.

This module provides a public request/response contract for orchestration
systems that need to request music tracks and receive generated audio plus
metadata in return.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DirectorBridge(BaseModel):
    """Public orchestration <-> ace-music standardized interface."""

    version: str = "1.0"

    class Request(BaseModel):
        """External orchestrator -> ace-music scene-oriented music request."""

        scene_id: str = Field(description="Unique scene identifier from the calling system")
        mood: str = Field(description="Emotional mood tag (e.g. 'melancholic', 'upbeat')")
        duration_seconds: float = Field(ge=5.0, le=240.0, description="Target duration")
        style_reference: str | None = Field(default=None, description="Style reference description")
        lyrics_hint: str | None = Field(default=None, description="Optional lyrics hint")
        tempo_preference: str | None = Field(default=None, description="Tempo preference")
        output_format: str = Field(default="wav")
        seed: int | None = Field(default=None, description="Reproducibility seed")
        scene_description: str | None = Field(
            default=None, description="Full scene description for context-aware music generation"
        )
        intensity: float | None = Field(
            default=None,
            ge=0.0,
            le=1.0,
            description="Emotional intensity (0.0=subtle, 1.0=extreme)",
        )
        valence: float | None = Field(
            default=None, ge=-1.0, le=1.0, description="Valence coordinate for music mapping"
        )
        arousal: float | None = Field(
            default=None, ge=0.0, le=1.0, description="Arousal coordinate for pace/energy mapping"
        )
        shot_count: int | None = Field(
            default=None, ge=0, description="Shot count proxy for visual pacing"
        )
        dialogue_density: float = Field(
            default=0.5, ge=0.0, le=1.0, description="Relative dialogue/TTS density in the scene"
        )
        tts_present: bool = Field(
            default=True, description="Whether TTS/dialogue is expected in the final mix"
        )
        tts_segments: list[dict] | None = Field(
            default=None,
            description="Optional TTS timing windows for contract-aware ducking",
        )
        target_lufs: float | None = Field(
            default=None, ge=-30.0, le=-10.0, description="Desired integrated loudness target"
        )
        max_true_peak_db: float | None = Field(
            default=None, ge=-6.0, le=0.0, description="Desired maximum true peak ceiling"
        )
        crossfade_seconds: float | None = Field(
            default=None,
            ge=0.0,
            le=10.0,
            description="Desired segment transition crossfade duration",
        )
        preset_name: str | None = Field(
            default=None, description="Style preset name to use (e.g. 'dark_suspense')"
        )
        is_instrumental: bool = Field(
            default=False, description="Generate instrumental (no vocals)"
        )

    class Response(BaseModel):
        """ace-music -> external orchestrator generated audio result."""

        audio_path: str = Field(description="Path to the generated audio file")
        duration_seconds: float = Field(description="Actual duration of the audio")
        format: str = Field(default="wav")
        metadata: dict = Field(
            default_factory=dict,
            description="BPM, key, style tags, and other generation metadata",
        )
        scene_id: str = Field(description="Echo of the requesting scene ID")
        success: bool = Field(default=True, description="Whether generation succeeded")
        error: str | None = Field(default=None, description="Error message if generation failed")
