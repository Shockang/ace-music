"""Pipeline input/output models for the full generation flow."""

from pydantic import BaseModel, Field

from ace_music.schemas.audio_contract import AudioSceneContract
from ace_music.schemas.material import MaterialContext
from ace_music.schemas.output_config import OutputConfig


class PipelineInput(BaseModel):
    """Top-level input to the MusicAgent pipeline."""

    description: str = Field(
        description="Natural language description of the desired music"
    )
    lyrics: str | None = Field(
        default=None, description="Pre-written lyrics (raw text)"
    )
    style_tags: list[str] = Field(
        default_factory=list, description="Pre-known style tags"
    )
    duration_seconds: float = Field(
        default=60.0, ge=5.0, le=240.0, description="Target audio duration"
    )
    language: str = Field(default="en")
    is_instrumental: bool = False
    seed: int | None = Field(default=None, description="Reproducibility seed")
    output_format: str = Field(default="wav")
    output_dir: str = Field(default="./output")

    # Style overrides
    tempo_preference: str | None = None
    mood: str | None = None
    preset_name: str | None = Field(
        default=None, description="Name of style preset to use (overrides heuristic style)"
    )
    guidance_scale: float | None = None
    infer_step: int | None = None
    output_config: OutputConfig | None = Field(
        default=None, description="Output configuration (naming, path, metadata)"
    )
    audio_contract: AudioSceneContract | None = Field(
        default=None,
        description="Structured scene/video audio contract from upstream orchestration",
    )
    material_context: MaterialContext | None = Field(
        default=None,
        description="Daily material context (inspiration, lyrics, style) driving this generation",
    )

    # Automation hardening
    stage_timeout_seconds: float | None = Field(
        default=120.0,
        gt=0,
        description=(
            "Default timeout per non-generation pipeline stage; "
            "None disables stage timeout"
        ),
    )
    generation_timeout_seconds: float | None = Field(
        default=600.0,
        gt=0,
        description="Timeout for the model generation stage; None falls back to stage timeout",
    )
    expected_sample_rate: int = Field(
        default=48000,
        gt=0,
        description="Expected output sample rate used by final audio validation",
    )
    min_valid_duration_seconds: float = Field(
        default=1.0,
        ge=0,
        description="Minimum valid output duration for audio validation",
    )
    duration_tolerance_seconds: float = Field(
        default=5.0,
        ge=0,
        description="Allowed absolute duration delta around requested duration",
    )


class PipelineOutput(BaseModel):
    """Top-level output from the MusicAgent pipeline."""

    audio_path: str = Field(description="Path to the final audio file")
    duration_seconds: float
    format: str
    sample_rate: int = 48000
    metadata: dict = Field(
        default_factory=dict,
        description="Generation metadata (seed, params, style, lyrics)",
    )
    segments: list[dict] = Field(
        default_factory=list, description="Lyrics segment info"
    )
